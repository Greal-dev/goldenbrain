"""Route du renommage : changer le titre affiché d'une tâche, sans toucher à son identifiant.

Rôle : traduire HTTP en `Vault.renommer` (le `# …` du corps) ; l'identifiant, le nom du fichier, les liens,
la session et les routes restent valides.
Frontières : aucune logique de titre ici (`vault.titre_valide`) ; garde INV-API-1 celle d'`api.py`.
Invariants portés : INV-RENOMMER-1 (le titre seul change, frontmatter de l'utilisateur intact, INV-VAULT-1).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .vault import Vault


class CorpsTitre(BaseModel):
    titre: str


def routes(vault: Vault, publier, tache) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.post("/taches/{ident}/renommer")
    async def renommer(ident: str, c: CorpsTitre):
        vault.renommer(ident, c.titre)
        publier("arbre")
        return tache(ident)

    return r
