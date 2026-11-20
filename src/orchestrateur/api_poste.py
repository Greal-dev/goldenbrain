"""Routes de la réservation du poste : lecture, prise (ou file), annulation, restitution.

Rôle : traduire HTTP en appels à `Poste` (`poste.py`) et publier l'événement `poste` aux abonnés.
Frontières : aucune règle ici (délai, titulaire, expiration : `poste.py`) ; la garde INV-API-1 reste
celle d'`api.py`.
Invariants portés : INV-POSTE-1.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .vault import Conflit, Vault


class CorpsReserver(BaseModel):
    tache: str
    motif: str = ""
    attendre: bool = False  # refus : 200 {poste: null, rang} au lieu de 409 (la CLI redemande)


class CorpsAnnuler(BaseModel):
    tache: str


class CorpsLiberer(BaseModel):
    tache: str | None = None  # absent : geste humain, toute réservation tombe


def routes(moteur, vault: Vault) -> APIRouter:
    r = APIRouter()

    @r.get("/api/poste")
    async def lire():
        return {"poste": moteur.poste.actuelle(), "file": moteur.poste.file()}

    @r.post("/api/poste/reserver")
    async def reserver(c: CorpsReserver):
        vault.tache(c.tache)  # 404 si la tâche n'existe pas
        avant = moteur.poste.rang(c.tache)
        try:
            res = moteur.poste.reserver(c.tache, c.motif)
        except Conflit:
            if avant is None:
                moteur.publier("poste")  # nouvel attendant : la file a changé
            if c.attendre:
                return {"poste": None, "rang": moteur.poste.rang(c.tache), "titulaire": moteur.poste.actuelle()}
            raise
        moteur.publier("poste")
        return {"poste": res}

    @r.post("/api/poste/annuler")
    async def annuler(c: CorpsAnnuler):
        if retire := moteur.poste.retirer(c.tache):
            moteur.publier("poste")
        return {"retire": retire}

    @r.post("/api/poste/liberer")
    async def liberer(c: CorpsLiberer):
        rendu = moteur.poste.liberer(c.tache)
        if rendu:
            moteur.publier("poste")
            moteur.publier("arbre")
        return {"libere": rendu, "poste": moteur.poste.actuelle()}

    return r
