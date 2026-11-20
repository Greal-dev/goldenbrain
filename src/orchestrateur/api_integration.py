"""Routes `/api/integration` : lire et régler la pastille « intégration en retard » (INV-INTEG-1).

Rôle : exposer `[integration]` (branche d'intégration, seuil en heures) et le persister dans `config.toml`.
Frontières : la lecture git et le cache sont dans `integration` ; aucune écriture vault.
Invariants portés : INV-INTEG-1.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter
from pydantic import BaseModel

from .api_simultanes import ecrire_cles
from .vault import Invalide


class CorpsIntegration(BaseModel):
    branche: str | None = None
    retard_h: float | None = None


def routes(config, suivi) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/integration")
    async def lire():
        return suivi.public()

    @r.put("/integration")
    async def regler(c: CorpsIntegration):
        champs = {k: v for k, v in c.model_dump().items() if v is not None}
        try:
            cible = replace(suivi.config, **champs)  # valide avant toute écriture
        except (TypeError, ValueError) as e:
            raise Invalide(str(e)) from e
        if config.chemin and champs:
            ecrire_cles(config.chemin, "integration", champs)
        suivi.config = cible
        return suivi.public()

    return r
