"""Routes du temps : vue « Aujourd'hui » et pose d'échéance / priorité d'une tâche.

Rôle : corps de `POST /taches` (qui porte aussi le temps, hors d'`api.py`, plafonné à 500 lignes) ;
traduire HTTP en appels à `temps.py` et `Vault.poser_temps`.
Frontières : aucune logique de date ici ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-TEMPS-1 (écriture stricte via `temps.valider`), INV-VAULT-1 (par `Vault`).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import temps
from .vault import Vault


class CorpsTache(BaseModel):
    titre: str
    description: str = ""
    de: str | None = None  # tâche de l'agent qui crée : la description devient obligatoire
    conteneur: str | None = None
    parent: str | None = None
    lancer: bool = False
    mission: str = ""  # consigne du premier tour quand `lancer` (sinon la description)
    harnais: str | None = None
    modele: str | None = None
    echeance: str | None = None
    priorite: str | None = None
    forcer: bool = False  # INV-RAPPROCHEMENT-1 : créer malgré une tâche proche ; interface : aussi malgré un parent plein
    hors_rangement: bool = False  # INV-PLAFOND-1 : pour un agent, la seule dérogation au plafond / à la nature
    genre: str | None = None  # nature de la tâche (INV-NATURE-1) ; absente : déduite du titre
    etiquettes: list[str] = []  # INV-ETIQUETTE-1 : posées à la création (un agent : existantes seulement)
    groupe: str | None = None  # titre d'un regroupement à créer sous le parent pour y ranger la tâche (INV-PLAFOND-1)


class CorpsTemps(BaseModel):
    # Absent = inchangé ; chaîne vide = retire la clé.
    echeance: str | None = None
    priorite: str | None = None


def routes(vault: Vault, publier, tache, humain=None) -> APIRouter:  # humain : ids en « Action humaine nécessaire » (INV-MAIN-4)
    r = APIRouter(prefix="/api")

    @r.get("/aujourdhui")
    async def aujourdhui():
        return temps.aujourdhui(vault, humain() if humain else None)

    @r.post("/taches/{ident}/temps")
    async def poser(ident: str, c: CorpsTemps):
        temps.poser(vault, ident, c.echeance, c.priorite)
        publier("arbre")
        return tache(ident)

    return r
