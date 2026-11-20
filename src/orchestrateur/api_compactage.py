"""Compactage automatique : routes `/api/compactage` (lire le réglage et la mesure, régler le seuil général).

Rôle : valider et persister le seuil général (`[compactage] pct`, `plafond` de `config.toml`) et servir
la vue de mesure (par harnais et par tranche de taille de contexte). INV-COMPACT-1.
Frontières : le calcul du seuil, l'héritage et la mesure sont dans `compactage` ; aucune écriture vault.
Invariants portés : INV-COMPACT-1.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter
from pydantic import BaseModel

from .api_simultanes import ecrire_cles
from .config import ConfigCompactage
from .vault import Invalide


class CorpsCompactage(BaseModel):
    pct: float | None = None
    plafond: int | None = None


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api")

    def vue() -> dict:
        return {**moteur.compactage_public(), "mesure": moteur.mesures.synthese()}

    @r.get("/compactage")
    async def lire():
        return vue()

    @r.put("/compactage")
    async def regler(c: CorpsCompactage):
        champs = {k: v for k, v in c.model_dump().items() if v is not None}
        try:
            cible = replace(config.compactage, **champs)  # valide (__post_init__) avant toute écriture
        except (TypeError, ValueError) as e:
            raise Invalide(str(e)) from e
        if config.chemin and champs:
            ecrire_cles(config.chemin, "compactage", champs)
        config.compactage = cible
        return vue()

    return r
