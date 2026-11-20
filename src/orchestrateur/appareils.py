"""Appareils distants (téléphone) : appairage par code QR, jetons d'appareil, révocation, journal.

Rôle : le poste ouvre un code d'appairage à usage unique et de courte durée (montré en code QR) ;
le téléphone l'échange contre un jeton d'appareil long, gardé dans un cookie. Seule l'empreinte du
jeton est persistée (`<donnees>/etat/appareils.json`, hors dépôt et hors vault), avec le nom de
l'appareil, sa création, sa dernière connexion et un journal borné des connexions distantes.
Frontières : aucun HTTP (routes et garde : `api_appareils`) ; aucune décision d'écoute réseau.
Invariants portés : INV-DISTANT-5 (code à usage unique, 120 s, tentatives limitées, empreinte
seule, en mémoire), INV-DISTANT-6 (jeton aléatoire long, empreinte seule, comparaison à temps
constant, révocation immédiate), INV-DISTANT-8 (journal des connexions distantes borné).
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from pathlib import Path

from . import fiches, langues
from .appairage import TropDEssais
from .executeurs import empreinte
from .vault import Invalide, NonTrouve

VALIDITE_S = 120       # le code QR vit deux minutes
ECHECS_MAX = 5         # échecs consécutifs avant verrou
VERROU_S = 60
CODES_MAX = 5
JOURNAL_MAX = 200
VU_PAS_S = 60          # la dernière connexion s'écrit au plus une fois par minute
NOM_MAX = 40


def _genre(genre: str) -> str:
    """Libellé d'une ligne du journal ; l'identifiant (`genre`) reste stocké tel quel (relu par `noter`)."""
    t = langues.t
    match genre:
        case "refus":
            return t("serveur.appareils.genre_refus")
        case "appairage refusé":
            return t("serveur.appareils.genre_appairage_refuse")
        case "appairage":
            return t("serveur.appareils.genre_appairage")
        case "connexion":
            return t("serveur.appareils.genre_connexion")
        case "révocation":
            return t("serveur.appareils.genre_revocation")
    return genre


class Appareils:
    def __init__(self, donnees: Path, horloge=time.time):
        self.fichier = Path(donnees) / "etat" / "appareils.json"
        self.horloge = horloge
        etat = self._lire()
        self.appareils: list[dict] = [a for a in etat.get("appareils") or [] if isinstance(a, dict)]
        self.journal: list[dict] = list(etat.get("journal") or [])[-JOURNAL_MAX:]
        self._codes: dict[str, tuple[str, float]] = {}   # empreinte du code -> (nom, fin)
        self._echecs = 0
        self._verrou_fin = 0.0

    # --- persistance ----------------------------------------------------------------------
    def _lire(self) -> dict:
        try:
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _sauver(self) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.fichier, json.dumps(
            {"appareils": self.appareils, "journal": self.journal}, ensure_ascii=False, indent=1))

    # --- journal (INV-DISTANT-8) ------------------------------------------------------------
    def noter(self, genre: str, ip: str, detail: str = "", sauver: bool = False) -> None:
        """Une ligne par événement ; un refus répété de la même adresse dans la minute se cumule."""
        t = self.horloge()
        d = self.journal[-1] if self.journal else None
        if d and d["genre"] == genre == "refus" and d["ip"] == ip and t - d["t"] < 60:
            d["nb"] = d.get("nb", 1) + 1
        else:
            self.journal.append({"t": t, "genre": genre, "ip": ip, "detail": detail[:120]})
            del self.journal[:-JOURNAL_MAX]
        if sauver:
            self._sauver()

    # --- appairage (INV-DISTANT-5) -----------------------------------------------------------
    def ouvrir_code(self, nom: str) -> dict:
        nom = (nom or "").strip()[:NOM_MAX] or langues.t("serveur.appareils.nom_defaut")
        maintenant = self.horloge()
        self._codes = {e: v for e, v in self._codes.items() if v[1] > maintenant}
        if len(self._codes) >= CODES_MAX:
            raise TropDEssais(langues.t("serveur.appareils.trop_de_codes"))
        code = secrets.token_urlsafe(16)
        self._codes[empreinte(code)] = (nom, maintenant + VALIDITE_S)
        return {"code": code, "nom": nom, "valide_s": VALIDITE_S}

    def echanger(self, code: str, ip: str) -> tuple[dict, str]:
        """Consomme le code et rend (appareil, jeton) ; le jeton n'est jamais gardé en clair."""
        maintenant = self.horloge()
        if maintenant < self._verrou_fin:
            raise TropDEssais(langues.t("serveur.appareils.trop_d_essais"))
        e = empreinte(code or "")
        trouve = next((k for k in self._codes if hmac.compare_digest(k, e)), None)
        valeur = self._codes.pop(trouve, None) if trouve else None
        if not valeur or valeur[1] <= maintenant:
            self._echecs += 1
            if self._echecs >= ECHECS_MAX:
                self._echecs, self._verrou_fin = 0, maintenant + VERROU_S
            self.noter("appairage refusé", ip, sauver=True)
            raise Invalide(langues.t("serveur.appareils.code_invalide"))
        self._echecs = 0
        jeton = secrets.token_urlsafe(32)
        appareil = {"id": secrets.token_hex(6), "nom": valeur[0], "empreinte": empreinte(jeton),
                    "cree": maintenant, "derniere": maintenant, "ip": ip}
        self.appareils.append(appareil)
        self.noter("appairage", ip, valeur[0], sauver=True)
        return appareil, jeton

    # --- jetons (INV-DISTANT-6) ----------------------------------------------------------------
    def identifier(self, jeton: str | None) -> dict | None:
        if not jeton:
            return None
        e = empreinte(jeton)
        trouve = None
        for a in self.appareils:
            if hmac.compare_digest(e, a.get("empreinte", "")):  # comparaison à temps constant
                trouve = a
        return trouve

    def vu(self, appareil: dict, ip: str) -> None:
        t = self.horloge()
        if t - appareil.get("derniere", 0) >= VU_PAS_S or ip != appareil.get("ip"):
            appareil["derniere"], appareil["ip"] = t, ip
            self.noter("connexion", ip, appareil["nom"], sauver=True)

    def revoquer(self, ident: str) -> dict:
        a = next((a for a in self.appareils if a["id"] == ident), None)
        if a is None:
            raise NonTrouve(langues.t("serveur.appareils.inconnu", ident=ident))
        self.appareils.remove(a)
        a["revoque"] = True  # INV-DISTANT-6 : un flux SSE encore ouvert par cet appareil se ferme
        self.noter("révocation", "poste", a["nom"], sauver=True)
        return a

    def public(self) -> dict:
        return {"appareils": [{k: a.get(k) for k in ("id", "nom", "cree", "derniere", "ip")} for a in self.appareils],
                "journal": [{**e, "genre": _genre(e["genre"])} for e in reversed(self.journal[-50:])]}
