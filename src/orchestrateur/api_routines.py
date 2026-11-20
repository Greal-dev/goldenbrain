"""Routes des routines programmées : liste, création, programme, pause, « Exécuter maintenant ».

Rôle : traduire HTTP en appels à `routines.Routines` (hors d'`api.py`, plafonné à 500 lignes).
Frontières : aucune logique d'échéance ici ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-ROUTINE-1 (409 si une exécution tourne), INV-ROUTINE-2 (programme validé).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


class CorpsRoutine(BaseModel):
    titre: str
    consigne: str
    programme: str
    conteneur: str | None = None
    harnais: str | None = None
    modele: str | None = None
    contexte: str = "suite"
    rattrapage: str = "une"


class CorpsConversion(BaseModel):
    programme: str
    contexte: str = "suite"
    rattrapage: str = "une"


class CorpsModif(BaseModel):
    programme: str | None = None  # absent = inchangé
    pause: bool | None = None


def routes(routines) -> APIRouter:
    r = APIRouter(prefix="/api/routines")

    @r.get("")
    async def lister():
        return {"routines": routines.liste()}

    @r.post("", status_code=201)
    async def creer(c: CorpsRoutine):
        ident = routines.creer(c.titre, c.consigne, c.programme, c.conteneur, c.harnais or None,
                               c.modele or None, c.contexte, c.rattrapage)
        return routines.public(ident)

    @r.post("/{ident}/convertir", status_code=201)
    async def convertir(ident: str, c: CorpsConversion):
        return routines.convertir(ident, c.programme, c.contexte, c.rattrapage)

    @r.post("/{ident}/retirer")
    async def retirer(ident: str):
        routines.retirer(ident)
        return {"ok": True}

    @r.get("/{ident}")
    async def lire(ident: str):
        return routines.public(ident)

    @r.post("/{ident}/modifier")
    async def modifier(ident: str, c: CorpsModif):
        return routines.modifier(ident, c.programme, c.pause)

    @r.post("/{ident}/executer", status_code=202)
    async def executer(ident: str):
        return {"etat_execution": routines.executer(ident), **routines.public(ident)}

    return r
