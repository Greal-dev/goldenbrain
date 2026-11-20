"""Routes du codespace d'une tâche : état, gestes (VS Code, navigateur, arrêt), lieu d'exécution.

Rôle : traduire HTTP en appels à `codespace.py` ; poser la clé `ou:` de la tâche.
Frontières : aucun appel direct à `gh` ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-CODESPACE-2 (le lieu ne change pas pendant un tour), INV-VAULT-1 (par `Vault`).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import codespace, langues
from .vault import Conflit, Invalide, Vault


class CorpsLieu(BaseModel):
    ou: str


def routes(vault: Vault, moteur, tache) -> APIRouter:
    r = APIRouter(prefix="/api/taches/{ident}")

    @r.get("/codespace")
    async def etat(ident: str, frais: bool = False):
        return await codespace.etat(vault, vault.tache(ident), frais)

    @r.post("/codespace/{quoi}")
    async def geste(ident: str, quoi: str):
        if quoi not in (*codespace.GESTES, "arreter"):
            raise Invalide(langues.t("serveur.api_codespace.geste_inconnu", geste=quoi))
        await codespace.geste(vault, vault.tache(ident), quoi)
        return await codespace.etat(vault, vault.tache(ident))

    @r.post("/ou")
    async def lieu(ident: str, c: CorpsLieu):
        if c.ou not in codespace.LIEUX:
            raise Invalide(langues.t("serveur.api_codespace.lieu_inconnu", lieu=c.ou))
        if moteur.etat_de(ident) in ("en_cours", "en_file"):
            raise Conflit(langues.t("serveur.api_codespace.seance_en_cours"))
        vault.modifier(ident, {"ou": "codespace" if c.ou == "codespace" else None})
        moteur.publier("arbre")
        return tache(ident)

    return r
