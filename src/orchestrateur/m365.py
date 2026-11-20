"""Connecteur Microsoft 365 Copilot : la connaissance d'entreprise de l'utilisateur, à la demande des agents.

Rôle : `orch m365 connecter` (code d'appareil Entra, jeton délégué), `orch m365 demander` (réponse de
Copilot avec citations, Work IQ Chat API), `orch m365 contexte` (extraits bruts, Retrieval API, pour que
l'agent raisonne lui-même). Appels REST par urllib : aucune dépendance (pas de `microsoft-agents-m365copilot`).
Frontières : n'est pas un harnais ; n'écrit jamais dans Microsoft 365 ; ne passe pas par le serveur
GoldenBrain ; ne touche ni au vault ni au moteur.
Invariants portés : INV-M365-1 (lecture seule : trois appels, ouvrir une conversation, y poser une
question, extraire), INV-M365-2 (jeton hors du dépôt, chiffré DPAPI sous Windows, jamais affiché ni
journalisé), INV-M365-3 (désactivé par défaut : rien ne part sans `[m365] actif = true`).
"""

from __future__ import annotations

import json
import os
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import RACINE_DEPOT, chemin_par_defaut

SOURCES = ("sharePoint", "oneDriveBusiness", "externalItem")
LONGUEUR_MAX = 1500  # Retrieval API : `queryString` borné à 1 500 caractères


class ErreurM365(Exception):
    pass


@dataclass
class ConfigM365:
    """`[m365]` de `config.toml`. Les URL sont réglables pour la Graph beta (`chat_url =
    "https://graph.microsoft.com/beta/copilot"`, même contrat) et pour les tests (serveur factice)."""
    actif: bool = False
    client_id: str = ""            # application Entra de l'utilisateur (client public)
    tenant: str = "organizations"
    jeton: str = "~/.goldenbrain/m365-jeton.bin"
    fuseau: str = "Europe/Paris"
    web: bool = False              # Work IQ ancre aussi sur le web par défaut : on s'en tient à l'entreprise
    source: str = "sharePoint"
    login_url: str = "https://login.microsoftonline.com"
    chat_url: str = "https://workiq.svc.cloud.microsoft/rest"
    chat_portee: str = "api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask"
    retrieval_url: str = "https://graph.microsoft.com/v1.0/copilot/retrieval"
    retrieval_portees: list[str] = field(default_factory=lambda: [
        "https://graph.microsoft.com/Files.Read.All", "https://graph.microsoft.com/Sites.Read.All"])

    def __post_init__(self):
        if self.source not in SOURCES:
            raise ValueError(f"m365.source inconnue : {self.source}")


# --- Jeton (INV-M365-2) ---------------------------------------------------------------------------

def _chemin_jeton(conf: ConfigM365) -> Path:
    chemin = Path(conf.jeton).expanduser().resolve()
    if chemin.is_relative_to(RACINE_DEPOT):  # INV-M365-2 : un jeton ne se versionne jamais par mégarde
        raise ErreurM365("m365.jeton : choisissez un chemin hors du dépôt")
    return chemin


