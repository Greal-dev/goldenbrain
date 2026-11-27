"""Accès distant des appareils (téléphone) : garde des requêtes distantes, routes d'appairage.

Rôle : décider, pour toute requête reçue sur l'interface d'écoute distante, si elle passe ; et
servir Réglages → Appareils (liste, code QR d'appairage, révocation, journal).
Frontières : aucune persistance (`appareils.Appareils`) ; le jeton d'exécuteur reste jugé par
`api_executeurs.refus_distant` ; la boucle locale (127.0.0.1) n'est jamais concernée.
Invariants portés : INV-DISTANT-1 (rien d'autre que l'adresse d'écoute posée), INV-DISTANT-5
(appairage ouvert au poste seulement, échange limité en essais), INV-DISTANT-6 (toute requête
distante sans jeton d'appareil ni d'exécuteur valide → 401, API et SSE compris ; cookie HttpOnly,
SameSite=Strict, Secure en HTTPS), INV-DISTANT-7 (Origin vérifié ; gestes à risque interdits
ou confirmés ; gestion des appareils, installation et terminaux du poste réservés au poste),
INV-DISTANT-8 (journal des connexions distantes).
"""

from __future__ import annotations

import re
from functools import lru_cache

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from . import api_executeurs, langues, qr
from .vault import ErreurOrch

COOKIE = "gb_appareil"
COOKIE_DUREE_S = 400 * 86400      # plafond des navigateurs ; la révocation reste immédiate
CONFIRMATION = "x-orch-confirmation"
ROUTE_ECHANGE = "/api/appareils/echange"
LIBRES = {"/appairer.html", "/appairer.js", "/favicon.svg", "/style.css", "/icone-192.png", "/icone-512.png",  # page d'appairage, servie sans jeton
          "/langues.js", *(f"/langues/{c}.json" for c in ("fr", "en", "de", "es"))}  # INV-LANGUE-1 : ses textes (dictionnaires publics)
POSTE_SEUL = ("/api/appareils", "/api/installation", "/api/executeurs/jetons", "/api/executeurs/appairage",
              "/api/executeurs/reparations", "/api/lecteur/ouvrir", "/api/lecteur/dossier", "/api/lecteur/reglages", "/api/mail")  # INV-MAIL-7
POSTE_SEUL_RE = re.compile(r"/api/taches/[^/]+/(natif|console|resultat(/ouvrir)?|livrables/ouvrir)")  # terminal, fichiers et navigateur du poste
RISQUE_RE = re.compile(r"/api/(redemarrer|mise-a-jour|lots(/[^/]+/annuler)?|taches/[^/]+/(arret|vigie/arreter-enfant))")
TAILSCALE = "https://tailscale.com/download"


class Reserve(ErreurOrch):
    code = 403


class CorpsCode(BaseModel):
    nom: str = Field("", max_length=40)


class CorpsEchange(BaseModel):
    code: str = Field(min_length=1, max_length=64)


def _ip(request: Request) -> str:
    return (request.client.host if request.client else "") or "?"


def risque(methode: str, chemin: str) -> bool:
    """Arrêt, redémarrage, mise à jour, suppression (INV-DISTANT-7)."""
    return methode == "DELETE" or (methode == "POST" and bool(RISQUE_RE.fullmatch(chemin)))


