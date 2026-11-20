"""Routes de la validation automatique par périmètre : réglage d'un conteneur, geste « Rouvrir ».

Rôle : traduire HTTP en appels à `validation_auto` (moteur.validation_auto).
Frontières : aucune logique de décision ici ; la clôture automatique se décide dans le moteur.
Invariants portés : INV-VALID-2 (réglage et réouverture sont des gestes humains).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from . import validation_auto


class CorpsReglage(BaseModel):
    conteneur: str
    mode: str


class CorpsRouvrir(BaseModel):
    tache: str


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api/validation-auto")

    @r.get("/reglage")
    async def lire(conteneur: str):
        """Mode posé par ce conteneur (« » s'il hérite) et accord tracé."""
        fm = (await asyncio.to_thread(moteur.vault.index))[1]
        if conteneur not in fm:
            return {"conteneur": conteneur, "mode": "", "accord": ""}
        chemin = moteur.vault.racine / conteneur / moteur.vault.cfg.contexte
        try:
            meta = moteur.vault._lire_meta(chemin)[0]
        except OSError:
            meta = {}
        mode = str(meta.get("validation") or "").strip().casefold()
        return {"conteneur": conteneur, "mode": mode if mode in validation_auto.MODES else "",
                "accord": str(meta.get("validation_accord") or "")}

    @r.post("/reglage")
    async def regler(c: CorpsReglage):
        return await asyncio.to_thread(moteur.validation_auto.regler, c.conteneur, c.mode)

    @r.post("/rouvrir")
    async def rouvrir(c: CorpsRouvrir):
        moteur.validation_auto.rouvrir(c.tache)
        return {"tache": c.tache, "statut": "fait"}

    @r.post("/reevaluer")
    async def reevaluer():
        """Relevé sans clôture : un motif par tâche `fait` des périmètres automatiques."""
        notes = await asyncio.to_thread(moteur.validation_auto.reevaluer)
        return {"total": len(notes), "taches": notes}

    return r
