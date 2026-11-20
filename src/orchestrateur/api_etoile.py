"""Routes `/api/etoile` : état de l'invitation, usage actif, réponse de l'utilisateur, réglage.

Rôle : relayer `etoile.py` à l'interface. Frontières : aucune décision ici ; routes synchrones (la sonde
publique du dépôt peut bloquer jusqu'au délai borné : elles tournent hors de la boucle d'événements).
Invariants portés : INV-ETOILE-1, INV-API-1 (écritures sous garde locale).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import langues
from .etoile import CHOIX, Etoile


class CorpsUsage(BaseModel):
    secondes: float


class CorpsReponse(BaseModel):
    choix: str


class CorpsReglage(BaseModel):
    actif: bool


def routes(config) -> APIRouter:
    r = APIRouter(prefix="/api/etoile")
    etoile = Etoile(config)

    @r.get("")
    def lire():
        return etoile.etat()

    @r.post("/usage")
    def usage(c: CorpsUsage):
        return etoile.usage(c.secondes)

    @r.post("/reponse")
    def reponse(c: CorpsReponse):
        if c.choix not in CHOIX:
            raise HTTPException(422, langues.t("serveur.api_etoile.choix_attendu", choix=", ".join(CHOIX)))
        return etoile.repondre(c.choix)

    @r.put("")
    def regler(c: CorpsReglage):
        return etoile.regler(c.actif)

    return r
