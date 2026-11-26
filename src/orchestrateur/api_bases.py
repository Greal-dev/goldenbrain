"""Route `/api/bases/table` (étape a des bases) : un dossier du vault servi comme une table.

Rôle : traduire HTTP en appel à `bases.table`, hors de la boucle d'événements. Lecture en GET (et
non en POST) : une lecture reste permise depuis un appareil distant, où les écritures sont gardées.
Frontières : aucun calcul ici (`bases.py`) ; tout chemin client passe par `notes.chemin_sur` ; la
famille « notes » fermée ferme aussi cette route (`api_interface.FERMEES`).
Invariants portés : INV-BASES-1 (lecture seule, confinement au vault), INV-NOTE-1.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter

from . import bases, langues, notes
from .config import Config
from .vault import Invalide, NonTrouve


def routes(config: Config, index) -> APIRouter:
    """`index` : `IndexNotes` du routeur des notes (même racine résolue que les autres routes)."""
    r = APIRouter(prefix="/api/bases")

    def table(dossier: str, filtres: str, tri: str, groupe: str) -> dict:
        # INV-NOTE-1, INV-BASES-1 : `..`, absolu, lien symbolique sortant → 404 avant toute lecture.
        rel, d = notes.chemin_sur(index.racine, dossier, config.notes.exclure, vide_ok=True)
        if not d.is_dir():
            raise NonTrouve(langues.t("serveur.api_notes.dossier_introuvable", chemin=dossier))
        try:
            liste = json.loads(filtres) if filtres else []
        except json.JSONDecodeError:
            raise Invalide(langues.t("serveur.bases.filtres_json")) from None
        if not isinstance(liste, list) or not all(isinstance(f, dict) for f in liste):
            raise Invalide(langues.t("serveur.bases.filtres_json"))
        return bases.table(d, rel, config.notes.exclure, liste, tri, groupe)

    @r.get("/table")
    async def get_table(dossier: str = "", filtres: str = "", tri: str = "", groupe: str = ""):
        return await asyncio.to_thread(table, dossier, filtres, tri, groupe)

    return r
