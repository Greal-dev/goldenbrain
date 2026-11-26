"""Routes du geste « Confier à l'IA / Renvoyer à l'IA » : une tâche, ou un lot, et la lecture d'état qui les motive.

Rôle : traduire HTTP en appels à `etat_main` (lecture) et `executant.confier` (envoi en file, consigne facultative).
Geste réservé à l'humain : une requête portant l'en-tête d'un agent (`X-Orch-Tache`) est refusée (INV-MAIN-5).
Frontières : aucune logique d'état ici ; un lot exclut les tâches dont un agent travaille (INV-VERROU-1) et celles
sans lecture (pilotage, permanente) ; la file reste maîtresse du départ (mémoire, agents simultanés : INV-ORDO-1).
Invariants portés : INV-MAIN-5 (geste humain seul, un clic envoie la tâche en file, compteur de renvois remis à zéro).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import etat_main, executant, langues, lot_statuts, rattachement
from .vault import Invalide


class CorpsRenvoi(BaseModel):
    consigne: str = ""


class CorpsLotIA(BaseModel):
    taches: list[str]
    consigne: str = ""
    apercu: bool = False


def refus_agent(request: Request):
    if request.headers.get("x-orch-tache"):  # INV-MAIN-5 : un geste humain n'est jamais fait par un agent
        return JSONResponse({"detail": langues.t("serveur.main.humain_seul")}, status_code=403)
    return None


def envoyer(moteur, ident: str, consigne: str = "") -> str:
    """Remet la tâche à l'IA : compteur remis à zéro, consigne (ou reprise par défaut), envoi en file."""
    t = moteur.vault.tache(ident)
    defaut = langues.t("serveur.main.consigne_renvoi" if t.fm.get("session") else "serveur.main.consigne_confier")
    moteur.attente_muette.remettre(ident)
    return executant.confier(moteur, ident, consigne.strip() or defaut)


def plan(moteur, ids: list[str]) -> tuple[list[dict], list[dict]]:
    """(à envoyer, exclues) : seules les tâches en `humain` ou en `file` à renvoyer ; jamais une tâche occupée."""
    ids = rattachement.normaliser(ids)
    if len(ids) > lot_statuts.MAX_LOT:
        raise Invalide(langues.t("serveur.lot.trop", max=lot_statuts.MAX_LOT))
    ctx = etat_main.Contexte(moteur)
    envoi, exclues = [], []
    for i in ids:
        t = moteur.vault.tache(i)
        lu = etat_main.lire(moteur, t, ctx)
        ligne = {"id": i, "titre": t.titre, "etat": (lu or {}).get("cle", "")}
        if moteur.occupation(i) or not lu or lu["cle"] not in ("humain", "file"):
            exclues.append({**ligne, "motif": langues.t("serveur.main.lot_exclue")})
        else:
            envoi.append({**ligne, "geste": lu.get("geste") or "renvoyer"})
    return envoi, exclues


def routes(moteur) -> APIRouter:
    r = APIRouter()

    @r.post("/api/taches/{ident}/ia", status_code=202)
    async def vers_ia(ident: str, request: Request, c: CorpsRenvoi | None = None):
        if refus := refus_agent(request):
            return refus
        return {"etat_execution": envoyer(moteur, ident, c.consigne if c else "")}

    @r.post("/api/lots/ia")
    async def lot_ia(c: CorpsLotIA, request: Request):
        if refus := refus_agent(request):
            return refus
        envoi, exclues = plan(moteur, c.taches)
        if c.apercu:
            return {"envoyees": envoi, "exclues": exclues}
        faits = []
        for e in envoi:
            try:
                envoyer(moteur, e["id"], c.consigne)
                faits.append(e)
            except Exception as ex:  # noqa: BLE001 — une tâche refusée ne bloque pas les autres
                exclues.append({**e, "motif": str(ex)})
        return {"envoyees": faits, "exclues": exclues}

    @r.get("/api/main")
    async def main():
        return {k: v for k, v in etat_main.toutes(moteur).items()}

    @r.get("/api/main/a-moi")
    async def a_moi():
        """« À moi » en trois listes, la plus ancienne d'abord : de quoi dérouler chaque pastille (INV-MAIN-4)."""
        return await asyncio.to_thread(etat_main.par_categorie, moteur)

    return r
