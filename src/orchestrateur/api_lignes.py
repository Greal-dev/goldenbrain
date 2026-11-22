"""Routes des lignes de tâche, de la nature des tâches et du réglage du rangement.

Rôle : traduire HTTP en gestes de `lignes` (ajouter, cocher, retirer, promouvoir, tâche -> ligne), poser ou retirer
la nature d'une tâche (`genre`), lire et écrire `[rangement]` de `config.toml`.
Frontières : aucune logique de ligne ici (`lignes`, `fiches`) ni de nature (`rangement`) ; l'auteur d'une ligne est
posé par le serveur (en-tête `X-Orch-Tache` = IA, sinon Moi), jamais lu du corps.
Invariants portés : INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import langues, lignes, rangement
from .config_rangement import ConfigRangement
from .api_simultanes import ecrire_cles
from .vault import Invalide


class CorpsLigne(BaseModel):
    texte: str
    lien: str = ""
    fait: bool = False


class CorpsIndex(BaseModel):
    index: int


class CorpsEnLigne(BaseModel):
    vers: str | None = None


class CorpsGenre(BaseModel):
    genre: str = ""  # vide : la nature est de nouveau déduite du titre


class CorpsRangement(BaseModel):
    plafond: int
    natures_separees: bool = True


def routes(config, moteur, tache) -> APIRouter:
    r = APIRouter(prefix="/api")
    vault = moteur.vault

    def fin(ident: str, **plus) -> dict:
        moteur.publier("arbre")
        return {"lignes": vault.detail(ident)["fiche"]["lignes"], **plus}

    @r.post("/taches/{ident}/lignes", status_code=201)
    async def ajouter(ident: str, c: CorpsLigne, request: Request):
        auteur = "ia" if request.headers.get("x-orch-tache") else "moi"
        lignes.ajouter(vault, ident, c.texte, auteur, c.lien, c.fait)
        return fin(ident)

    @r.post("/taches/{ident}/lignes/basculer")
    async def basculer(ident: str, c: CorpsIndex):
        lignes.basculer(vault, ident, c.index)
        return fin(ident)

    @r.post("/taches/{ident}/lignes/retirer")
    async def retirer(ident: str, c: CorpsIndex):
        lignes.retirer(vault, ident, c.index)
        return fin(ident)

    @r.post("/taches/{ident}/lignes/promouvoir", status_code=201)
    async def promouvoir(ident: str, c: CorpsIndex):
        res = lignes.promouvoir(moteur, ident, c.index)
        return fin(ident, id=res["id"])

    @r.post("/taches/{ident}/en-ligne")
    async def en_ligne(ident: str, c: CorpsEnLigne):
        res = lignes.en_ligne(moteur, ident, c.vers)
        return {"vers": res["vers"], "lignes": res["lignes"]}

    @r.post("/taches/{ident}/genre")
    async def genre(ident: str, c: CorpsGenre):
        if c.genre and not rangement.valide(c.genre):
            raise Invalide(langues.t("serveur.rangement.nature_inconnue", genre=c.genre))
        vault.modifier(ident, {"genre": rangement.valide(c.genre) or None})
        moteur.publier("arbre")
        return tache(ident)

    @r.get("/rangement")
    async def lire():
        return {"plafond": config.rangement.plafond, "natures_separees": config.rangement.natures_separees}

    @r.put("/rangement")
    async def regler(c: CorpsRangement):
        try:
            nouveau = ConfigRangement(c.plafond, c.natures_separees)  # valide avant d'écrire
        except ValueError as e:
            raise Invalide(str(e)) from e
        if config.chemin:
            ecrire_cles(config.chemin, "rangement", {"plafond": nouveau.plafond,
                                                     "natures_separees": nouveau.natures_separees})
        config.rangement = nouveau
        return {"plafond": nouveau.plafond, "natures_separees": nouveau.natures_separees}

    return r
