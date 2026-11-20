"""Routes `/api/telegram` : réglages du connecteur, essai de connexion, issue d'un envoi, question d'un agent.

Rôle : lire et écrire `[telegram]` (section seule de `config.toml`), protéger le jeton (DPAPI ou fichier 0600), relancer
le connecteur après un réglage ; reconnaître la discussion de l'utilisateur et l'ancien webhook ; relayer `orch creer --envoi`, `orch rattacher` et `orch telegram`.
Frontières : aucune logique Telegram ici (`telegram.py`) ; aucun secret dans une réponse ni un journal.
Invariants portés : INV-TELEGRAM-1, INV-TELEGRAM-2, INV-INSTALL-1 (terminal du jeton : commande exacte), INV-INTERFACE-2 (la persistance ne touche que
la section réglée).
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel

from . import coffre, langues, telegram_jeton
from .api_interface import remplacer_section
from . import telegram_connexion
from .telegram import Connecteur, ErreurTelegram, dans_un_fil
from .vault import Conflit, Invalide

CLES = ("actif", "discussions", "reception", "conteneur")


class CorpsTelegram(BaseModel):
    actif: bool | None = None
    discussions: list[str] | None = None
    reception: str | None = None
    conteneur: str | None = None
    jeton: str | None = None  # écrit protégé (DPAPI ou fichier 0600), jamais dans config.toml ; "" = l'effacer


class CorpsAccord(BaseModel):
    accord: str


class CorpsIssue(BaseModel):
    tache: str
    cree: bool = True


class CorpsQuestion(BaseModel):
    tache: str
    texte: str
    boutons: bool = False  # compte rendu : Valider / Renvoyer au lieu d'une question libre
    vise: str = ""  # tâche touchée : sa ligne (titre, place, lien) suit le texte
    choix: list[str] = []  # 2-3 tâches candidates : boutons de choix
    geste: str = ""  # statut=… | echeance=… | priorite=… sur `vise`, appliqué sur Confirmer


def _toml(v) -> str:
    # json produit des chaînes et des listes de chaînes valides en TOML (échappements compris).
    return str(v).lower() if isinstance(v, bool) else json.dumps(v, ensure_ascii=False)


def routes(config, moteur, connecteur: Connecteur) -> APIRouter:
    r = APIRouter(prefix="/api/telegram")
    cfg = config.telegram

    @r.get("")
    async def lire():
        return {**connecteur.public(), "commande_jeton": telegram_jeton.commande(config)}

    @r.post("/jeton/terminal")
    async def jeton_terminal(c: CorpsAccord):
        # INV-INSTALL-1 : on ne lance que la commande montrée, caractère pour caractère.
        if c.accord != telegram_jeton.commande(config):
            raise Invalide(langues.t("serveur.api_telegram.accord_commande"))
        motif = telegram_jeton.ouvrir_terminal(telegram_jeton.argv(config))
        return {"ok": not motif, "motif": motif}

    @r.put("")
    async def regler(c: CorpsTelegram):
        maj = {k: getattr(c, k) for k in CLES if getattr(c, k) is not None}
        if "discussions" in maj:
            maj["discussions"] = [d.strip() for d in maj["discussions"] if d.strip()]
            if any(not d.lstrip("-").isdigit() for d in maj["discussions"]):
                raise Invalide(langues.t("serveur.api_telegram.discussion_entier"))
        if "conteneur" in maj and maj["conteneur"]:
            moteur.vault.conteneur(maj["conteneur"])  # INV-VAULT-3 : conteneur connu, sinon 404
        ancien = {k: getattr(cfg, k) for k in CLES}
        for k, v in maj.items():
            setattr(cfg, k, v)
        try:
            connecteur.reception()  # INV-NOTE-1 : dossier de réception sous le vault
            if c.jeton is not None:
                coffre.proteger(c.jeton, connecteur.fichier_jeton())  # INV-TELEGRAM-2
            if config.chemin and maj:
                remplacer_section(config.chemin, "telegram",
                                  [(k, _toml(getattr(cfg, k))) for k in CLES], garder=("api", "jeton_fichier"))
        except (Invalide, OSError) as e:
            for k, v in ancien.items():
                setattr(cfg, k, v)
            raise Invalide(str(e)) from e
        connecteur.arreter()
        connecteur.demarrer()  # INV-TELEGRAM-1 : ne lit que si actif ET jeton présent
        moteur.publier("interface")
        return connecteur.public()

    @r.post("/tester")
    async def tester():
        return await connecteur.tester()

    @r.post("/reconnaitre")
    async def reconnaitre():
        """Discussions qui ont écrit au bot (INV-TELEGRAM-5 ; un autre lecteur donne un 409, expliqué)."""
        try:
            # Connecteur en marche : ses discussions vues, pas un second lecteur (409).
            vues = dict(connecteur.vues) if connecteur.tache else None
            return {"ok": True, **await dans_un_fil(telegram_connexion.reconnaitre, connecteur.client(), vues)}
        except (ErreurTelegram, Invalide) as e:
            return {"ok": False, "motif": langues.t("serveur.api_telegram.erreur_409", detail=e) if "409" in str(e) else str(e)}

    @r.post("/webhook/desactiver")
    async def desactiver_webhook():
        try:
            await dans_un_fil(telegram_connexion.desactiver_webhook, connecteur.client())
            return {"ok": True}
        except (ErreurTelegram, Invalide) as e:
            return {"ok": False, "motif": str(e)}

    @r.post("/envois/{n}/issue")
    async def issue(n: int, c: CorpsIssue):
        try:
            return await connecteur.issue(n, c.tache, c.cree)
        except ErreurTelegram as e:
            raise Conflit(langues.t("serveur.api_telegram.conflit", detail=e)) from None

    @r.post("/question")
    async def question(c: CorpsQuestion):
        try:
            return await connecteur.question(c.tache, c.texte, c.boutons, c.choix, c.geste, c.vise)
        except ErreurTelegram as e:
            raise Conflit(langues.t("serveur.api_telegram.conflit", detail=e)) from None

    return r
