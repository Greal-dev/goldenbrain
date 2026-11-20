"""Routes des exécuteurs distants : annonce, travail (long-poll), événements, vue, jetons.

Rôle : traduire HTTP en appels au registre `Executeurs` (`executeurs.py`) et dire à la garde
d'`api.py` si une requête arrivée par l'interface d'écoute distante est admise.
Frontières : aucune règle de répartition ici ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-DISTANT-1 (jeton exigé de tout ce qui arrive par l'interface distante ;
jetons créés et révoqués depuis le poste seulement ; jeton montré une fois), INV-DISTANT-3
(l'exécuteur n'atteint le vault que par `/api/`), INV-INSTALL-1 (l'assistant d'installation ne se joint jamais
par l'interface distante), INV-INSTALL-4 (la réparation d'un PC se demande au poste du chef), INV-APPAIRAGE-1 (le code s'ouvre depuis le poste ;
seul l'échange du code, limité en essais, s'admet sans jeton par l'interface distante).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import langues

ENTETE = "x-orch-jeton"
ROUTES_JETONS = "/api/executeurs/jetons"
ROUTE_APPAIRAGE = "/api/executeurs/appairage"
ROUTE_ECHANGE = ROUTE_APPAIRAGE + "/echange"
ROUTE_REPARATION = "/api/executeurs/reparations"  # INV-INSTALL-4 : accord humain, donné au poste du chef
ROUTE_TG_JETON = "/api/telegram/jeton"  # ouvre un terminal sur CE poste
ROUTE_INSTALLATION = "/api/installation"  # INV-INSTALL-1 : lance des commandes sur CE poste
ROUTE_ACCUEIL = "/api/accueil"  # INV-ACCUEIL-1 : lit des historiques locaux, poste seulement


def distante(config, request: Request) -> bool:
    """Requête reçue ailleurs que sur la boucle locale, dès qu'une écoute distante est posée.
    Défaut fermé (revue du 2026-11-18) : seul 127.0.0.1, adresse de la boucle servie (INV-API-1), est local."""
    serveur = request.scope.get("server") or ("", 0)
    return bool(config.executeurs.ecoute) and serveur[0] != "127.0.0.1"


def refus_distant(registre, config, request: Request) -> str | None:
    """Motif de refus d'une requête distante, None si admise (ou locale)."""
    if not distante(config, request):
        return None
    # INV-APPAIRAGE-1 : seul l'échange d'un code se passe de jeton (c'est lui qui le remet).
    if request.method == "POST" and request.url.path == ROUTE_ECHANGE:
        return None
    if not registre.identifier(request.headers.get(ENTETE)):
        return langues.t("serveur.api_executeurs.jeton_requis")
    # INV-DISTANT-3 : rien d'autre que l'API ; INV-DISTANT-1 : les jetons se gèrent au poste.
    if not request.url.path.startswith("/api/") or request.url.path.startswith((ROUTES_JETONS, ROUTE_APPAIRAGE, ROUTE_REPARATION, ROUTE_INSTALLATION, ROUTE_TG_JETON, ROUTE_ACCUEIL)):
        return langues.t("serveur.api_executeurs.poste_principal")
    return None


class CorpsAnnonce(BaseModel):
    harnais: list[str] = Field(default_factory=list, max_length=20)
    memoire: dict = Field(default_factory=dict)
    prerequis: list[dict] | None = Field(None, max_length=40)  # état des étapes d'installation (INV-INSTALL-4)
    reparation: dict | None = None
    places: int = Field(1, ge=1, le=32)
    tours: list[str] = Field(default_factory=list, max_length=200)
    depart: bool = False  # première annonce après le lancement de l'exécuteur


class CorpsEvenements(BaseModel):
    tour: str = Field(min_length=1, max_length=64)
    evenements: list[dict] = Field(default_factory=list, max_length=2000)
    fini: bool = False


class CorpsJeton(BaseModel):
    nom: str = Field(min_length=1, max_length=40)


class CorpsReparation(BaseModel):
    nom: str = Field(min_length=1, max_length=40)
    etape: str = Field(min_length=1, max_length=40)
    accord: str = Field(max_length=300)


class CorpsCode(BaseModel):
    code: str = Field(max_length=32)


def routes(config, moteur) -> APIRouter:
    r = APIRouter()
    reg = moteur.executeurs

    def qui(request: Request) -> str:
        if not (nom := reg.identifier(request.headers.get(ENTETE))):
            raise HTTPException(401, langues.t("serveur.api_executeurs.jeton_requis"))
        return nom

    @r.post("/api/executeurs/annonce")
    async def annonce(c: CorpsAnnonce, request: Request):
        return reg.annoncer(qui(request), c.model_dump())

    @r.get("/api/executeurs/travail")
    async def travail(request: Request, attente: float = 25):
        return {"ordres": await reg.travail(qui(request), max(0.0, attente))}

    @r.post("/api/executeurs/evenements")
    async def evenements(c: CorpsEvenements, request: Request):
        if not reg.recevoir(qui(request), c.tour, c.evenements, c.fini):
            raise HTTPException(410, langues.t("serveur.api_executeurs.tour_inconnu"))
        return {"ok": True}

    @r.get("/api/executeurs")
    async def lister():
        return {"executeurs": reg.public(), "ecoute": config.executeurs.ecoute,
                "appairages": reg.appairage.ouverts()}

    @r.post(ROUTE_APPAIRAGE)
    async def ouvrir(c: CorpsJeton):
        # INV-APPAIRAGE-1 : le code n'est rendu qu'ici, au poste du chef.
        code = reg.appairage.ouvrir(c.nom)
        moteur.publier("executeurs")
        return code

    @r.post(ROUTE_ECHANGE)
    async def echanger(c: CorpsCode):
        # INV-DISTANT-1 : jeton rendu une fois, en échange d'un code à usage unique.
        rep = reg.appairage.echanger(c.code)
        moteur.publier("executeurs")
        return rep

    @r.post(ROUTE_REPARATION)
    async def reparer(c: CorpsReparation):
        reg.reparer(c.nom, c.etape, c.accord)
        return {"demande": c.etape}

    @r.post(ROUTES_JETONS)
    async def creer(c: CorpsJeton):
        # INV-DISTANT-1 : le jeton n'est rendu qu'ici, une fois ; seule son empreinte est gardée.
        jeton = reg.creer_jeton(c.nom)
        moteur.publier("executeurs")
        return {"nom": c.nom, "jeton": jeton}

    @r.delete(ROUTES_JETONS + "/{nom}")
    async def revoquer(nom: str):
        reg.revoquer(nom)
        return {"revoque": nom}

    return r