def _dpapi(donnees: bytes, chiffrer: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    entree = Blob(len(donnees), ctypes.cast(ctypes.c_char_p(donnees), ctypes.POINTER(ctypes.c_char)))
    sortie = Blob()
    crypt = ctypes.windll.crypt32
    fonction = crypt.CryptProtectData if chiffrer else crypt.CryptUnprotectData
    if not fonction(ctypes.byref(entree), None, None, None, None, 0, ctypes.byref(sortie)):
        raise ErreurM365("jeton illisible pour ce compte Windows : orch m365 connecter")
    try:
        return ctypes.string_at(sortie.pbData, sortie.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(sortie.pbData)


def ecrire_jeton(conf: ConfigM365, rafraichissement: str) -> None:
    chemin = _chemin_jeton(conf)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    brut = rafraichissement.encode("utf-8")
    # ponytail: hors Windows, fichier en clair restreint au propriétaire ; trousseau du système au besoin
    chemin.write_bytes(_dpapi(brut, True) if sys.platform == "win32" else brut)
    if sys.platform != "win32":
        chemin.chmod(0o600)


def lire_jeton(conf: ConfigM365) -> str:
    chemin = _chemin_jeton(conf)
    if not chemin.is_file():
        raise ErreurM365("pas encore connecté : orch m365 connecter")
    brut = chemin.read_bytes()
    return (_dpapi(brut, False) if sys.platform == "win32" else brut).decode("utf-8")


# --- HTTP -----------------------------------------------------------------------------------------

def _poster(url: str, corps: dict, jeton: str | None = None, formulaire: bool = False) -> dict:
    if formulaire:
        donnees, type_ = urllib.parse.urlencode(corps).encode(), "application/x-www-form-urlencoded"
    else:
        donnees, type_ = json.dumps(corps).encode("utf-8"), "application/json"
    entetes = {"Content-Type": type_, **({"Authorization": f"Bearer {jeton}"} if jeton else {})}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=donnees, headers=entetes,
                                                           method="POST"), timeout=120) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
        except ValueError:
            detail = {}
        if formulaire:  # erreur OAuth : rendue à l'appelant, qui la qualifie (code d'appareil en attente…)
            return {"error": detail.get("error", f"http_{e.code}"),
                    "error_description": detail.get("error_description", "")}
        message = (detail.get("error") or {}).get("message") if isinstance(detail.get("error"), dict) \
            else detail.get("error")
        raise ErreurM365(f"Microsoft 365 a répondu {e.code} : {message or e.reason}") from None
    except urllib.error.URLError as e:
        raise ErreurM365(f"Microsoft 365 injoignable : {e.reason}") from None


def _jeton_oauth(conf: ConfigM365) -> str:
    return f"{conf.login_url.rstrip('/')}/{conf.tenant}/oauth2/v2.0/token"


def _preparer(conf: ConfigM365) -> None:
    if not conf.actif:  # INV-M365-3
        raise ErreurM365("connecteur Microsoft 365 désactivé : [m365] actif = true dans config.toml")
    if not conf.client_id:
        raise ErreurM365("[m365] client_id manquant : identifiant de l'application Entra")


def acces(conf: ConfigM365, portees: str) -> str:
    """Jeton d'accès pour une ressource, tiré du jeton de rafraîchissement (valable pour Graph comme
    pour Work IQ : une seule connexion) ; le jeton renouvelé remplace l'ancien."""
    r = _poster(_jeton_oauth(conf), {"client_id": conf.client_id, "grant_type": "refresh_token",
                                     "refresh_token": lire_jeton(conf),
                                     "scope": f"{portees} offline_access"}, formulaire=True)
    if "access_token" not in r:
        raise ErreurM365(f"connexion refusée ({r.get('error')}) : orch m365 connecter, ou consentement "
                         f"de l'administrateur à demander")
    if r.get("refresh_token"):
        ecrire_jeton(conf, r["refresh_token"])
    return r["access_token"]


def connecter(conf: ConfigM365, afficher=print, attendre=time.sleep) -> None:
    """Code d'appareil : l'utilisateur s'identifie dans son navigateur ; aucun secret d'application."""
    _preparer(conf)
    portees = " ".join(conf.retrieval_portees) + " offline_access"
    base = f"{conf.login_url.rstrip('/')}/{conf.tenant}/oauth2/v2.0"
    d = _poster(f"{base}/devicecode", {"client_id": conf.client_id, "scope": portees}, formulaire=True)
    if "device_code" not in d:
        raise ErreurM365(f"code d'appareil refusé : {d.get('error')} {d.get('error_description', '')[:200]}")
    afficher(d.get("message") or f"Ouvrez {d['verification_uri']} et saisissez {d['user_code']}")
    intervalle, fin = int(d.get("interval", 5)), time.monotonic() + int(d.get("expires_in", 900))
    while time.monotonic() < fin:
        attendre(intervalle)
        r = _poster(f"{base}/token", {"client_id": conf.client_id, "device_code": d["device_code"],
                                      "grant_type": "urn:ietf:params:oauth:grant-type:device_code"},
                    formulaire=True)
        if "refresh_token" in r:
            ecrire_jeton(conf, r["refresh_token"])
            afficher("connecté ; jeton enregistré hors du dépôt")
            return
        if r.get("error") == "slow_down":
            intervalle += 5
        elif r.get("error") != "authorization_pending":
            raise ErreurM365(f"connexion refusée : {r.get('error')}")
    raise ErreurM365("code d'appareil expiré : relancez orch m365 connecter")


