"""Routes `/api/mail` : réglage de la messagerie, lecture de la boîte, réponse et transfert, mail → tâche.

Rôle : traduire HTTP en appels à `mail_imap` (toujours hors de la boucle d'événements), `mail_message` et `mail_tache`.
Frontières : aucune logique IMAP ni de contenu ici ; réservé au poste (`api_appareils.POSTE_SEUL`) ET refusé à tout
agent (en-tête de tâche ou jeton d'exécuteur) : lire, envoyer et ranger un mail sont des gestes humains ; aucune
réponse ne porte le mot de passe.
Invariants portés : INV-MAIL-1, INV-MAIL-3 (document HTML servi sous CSP `sandbox` sans script, images distantes
seulement sur demande), INV-MAIL-4, INV-MAIL-6, INV-MAIL-7 (geste humain : un agent reçoit 403), INV-INSTALL-1.
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import api_executeurs, langues, mail_imap, mail_mdp, mail_message, mail_tache, telegram_jeton
from .api_simultanes import ecrire_cles
from .config_messagerie import ConfigMessagerie
from .vault import ErreurOrch, Invalide

AIDE = "https://myaccount.google.com/apppasswords"
MODES = ("repondre", "repondre_tous", "transferer")
CACHE = 4  # derniers messages bruts gardés : ouvrir un mail lit le détail, le cadre HTML puis ses pièces


class Interdit(ErreurOrch):
    code = 403


class CorpsAdresse(BaseModel):
    adresse: str = Field(max_length=320)


class CorpsAccord(BaseModel):
    accord: str


class CorpsMessage(BaseModel):
    vue: str = Field(max_length=500)
    uid: int = Field(ge=1)


class CorpsRestaurer(BaseModel):
    message_id: str = Field(min_length=1, max_length=998, pattern=r"^[^\r\n\x00]+$")


class CorpsMarquer(CorpsMessage):
    lu: bool


class CorpsEnvoi(CorpsMessage):
    mode: str
    a: str = Field(max_length=4000)
    cc: str = Field(default="", max_length=4000)
    objet: str = Field(default="", max_length=1000)
    texte: str = Field(default="", max_length=200_000)


class CorpsTache(CorpsMessage):
    tache: str = Field(max_length=300)
    instruction: str = ""
    libre: str = Field(default="", max_length=2000)
    lancer: bool = False


def humain(request: Request) -> None:
    # INV-MAIL-7 : la boîte d'un humain ne s'ouvre ni ne parle pour un agent, comme la suppression (INV-SUPPR-1).
    if request.headers.get("x-orch-tache") or request.headers.get(api_executeurs.ENTETE):
        raise Interdit(langues.t("serveur.mail.agent_refuse"))


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api/mail", dependencies=[Depends(humain)])
    etat = {"boite": mail_imap.Boite(mail_imap.compte(config)), "bruts": {}}

    def boite() -> mail_imap.Boite:
        return etat["boite"]

    async def brut(vue: str, uid: int, marquer_lu: bool = False) -> tuple[bytes, list[str]]:
        cle = (vue, uid)
        if not marquer_lu and cle in etat["bruts"]:
            return etat["bruts"][cle]
        r_ = await asyncio.to_thread(boite().brut, vue, uid, marquer_lu)  # INV-MAIL-6
        etat["bruts"] = {**dict(list(etat["bruts"].items())[-(CACHE - 1):]), cle: r_}
        return r_

    def public() -> dict:
        cpt = mail_imap.compte(config)
        source = mail_imap.mot_de_passe(cpt)[1]  # INV-MAIL-1 : on dit d'où il vient, jamais ce qu'il est
        return {"adresse": cpt.adresse, "mdp": bool(source), "source": source, "commande_mdp": mail_mdp.commande(config), "aide": AIDE}

    @r.get("/reglages")
    def lire_reglages():
        return public()

    @r.put("/reglages")
    def regler(c: CorpsAdresse):
        try:
            nouveau = ConfigMessagerie(**{**config.messagerie.__dict__, "adresse": c.adresse})
        except ValueError as e:
            raise Invalide(str(e)) from e
        if config.chemin:
            ecrire_cles(config.chemin, "messagerie", {"adresse": nouveau.adresse})
        config.messagerie = nouveau
        boite().fermer()
        etat["boite"], etat["bruts"] = mail_imap.Boite(mail_imap.compte(config)), {}
        return public()

    @r.post("/mdp/terminal")
    def mdp_terminal(c: CorpsAccord):
        # INV-INSTALL-1 : seule la commande montrée, caractère pour caractère.
        if c.accord != mail_mdp.commande(config):
            raise Invalide(langues.t("serveur.api_telegram.accord_commande"))
        boite().fermer()  # le prochain échange relira le coffre
        motif = telegram_jeton.ouvrir_terminal(mail_mdp.argv(config), "Messagerie")
        return {"ok": not motif, "motif": motif}

    @r.post("/tester")
    async def tester():
        try:
            return await asyncio.to_thread(boite().tester)
        except ErreurOrch as e:
            return {"ok": False, "motif": str(e)}

    @r.get("/dossiers")
    async def dossiers():
        return await asyncio.to_thread(boite().dossiers)

    @r.get("/messages")
    async def messages(vue: str = "inbox", q: str = "", page: int = 0):
        return await asyncio.to_thread(boite().lister, vue, q.strip(), max(page, 0))

    @r.get("/message")
    async def message(vue: str, uid: int):
        octets, flags = await brut(vue, uid, marquer_lu=True)
        return {"vue": vue, **mail_message.detail(octets, uid, flags)}

    @r.get("/html")
    async def html(vue: str, uid: int, images: bool = False):
        octets, _ = await brut(vue, uid)
        dehors = " https: http:" if images else ""
        # INV-MAIL-3 : ni script, ni formulaire, ni origine ; seules les images (sur demande) sortent du poste.
        csp = (f"sandbox allow-popups allow-popups-to-escape-sandbox; default-src 'none'; style-src 'unsafe-inline'; "
               f"img-src data:{dehors}; font-src data:; frame-ancestors 'self'")
        return HTMLResponse(mail_message.html_isole(octets), headers={"Content-Security-Policy": csp, "Referrer-Policy": "no-referrer"})

    @r.get("/piece")
    async def piece(vue: str, uid: int, n: int):
        nom, octets = mail_message.piece((await brut(vue, uid))[0], n)
        # Toujours en téléchargement, jamais interprété par le navigateur (HTML ou SVG joints).
        return Response(octets, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"})

    @r.post("/marquer")
    async def marquer(c: CorpsMarquer):
        await asyncio.to_thread(boite().marquer, c.vue, c.uid, c.lu)
        return {"ok": True}

    @r.post("/archiver")
    async def archiver(c: CorpsMessage):
        # Le Message-ID permet d'annuler : l'UID change avec le dossier (INV-MAIL-8).
        octets, flags = await brut(c.vue, c.uid)
        mid = mail_message.detail(octets, c.uid, flags)["message_id"]
        await asyncio.to_thread(boite().archiver, c.vue, c.uid)
        etat["bruts"].pop((c.vue, c.uid), None)
        return {"ok": True, "message_id": mid}

    @r.post("/restaurer")
    async def restaurer(c: CorpsRestaurer):
        await asyncio.to_thread(boite().restaurer, c.message_id)
        return {"ok": True}

    @r.get("/brouillon")
    async def brouillon(mode: str, vue: str, uid: int):
        if mode not in MODES:
            raise Invalide(langues.t("serveur.mail.mode_inconnu"))
        return mail_message.brouillon(mode, (await brut(vue, uid))[0], config.messagerie.adresse)

    @r.post("/envoyer")
    async def envoyer(c: CorpsEnvoi):
        if c.mode not in MODES:
            raise Invalide(langues.t("serveur.mail.mode_inconnu"))
        original = (await brut(c.vue, c.uid))[0]
        msg = mail_message.composer(c.mode, original, config.messagerie.adresse, c.a, c.cc, c.objet, c.texte)  # INV-MAIL-4
        await asyncio.to_thread(mail_imap.envoyer, boite().cpt, msg)
        return {"ok": True}

    @r.post("/tache")
    async def tache(c: CorpsTache):
        octets = (await brut(c.vue, c.uid))[0]
        # Sur la boucle : quelques écritures du vault, et `soumettre` planifie le tour sur elle.
        return mail_tache.rattacher(moteur, c.tache, octets, c.instruction, c.libre, c.lancer)

    return r
