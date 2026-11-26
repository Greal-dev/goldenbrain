"""Routes `/api/lecteur` : renseigner, lire et servir un fichier ; l'ouvrir dans l'application du poste ; réglages.

Rôle : traduire HTTP en gestes de `lecteur`. Frontières : aucune décision ici ; lecture ouverte à l'appareil distant
(vault et livrables seulement, jugé par `lecteur.resoudre`) ; ouverture d'une application, affichage du dossier et
réglages réservés au poste (`api_appareils.POSTE_SEUL`) ET refusés à tout agent (en-tête de tâche ou jeton d'exécuteur).
Invariants portés : INV-LECTEUR-1, INV-API-1.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import api_executeurs, langues, lecteur
from .api_appareils import Reserve
from .api_simultanes import ecrire_cles
from .config_lecteur import ConfigLecteur
from .vault import Invalide

CHEMIN = "/api/lecteur/brut"


class CorpsChemin(BaseModel):
    chemin: str = Field(min_length=1, max_length=2000)


class CorpsReglage(BaseModel):
    dossiers: list[str] = Field(default_factory=list, max_length=200)
    lecteur: list[str] = Field(default_factory=list, max_length=200)
    application: list[str] = Field(default_factory=list, max_length=200)


def entetes(chemin: str, csp: str | None) -> dict | None:
    """En-têtes du fichier brut : la politique posée par `lecteur.brut` (isolement) remplace celle de l'interface."""
    if chemin != CHEMIN or not csp:
        return None
    return {"X-Frame-Options": "SAMEORIGIN", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Content-Security-Policy": csp}


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api/lecteur")

    def distante(request: Request) -> bool:
        return api_executeurs.distante(config, request)

    def geste_humain(request: Request) -> None:
        # INV-LECTEUR-1 : l'application du poste ne s'ouvre ni à distance ni sur ordre d'un agent (défense en profondeur).
        if distante(request) or request.headers.get("x-orch-tache") or request.headers.get(api_executeurs.ENTETE):
            raise Reserve(langues.t("serveur.lecteur.poste_seul"))

    @r.get("/info")
    def lire_info(request: Request, chemin: str):
        return lecteur.info(moteur, chemin, distante(request))

    @r.get("/page")
    def lire_page(request: Request, chemin: str, debut: int = 0):
        return lecteur.lire(moteur, chemin, distante(request), debut)

    @r.get("/brut")
    def lire_brut(request: Request, chemin: str, externe: bool = False):
        p, type_, tetes = lecteur.brut(moteur, chemin, distante(request), externe)
        return FileResponse(p, media_type=type_, headers=tetes, content_disposition_type="inline")

    @r.post("/ouvrir")
    def ouvrir(c: CorpsChemin, request: Request):
        geste_humain(request)
        return lecteur.ouvrir_application(moteur, c.chemin)

    @r.post("/dossier")
    def dossier(c: CorpsChemin, request: Request):
        geste_humain(request)
        return lecteur.afficher_dossier(moteur, c.chemin)

    def etat() -> dict:
        cfg = config.lecteur
        return {"dossiers": cfg.dossiers, "lecteur": cfg.lecteur, "application": cfg.application, "registre": lecteur.registre(cfg)}

    @r.get("/reglages")
    def lire_reglages():
        return etat()

    @r.put("/reglages")
    def regler(c: CorpsReglage, request: Request):
        geste_humain(request)
        try:
            nouveau = ConfigLecteur(c.dossiers, c.lecteur, c.application)  # valide avant d'écrire
        except ValueError as e:
            raise Invalide(str(e)) from e
        if config.chemin:
            ecrire_cles(config.chemin, "lecteur", {"dossiers": nouveau.dossiers, "lecteur": nouveau.lecteur, "application": nouveau.application})
        config.lecteur = nouveau
        lecteur.vider_cache()
        return etat()

    return r
