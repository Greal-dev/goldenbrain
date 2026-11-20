"""Mode « Apprendre » : routes `/api/apprendre` (réglage général) et `/api/taches/{id}/apprendre` (réglage de la tâche).

Rôle : lire et persister `[apprendre] actif` de `config.toml` ; poser ou retirer `apprendre` dans le frontmatter d'une tâche.
Frontières : la consigne est construite par `apprendre` et `moteur` ; l'effet vaut à partir du tour suivant.
Invariants portés : INV-APPRENDRE-1.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .api_simultanes import ecrire_cles


class CorpsGeneral(BaseModel):
    actif: bool


class CorpsTache(BaseModel):
    valeur: bool | None = None  # None : la tâche suit le réglage général


def routes(config, moteur, tache) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/apprendre")
    async def lire():
        return {"actif": config.apprendre.actif}

    @r.put("/apprendre")
    async def regler(c: CorpsGeneral):
        if config.chemin:
            ecrire_cles(config.chemin, "apprendre", {"actif": c.actif})  # d'abord le disque
        config.apprendre.actif = c.actif
        return {"actif": c.actif}

    @r.post("/taches/{ident}/apprendre")
    async def poser(ident: str, c: CorpsTache):
        moteur.vault.modifier(ident, {"apprendre": None if c.valeur is None else ("oui" if c.valeur else "non")})
        return tache(ident)

    return r
