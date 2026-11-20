"""Routes locales de l'accueil d'un nouvel arrivant : état, proposition, validation, « plus tard ».

Rôle : traduire HTTP en appels à `accueil` (plan, sans écriture) et `accueil_ecriture` (après validation).
L'état « accueil fait ou différé » vit dans `<donnees>/etat/accueil.json`. L'accueil se propose seulement
quand le vault ne porte encore aucune tâche ; « Relancer l'accueil » (Réglages) l'ouvre à tout moment.
Frontières : poste seulement (garde d'`api.py`, INV-ACCUEIL-1) ; aucune écriture avant `POST /valider`.
Invariants portés : INV-ACCUEIL-1, INV-ACCUEIL-2.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import accueil, accueil_ecriture, accueil_sources, fiches, premiers_pas, squelette

ROUTE = "/api/accueil"


class CorpsSources(BaseModel):
    sources: dict = Field(default_factory=dict)


class CorpsPlan(BaseModel):
    plan: dict


def routes(config, moteur, vault) -> APIRouter:
    r = APIRouter()
    chemin = config.donnees / "etat" / "accueil.json"

    def etat() -> str:
        try:
            return str(json.loads(chemin.read_text(encoding="utf-8")).get("etat") or "")
        except (OSError, ValueError):
            return ""

    def poser(valeur: str) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(chemin, json.dumps({"etat": valeur}))

    @r.get(ROUTE)
    async def lire():
        vide = not vault.index()[0]
        dispo = await asyncio.to_thread(accueil_sources.disponibles)
        return {"propose": vide and not etat(), "etat": etat() or "jamais", "conversations": dispo,
                "vault": str(vault.racine), "vide": squelette.vide(vault.racine),
                "obsidian": squelette.obsidian(vault.racine)}

    @r.post(ROUTE + "/proposer")
    async def proposer(c: CorpsSources):
        return await asyncio.to_thread(accueil.proposer, vault, c.sources)  # INV-ACCUEIL-2 : n'écrit rien

    @r.post(ROUTE + "/valider")
    async def valider(c: CorpsPlan):
        bilan = await asyncio.to_thread(accueil_ecriture.appliquer, vault, c.plan)
        poser("fait")
        moteur.publier("arbre")
        return bilan

    @r.post(ROUTE + "/plus-tard")
    async def plus_tard():
        poser("differe")
        return {"etat": "differe"}

    r.include_router(premiers_pas.routes(config, moteur, vault))  # même préfixe : poste seulement (INV-ACCUEIL-1)
    return r