def refus(registre, executeurs, config, request: Request) -> tuple[int, str] | None:
    """(code HTTP, motif) d'une requête distante refusée ; None si admise ou locale."""
    if not api_executeurs.distante(config, request):
        return None
    chemin, methode = request.url.path, request.method
    # INV-DISTANT-1 : un exécuteur se présente par son jeton ; son échange de code est le sien.
    if request.headers.get(api_executeurs.ENTETE) or chemin == api_executeurs.ROUTE_ECHANGE:
        motif = api_executeurs.refus_distant(executeurs, config, request)
        return (401, motif) if motif else None
    ip = _ip(request)
    origine = request.headers.get("origin")
    if origine and origine != f"{request.url.scheme}://{request.headers.get('host')}":
        registre.noter("refus", ip,
                       langues.t("serveur.api_appareils.origine_etrangere", origine=origine[:60]))
        return 403, langues.t("serveur.api_appareils.origine_refusee")  # INV-DISTANT-7 : anti-CSRF (le Host est gardé par INV-API-1)
    if not config.distant.appareils:
        return 401, langues.t("serveur.api_appareils.acces_desactive")
    if (methode == "GET" and chemin in LIBRES) or (methode == "POST" and chemin == ROUTE_ECHANGE):
        return None
    appareil = registre.identifier(request.cookies.get(COOKIE))
    if appareil is None:
        registre.noter("refus", ip, chemin[:80])
        return 401, langues.t("serveur.api_appareils.non_appaire")
    if chemin.startswith(POSTE_SEUL) or POSTE_SEUL_RE.fullmatch(chemin):
        return 403, langues.t("serveur.api_appareils.poste_seul")
    if risque(methode, chemin):
        if config.distant.gestes == "interdire":
            return 403, langues.t("serveur.api_appareils.geste_interdit")
        if request.headers.get(CONFIRMATION) != "1":
            return 428, langues.t("serveur.api_appareils.geste_risque")
    registre.vu(appareil, ip)
    request.state.appareil = appareil  # INV-DISTANT-6 : le flux SSE ouvert se ferme à la révocation
    return None


def revoque(request: Request) -> bool:
    a = getattr(request.state, "appareil", None)
    return bool(a and a.get("revoque"))


@lru_cache(maxsize=1)
def _qr_tailscale() -> str:
    return qr.svg(TAILSCALE)


def adresse(config) -> str:
    """Adresse de base vue par le téléphone ; vide si aucune écoute distante n'est posée."""
    hote = config.distant.nom_hote or config.executeurs.ecoute
    if not config.executeurs.ecoute:
        return ""
    return f"{'https' if config.distant.certificat else 'http'}://{hote}:{config.port}"


def routes(config, registre) -> APIRouter:
    r = APIRouter(prefix="/api/appareils")

    def au_poste(request: Request) -> None:
        # Défense en profondeur : la garde refuse déjà ces routes à distance (INV-DISTANT-7).
        if api_executeurs.distante(config, request):
            raise Reserve(langues.t("serveur.api_appareils.poste_seul"))

    @r.get("")
    async def lister(request: Request):
        au_poste(request)
        return {**registre.public(), "actif": config.distant.appareils, "gestes": config.distant.gestes,
                "ecoute": config.executeurs.ecoute, "adresse": adresse(config),
                "https": bool(config.distant.certificat), "qr_tailscale": _qr_tailscale(), "tailscale": TAILSCALE}

    @r.post("/appairage")
    async def appairer(corps: CorpsCode, request: Request):
        au_poste(request)
        if request.headers.get("x-orch-tache"):  # INV-APPAIRAGE-2 : jamais le geste d'un agent (garde B4)
            raise Reserve(langues.t("serveur.api_appareils.poste_seul"))
        base = adresse(config)
        if not base or not config.distant.appareils:
            raise ErreurOrch(langues.t("serveur.api_appareils.acces_non_ouvert"))
        c = registre.ouvrir_code(corps.nom)
        lien = f"{base}/appairer.html#{c['code']}"  # fragment : le code n'entre dans aucun journal HTTP
        return {**c, "lien": lien, "qr": qr.svg(lien)}

    @r.post("/echange")
    async def echanger(corps: CorpsEchange, request: Request, reponse: Response):
        appareil, jeton = registre.echanger(corps.code, _ip(request))
        reponse.set_cookie(COOKIE, jeton, max_age=COOKIE_DUREE_S, httponly=True, samesite="strict",
                           secure=request.url.scheme == "https", path="/")
        return {"nom": appareil["nom"]}

    @r.delete("/{ident}")
    async def revoquer(ident: str, request: Request):
        au_poste(request)
        a = registre.revoquer(ident)
        return {"revoque": a["nom"]}

    return r
