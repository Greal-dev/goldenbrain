"""Routes du feu vert lié à une version (`/api/feux-verts`).

Rôle : traduire HTTP en appels à `FeuxVerts` (demande, verdict, lecture).
Frontières : aucune règle ici ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-FEU-1 (par `feux_verts.py`).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .feux_verts import FeuxVerts


class CorpsDemande(BaseModel):
    sha: str
    objet: str
    a: str
    de: str = ""
    sauts: int = 0


class CorpsVerdict(BaseModel):
    geste: str  # accorder | refuser
    motif: str
    de: str = ""
    sauts: int = 0


def routes(feux: FeuxVerts) -> APIRouter:
    r = APIRouter(prefix="/api/feux-verts")

    @r.post("", status_code=201)
    async def demander(c: CorpsDemande):
        return feux.demander(c.sha, c.objet, c.a, c.de, c.sauts)

    @r.post("/{sha}/verdict")
    async def trancher(sha: str, c: CorpsVerdict):
        return feux.trancher(sha, c.geste, c.motif, c.de, c.sauts)

    @r.get("/{sha}")
    async def lire(sha: str):
        return feux.lire(sha)

    return r
