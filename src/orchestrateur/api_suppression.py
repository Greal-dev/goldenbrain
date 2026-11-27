"""Routes de la suppression d'une tâche ou d'un projet : aperçu, puis geste.

Rôle : `GET /api/suppression` (ce que le dialogue annonce), `POST /api/taches/{id}/supprimer`,
`POST /api/conteneurs/supprimer` ; `api.py` est plafonné à 500 lignes.
Frontières : aucune logique de vault ici (module `suppression`) ; refuse tout appel d'agent.
Invariants portés : INV-SUPPR-1 (geste humain : un agent, par l'en-tête de sa tâche ou un jeton
d'exécuteur, reçoit 403 ; aucune commande `orch`).
"""

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import api_executeurs, langues, suppression
from .vault import ErreurOrch


class Interdit(ErreurOrch):
    code = 403


class CorpsSupprimerTache(BaseModel):
    sous_taches: str | None = None  # "supprimer" | "deplacer"
    vers: str | None = None


class CorpsSupprimerConteneur(BaseModel):
    conteneur: str
    contenu: str | None = None  # "supprimer" | "deplacer"
    vers: str | None = None


def _humain(request: Request) -> None:
    # INV-SUPPR-1 : effacer est un geste humain ; un agent ne supprime jamais.
    if request.headers.get("x-orch-tache") or request.headers.get(api_executeurs.ENTETE):
        raise Interdit(langues.t("serveur.suppression.agent_refuse"))


def routes(moteur, aligneur) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/suppression")
    def apercu(tache: str | None = None, conteneur: str | None = None):
        return suppression.apercu(moteur, aligneur, tache, conteneur)

    @r.post("/taches/{ident}/supprimer")
    async def supprimer_tache(ident: str, c: CorpsSupprimerTache, request: Request):
        _humain(request)
        return await suppression.supprimer(moteur, aligneur, partial(
            suppression.plan_tache, moteur, ident, c.sous_taches, c.vers))

    @r.post("/conteneurs/supprimer")
    async def supprimer_conteneur(c: CorpsSupprimerConteneur, request: Request):
        _humain(request)
        return await suppression.supprimer(moteur, aligneur, partial(
            suppression.plan_projet, moteur, aligneur, c.conteneur, c.contenu, c.vers))

    return r
