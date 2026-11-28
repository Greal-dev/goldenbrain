"""Route du REX : relance à la demande (geste humain) d'une passe de métacognition.

Rôle : traduire HTTP en appel à `moteur.rex.declencher(force=True)`.
Frontières : aucune logique ici ; le REX automatique part de `Vault.apres_statut`.
Invariants portés : INV-REX-1 (la relance manuelle ignore l'interrupteur, la dérogation et « déjà fait », jamais l'absence de session).
"""

from __future__ import annotations

from fastapi import APIRouter

from .vault import Conflit


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api/taches")

    @r.post("/{ident}/rex", status_code=202)
    async def lancer_rex(ident: str):
        moteur.vault.tache(ident)
        if motif := moteur.rex.declencher(ident, force=True):
            raise Conflit(f"REX impossible : {motif}")
        return {"rex": "lance"}

    return r
