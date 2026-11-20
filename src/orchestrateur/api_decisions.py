"""Routes de la page « Décisions » : liste des décisions en attente et gestes par lot.

Rôle : traduire HTTP en appels à `decisions` (lecture des journaux hors de la boucle d'événements).
Les gestes à l'unité réutilisent les routes existantes (valider, renvoyer, messages, temps,
propositions) : aucun second chemin d'écriture.
Frontières : aucune logique de décision ici.
Invariants portés : INV-DECISIONS-1 (lots exécutés geste par geste, un refus n'arrête pas le lot).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from . import decisions, evitable, scan


class CorpsValidations(BaseModel):
    taches: list[str]


class CorpsDocumenter(BaseModel):
    tache: str


class CorpsFermetures(BaseModel):
    numeros: list[int]


class CorpsEvitable(BaseModel):
    actif: bool | None = None
    seuil: int | None = None


class ChoixAgent(BaseModel):
    id: str
    action: str
    tache: str = ""


class CorpsAgents(BaseModel):
    choix: list[ChoixAgent]


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api/decisions")

    @r.get("")
    async def lister():
        return await asyncio.to_thread(decisions.rassembler, moteur)

    @r.get("/evitable")
    async def evitable_lire():
        return evitable.lire(moteur.config.donnees)

    @r.put("/evitable")
    async def evitable_regler(c: CorpsEvitable):
        # INV-EVITABLE-1 : réglage de la pastille, sans effet sur le vault.
        return evitable.regler(moteur.config.donnees, c.actif, c.seuil)

    @r.post("/valider")
    async def valider(c: CorpsValidations):
        res = decisions.valider_lot(moteur, c.taches)
        moteur.publier("arbre")
        return res

    @r.post("/documenter", status_code=202)
    async def documenter(c: CorpsDocumenter):
        return {"etat_execution": decisions.documenter(moteur, c.tache)}

    @r.post("/fermer")
    async def fermer(c: CorpsFermetures):
        return decisions.fermer_lot(moteur, c.numeros)

    @r.post("/scan")
    async def scanner():
        # INV-SCAN-1 : le scan dépose des propositions en attente ; rien n'est appliqué ici.
        return await asyncio.to_thread(scan.scanner, moteur)

    @r.post("/agents")
    async def agents(c: CorpsAgents):
        # INV-AGENTSCC-1 : rattacher, créer ou ignorer, sur le geste de l'utilisateur, un par un.
        return await asyncio.to_thread(moteur.agents_cc.appliquer, [x.model_dump() for x in c.choix])

    return r
