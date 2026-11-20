"""Routes `/api/taches/{id}/resultat` : liste de ce que la tâche a produit, ouverture d'un élément.

Rôle : relayer `resultat.py` à l'interface. Frontières : aucune décision ici ; routes synchrones (lecture
du disque hors de la boucle d'événements). Poste seulement : la garde distante (`api_appareils.POSTE_SEUL_RE`)
refuse ces routes à un appareil distant.
Invariants portés : INV-RESULTAT-1, INV-API-1 (écriture sous garde locale).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import resultat


class CorpsOuvrir(BaseModel):
    cible: str = Field(min_length=1, max_length=2000)


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api/taches/{ident}/resultat")

    @r.get("")
    def lire(ident: str):
        return resultat.chercher(moteur, ident)

    @r.post("/ouvrir")
    def ouvrir(ident: str, c: CorpsOuvrir):
        return resultat.ouvrir(moteur, ident, c.cible)

    return r
