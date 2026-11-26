"""Routes de la modification en bloc : `/api/lots` (aperçu, application) et `/api/lots/{lot}/annuler`.

Rôle : traduire HTTP en appels à `lot_statuts`. Geste réservé à l'humain : une requête portant l'en-tête d'un agent
(`X-Orch-Tache`) est refusée. Depuis un appareil distant, la route compte parmi les gestes à risque (INV-DISTANT-7).
Frontières : aucune logique de lot ici.
Invariants portés : INV-LOT-1.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import langues, lot_statuts


class CorpsLot(BaseModel):
    taches: list[str]
    statut: str | None = None
    echeance: str | None = None  # « » retire l'échéance
    parent: str | None = None  # « racine » détache
    etiquettes: dict | None = None  # {"ajouter": [...], "retirer": [...]} : pose et retrait en bloc (INV-ETIQUETTE-1)
    apercu: bool = False


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api/lots")

    def refuse_agent(request: Request):
        if request.headers.get("x-orch-tache"):  # INV-LOT-1 : le geste de lot n'est jamais celui d'un agent
            return JSONResponse({"detail": langues.t("serveur.lot.humain_seul")}, status_code=403)
        return None

    @r.post("")
    async def appliquer(c: CorpsLot, request: Request):
        if refus := refuse_agent(request):
            return refus
        if c.apercu:
            return lot_statuts.apercu(moteur, c.taches, c.statut, c.echeance, c.parent, c.etiquettes)
        return lot_statuts.appliquer(moteur, c.taches, c.statut, c.echeance, c.parent, c.etiquettes)

    @r.post("/{lot}/annuler")
    async def annuler(lot: str, request: Request):
        if refus := refuse_agent(request):
            return refus
        return lot_statuts.annuler(moteur, lot)

    return r
