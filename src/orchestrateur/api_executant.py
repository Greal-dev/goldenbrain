"""Routes du curseur « Moi / IA » d'une tâche : exécutant, notes de l'utilisateur, « Confier la suite ».

Rôle : traduire HTTP en appels à `executant.py`.
Frontières : la garde des écritures d'agent est appelée par le middleware d'`api.py` ; aucune
écriture vault ici (tout passe par `executant`, donc par `Vault`).
Invariants portés : INV-EXECUTANT-1, INV-EXECUTANT-2, INV-EXECUTANT-3 (aucun agent n'écrit les notes : garde
d'`api.py`), INV-VAULT-1 (par `Vault`).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import api_main, executant, notes_ia


class CorpsExecutant(BaseModel):
    executant: str


class CorpsNote(BaseModel):
    texte: str


class CorpsNotesIA(BaseModel):
    action: str
    texte: str


class CorpsConfier(BaseModel):
    consigne: str = ""


def routes(moteur, tache) -> APIRouter:
    r = APIRouter(prefix="/api/taches/{ident}")

    @r.post("/executant")
    async def poser(ident: str, c: CorpsExecutant):
        executant.poser(moteur, ident, c.executant)
        return tache(ident)

    @r.post("/notes", status_code=201)
    async def ajouter(ident: str, c: CorpsNote):
        return executant.ajouter_note(moteur.vault, ident, c.texte)

    @r.put("/notes/{n}")
    async def modifier(ident: str, n: int, c: CorpsNote):
        return executant.modifier_note(moteur.vault, ident, n, c.texte)

    @r.post("/notes/ia")
    async def notes_ia_proposer(ident: str, c: CorpsNotesIA):
        # INV-EXECUTANT-3 : proposition seulement ; l'écriture suit le geste de l'utilisateur.
        return await notes_ia.proposer(moteur, ident, c.action, c.texte)

    @r.post("/confier", status_code=202)
    async def confier(ident: str, c: CorpsConfier, request: Request):
        if refus := api_main.refus_agent(request):  # INV-MAIN-5
            return refus
        moteur.attente_muette.remettre(ident)
        return {"etat_execution": executant.confier(moteur, ident, c.consigne)}

    return r
