"""Routes des livrables : relevé (tâche ou parent), déclaration, attendus, retrait, ouverture d'un fichier du poste.

Rôle : traduire HTTP en gestes de `livrables`. Frontières : aucune logique ici ; l'auteur d'un livrable est posé
par le serveur (en-tête `X-Orch-Tache` = IA, sinon Moi) ; l'ouverture d'un fichier est réservée au poste
(`api_appareils.POSTE_SEUL_RE`) et, depuis un appareil distant, le relevé ne touche jamais un fichier hors vault.
Invariants portés : INV-LIVRABLES-1, INV-API-1.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import api_executeurs, livrables


class CorpsLivrable(BaseModel):
    cible: str = Field(max_length=livrables.LONGUEUR + 100)
    titre: str = Field("", max_length=400)
    type: str = Field("", max_length=20)


class CorpsAttendu(BaseModel):
    titre: str = Field(max_length=400)


class CorpsIndex(BaseModel):
    index: int


class CorpsOuvrir(BaseModel):
    cible: str = Field(min_length=1, max_length=livrables.LONGUEUR + 100)


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api")
    vault = moteur.vault

    def auteur(request: Request) -> str:
        return "ia" if request.headers.get("x-orch-tache") else "moi"

    def fin(ident: str, request: Request) -> dict:
        moteur.publier("arbre")
        return livrables.releve(moteur, ident, api_executeurs.distante(config, request))

    @r.get("/livrables")
    def lire(request: Request, de: str, type: str = "", q: str = ""):  # `de` : tâche ou nœud (groupe, projet, casquette)
        return livrables.releve(moteur, de, api_executeurs.distante(config, request), type, q)

    @r.post("/taches/{ident}/livrables", status_code=201)
    def declarer(ident: str, c: CorpsLivrable, request: Request):
        livrables.declarer(vault, ident, c.cible, c.titre, auteur(request), c.type)
        return fin(ident, request)

    @r.post("/taches/{ident}/livrables/attendre", status_code=201)
    def attendre(ident: str, c: CorpsAttendu, request: Request):
        livrables.annoncer(vault, ident, c.titre, auteur(request))
        return fin(ident, request)

    @r.post("/taches/{ident}/livrables/basculer")
    def basculer(ident: str, c: CorpsIndex, request: Request):
        livrables.basculer(vault, ident, c.index)
        return fin(ident, request)

    @r.post("/taches/{ident}/livrables/retirer")
    def retirer(ident: str, c: CorpsIndex, request: Request):
        livrables.retirer(vault, ident, c.index)
        return fin(ident, request)

    @r.post("/taches/{ident}/livrables/ouvrir")
    def ouvrir(ident: str, c: CorpsOuvrir):
        return livrables.ouvrir(moteur, ident, c.cible)

    return r
