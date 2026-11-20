"""Conversation d'une tâche et modification d'un message envoyé : routes HTTP.

Rôle : `GET /api/taches/{id}/conversation` (messages reliés à leur tour), plan et exécution de
« Modifier » (`GET|POST /api/taches/{id}/modifier`), versions archivées (`/versions`).
Frontières : la logique vit dans `retour` (et `points` pour git) ; aucune écriture vault ici.
Invariants portés : INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3, INV-EXEC-7, INV-EXEC-8.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from . import fiches, retour, sessions
from .moteur import session_valide


class CorpsModifier(BaseModel):
    tour: str
    texte: str
    code: bool = False


async def conversation(config, moteur, harnais_de, ident: str, limite: int = 200) -> list[dict]:
    t, _, h = harnais_de(ident)
    session_ = str(t.fm.get("session") or "")
    lus, depuis_journaux = [], False
    if session_:
        # Lecture et analyse du transcript hors de la boucle : il peut peser plusieurs Mo.
        try:
            lus = await asyncio.to_thread(h.transcript, session_valide(session_), limite)
        except NotImplementedError:  # harnais sans transcript lisible : les journaux en tiennent lieu
            depuis_journaux = True
    else:  # aucune session (premier tour en échec) : seuls les journaux ont gardé l'échange
        depuis_journaux = True
    if depuis_journaux:
        lus = await asyncio.to_thread(sessions.relire_journaux, config.donnees, ident,
                                      limite, moteur.registre)
    else:  # le transcript ignore les échecs de tour : on les relit au journal (INV-EXEC-8)
        lus = sessions.inserer_par_date(
            list(lus), await asyncio.to_thread(sessions.echecs_journaux, config.donnees, ident))
    messages = [asdict(m) for m in lus]
    for m in messages:
        m["texte"] = fiches.sans_rendu(m["texte"])
    messages = [m for m in messages if m["texte"] or m["outils"]]
    # INV-EXEC-7 : le transcript n'a le message d'un tour qu'une fois écrit par le harnais (et rien
    # avant la première session) : le message du tour en cours s'affiche d'emblée.
    if (en_cours := moteur.message_en_cours(ident)) and not any(
            m["role"] == "utilisateur" and en_cours["texte"].strip()[:80] in m["texte"]
            for m in messages):
        messages.append(en_cours)
    # INV-RETOUR-1 : chaque message envoyé par GoldenBrain est relié à son tour (« Modifier »).
    return retour.annoter(messages, await asyncio.to_thread(retour.lister, config.donnees, ident))


def _public(p: dict) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}


def routes(config, moteur, harnais_de) -> APIRouter:
    r = APIRouter(prefix="/api/taches/{ident}")

    @r.get("/conversation")
    async def lire(ident: str, limite: int = 200):
        return await conversation(config, moteur, harnais_de, ident, limite)

    @r.get("/modifier")
    async def planifier(ident: str, tour: str):
        msgs = await conversation(config, moteur, harnais_de, ident)
        h = harnais_de(ident)[2]
        return _public(await asyncio.to_thread(retour.plan, moteur, ident, tour, msgs, h))

    @r.post("/modifier", status_code=202)
    async def modifier(ident: str, c: CorpsModifier):
        msgs = await conversation(config, moteur, harnais_de, ident)
        return await retour.modifier(moteur, ident, c.tour, c.texte, c.code, msgs, harnais_de(ident)[2])

    @r.get("/versions")
    async def versions(ident: str):
        moteur.vault.tache(ident)
        return await asyncio.to_thread(retour.versions, config.donnees, ident)

    @r.get("/versions/{n}")
    async def version(ident: str, n: int):
        h = harnais_de(ident)[2]
        return await asyncio.to_thread(retour.version, config.donnees, ident, n, moteur.registre, h)

    return r
