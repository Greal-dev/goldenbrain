"""Routes du chat de projet : `/api/pilotage` (conversation d'un nœud de l'arbre).

Rôle : trouver la tâche de pilotage d'un nœud ; au premier message, la créer puis soumettre le
message par le moteur (même chemin que toute tâche).
Frontières : la logique vit dans `pilotage.py` ; la suite de la conversation passe par les routes
ordinaires d'une tâche (`/api/taches/{id}/…`).
Invariants portés : INV-PILOTAGE-1 (créée au premier message, jamais à la lecture).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import langues, pilotage
from .vault import Invalide


class CorpsPilotage(BaseModel):
    noeud: str
    texte: str
    harnais: str | None = None
    modele: str | None = None


def routes(moteur) -> APIRouter:
    r = APIRouter()

    @r.get("/api/pilotage")
    async def lire(noeud: str):
        return {"noeud": noeud, "tache": pilotage.trouver(moteur.vault, noeud)}

    @r.post("/api/pilotage", status_code=202)
    async def ecrire(c: CorpsPilotage):
        if not c.texte.strip():
            raise Invalide(langues.t("serveur.api_pilotage.message_vide"))
        ident = pilotage.ouvrir(moteur, c.noeud)
        return {"tache": ident,
                "etat_execution": moteur.soumettre(ident, c.texte, harnais=c.harnais, modele=c.modele)}

    return r
