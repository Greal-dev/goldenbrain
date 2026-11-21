"""Routes des chaînes : modèles (liste, enregistrement, retrait), lancement, suivi, validation, reprise, ajustement.

Rôle : traduire HTTP en appels à `chaines` (modèles) et `chaines_execution.Chaines` (exécutions), hors d'`api.py`
(plafonné à 500 lignes). Les erreurs du vault (`Invalide`, `NonTrouve`, `Conflit`) sont traduites par `api.py`.
Frontières : aucune logique d'enchaînement ici ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-CHAINE-1, INV-CHAINE-2, INV-CHAINE-3.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import chaines
from .chaines_execution import Chaines


class CorpsModele(BaseModel):
    id: str = ""  # vide : tiré du titre
    titre: str
    resume: str = ""
    contexte: str = ""
    phases: list[dict]
    surveiller: str = ""
    conteneur: str = ""


class CorpsLancer(BaseModel):
    modele: str
    conteneur: str | None = None
    dossier: str = ""
    titre: str = ""


class CorpsAjuster(BaseModel):
    de: str  # tâche de la phase qui ajuste (l'agent passe `ORCH_TACHE`) ou tâche parente
    action: str
    n: str = ""
    titre: str = ""
    consigne: str = ""
    motif: str = ""


def routes(moteur) -> APIRouter:
    """Crée aussi `moteur.chaines`, dont la boucle (fin des tours, surveillance) part avec le serveur."""
    execution = moteur.chaines = Chaines(moteur)
    r = APIRouter(prefix="/api/chaines")
    racine = execution.vault.racine

    @r.get("")
    async def modeles():
        return chaines.lister(racine)

    @r.post("")
    async def enregistrer(c: CorpsModele):
        return chaines.enregistrer(racine, c.model_dump(), c.id)

    @r.post("/{ident}/retirer")
    async def retirer(ident: str):
        chaines.retirer(racine, ident)
        return {"ok": True}

    @r.post("/lancer")
    async def lancer(c: CorpsLancer):
        parent = execution.lancer(c.modele, c.conteneur or None, c.dossier, c.titre)
        return execution.public(parent)

    @r.get("/executions")
    async def executions():
        return execution.liste()

    @r.get("/executions/{tache}")
    async def plan(tache: str):  # la tâche parente ou l'une de ses phases
        return execution.plan(tache)

    @r.post("/executions/{parent}/poursuivre")
    async def poursuivre(parent: str):
        return execution.poursuivre(parent)

    @r.post("/executions/{parent}/reprendre")
    async def reprendre(parent: str):
        return execution.reprendre(parent)

    @r.post("/ajuster")
    async def ajuster(c: CorpsAjuster):
        return execution.ajuster(c.de, c.action, c.n, c.titre, c.consigne, c.motif)

    return r
