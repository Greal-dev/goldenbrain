"""Curseur Performance ↔ Économie : routes `/api/economie` (lire, régler) et moteur prévu d'une tâche.

Rôle : exposer la position du curseur, sa traduction effective par harnais (mode intelligent), les
fenêtres de quota et la consommation sur 7 jours ; persister `[economie] position, famille_defaut` dans
`config.toml` ; dire, pour une tâche, le moteur que le prochain tour prendrait et la bascule proposée.
Frontières : aucune décision (module `economie`) ; aucune écriture vault ; accepter une bascule passe par
la route existante `POST /taches/{id}/moteur` (nouvelle conversation dans l'autre harnais).
Invariants portés : INV-ECO-1 (la lecture du moteur prévu n'écrit rien et ne change aucun harnais).
"""

from __future__ import annotations

from dataclasses import asdict, replace

from fastapi import APIRouter
from pydantic import BaseModel

from .api_simultanes import ecrire_cles
from .vault import Invalide


class CorpsEconomie(BaseModel):
    position: str | None = None
    famille_defaut: str | None = None


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/economie")
    async def lire():
        return moteur.economie.public()

    @r.put("/economie")
    async def regler(c: CorpsEconomie):
        champs = {k: v for k, v in c.model_dump().items() if v is not None}
        try:
            cible = replace(config.economie, **champs)  # __post_init__ valide position et famille
        except (TypeError, ValueError) as e:
            raise Invalide(str(e)) from e
        if config.chemin and champs:
            ecrire_cles(config.chemin, "economie", champs)
        config.economie = cible
        moteur.economie.etats.clear()  # nouvelle position : l'hystérésis repart de l'état neutre
        moteur.publier("economie")
        return moteur.economie.public()

    @r.get("/taches/{ident}/economie")
    async def prevu(ident: str):
        return asdict(moteur.economie.decider(moteur.vault.tache(ident), ident in moteur.a_deriver))

    return r