# --- Lecture (INV-M365-1) -------------------------------------------------------------------------

def _question(question: str) -> str:
    question = question.strip()
    if not question:
        raise ErreurM365("question vide")
    if len(question) > LONGUEUR_MAX:
        raise ErreurM365(f"question trop longue (plus de {LONGUEUR_MAX} caractères)")
    return question


def demander(conf: ConfigM365, question: str) -> dict:
    """Réponse synthétisée par Copilot : {texte, citations: [{titre, url}]}."""
    _preparer(conf)
    question = _question(question)
    jeton = acces(conf, conf.chat_portee)
    base = conf.chat_url.rstrip("/")
    conversation = _poster(f"{base}/conversations", {}, jeton)["id"]
    r = _poster(f"{base}/conversations/{urllib.parse.quote(conversation, safe='')}/chat", {
        "message": {"text": question}, "locationHint": {"timeZone": conf.fuseau},
        "contextualResources": {"webContext": {"isWebEnabled": conf.web}}}, jeton)
    messages = r.get("messages") or []
    if len(messages) < 2:
        raise ErreurM365("Copilot n'a pas répondu")
    reponse = messages[-1]  # le premier message est l'écho de la question
    citations = [{"titre": a.get("providerDisplayName") or "", "url": a.get("seeMoreWebUrl") or ""}
                 for a in reponse.get("attributions") or [] if a.get("attributionType") == "citation"]
    return {"texte": reponse.get("text") or "", "citations": citations}


def contexte(conf: ConfigM365, question: str, source: str = "", nombre: int = 10) -> list[dict]:
    """Extraits pertinents des contenus de l'utilisateur : [{titre, auteur, url, extraits}]."""
    _preparer(conf)
    source = source or conf.source
    if source not in SOURCES:
        raise ErreurM365(f"source inconnue : {source} ({', '.join(SOURCES)})")
    corps = {"queryString": _question(question), "dataSource": source,
             "maximumNumberOfResults": max(1, min(nombre, 25)), "resourceMetadata": ["title", "author"]}
    r = _poster(conf.retrieval_url, corps, acces(conf, " ".join(conf.retrieval_portees)))
    return [{"titre": (h.get("resourceMetadata") or {}).get("title") or "",
             "auteur": (h.get("resourceMetadata") or {}).get("author") or "",
             "url": h.get("webUrl") or "",
             "extraits": [x.get("text") or "" for x in h.get("extracts") or []]}
            for h in r.get("retrievalHits") or []]


def rendre_reponse(r: dict) -> list[str]:
    lignes = [r["texte"] or "(réponse vide)"]
    if r["citations"]:
        lignes += ["", "Sources :"] + [f"[{i}] {c['titre']} — {c['url']}"
                                      for i, c in enumerate(r["citations"], 1)]
    return lignes


def rendre_contexte(hits: list[dict]) -> list[str]:
    lignes = []
    for i, h in enumerate(hits, 1):
        lignes.append(f"[{i}] {h['titre'] or h['url']}" + (f" ({h['auteur']})" if h["auteur"] else "")
                      + f" — {h['url']}")
        lignes += [f"    {x.strip()}" for x in h["extraits"] if x.strip()]
    return lignes or ["(aucun extrait)"]


def charger(chemin: str | os.PathLike | None = None) -> ConfigM365:
    """Section `[m365]` seule : le connecteur n'a pas besoin du reste de la configuration."""
    chemin = Path(chemin) if chemin else chemin_par_defaut()
    brut = tomllib.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else {}
    return ConfigM365(**brut.get("m365", {}))
