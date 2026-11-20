"""Routes `/api/manager` : volet de conversation avec l'assistant (le « manager »), sur tous les écrans.

Rôle : lire le fil commun, y écrire une instruction, presser un bouton de choix ou de geste.
Frontières : aucune logique ici (`manager.Fil`) ; l'assistant est la tâche permanente du connecteur
Telegram, qu'il soit configuré ou non.
Invariants portés : INV-MANAGER-1, INV-API-1 (écritures sous l'en-tête X-Orchestrateur, contrôlé par le
garde commun), INV-TELEGRAM-3.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import langues
from .vault import Conflit


class CorpsMessage(BaseModel):
    texte: str = Field(max_length=8000)


class CorpsBouton(BaseModel):
    n: int = Field(ge=1)
    choix: str = Field(max_length=40)  # confirmer | annuler | choix:<i>


def routes(connecteur) -> APIRouter:
    r = APIRouter(prefix="/api/manager")
    fil = connecteur.fil

    @r.get("")
    async def lire():
        return fil.public()

    @r.post("/message")
    async def message(c: CorpsMessage):
        return fil.instruction(c.texte)

    @r.post("/bouton")
    async def bouton(c: CorpsBouton, req: Request):
        # INV-MANAGER-1 : un agent (en-tête X-Orch-Tache) ne confirme pas son propre geste.
        if req.headers.get("X-Orch-Tache", "").strip():
            raise Conflit(langues.t("serveur.api_manager.agent_bouton"))
        return fil.bouton(c.n, c.choix)

    return r
