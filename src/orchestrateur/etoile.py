"""Invitation unique à mettre une étoile GitHub au dépôt, éteinte tant que celui-ci n'est pas public.

Rôle : cumuler l'usage actif déclaré par l'interface, décider si l'invitation est due, mémoriser la réponse.
Frontières : aucune donnée envoyée hors la vérification publique du dépôt (API GitHub sans jeton, une fois par jour
au plus, délai borné) ; aucun compte GitHub, aucune vérification de l'étoile ; état dans `<donnees>/etat/etoile.json`,
jamais dans le vault ni dans le dépôt. Horloge, réseau et lecture de `origin` sont injectables (tests).
Invariants portés : INV-ETOILE-1 (invitation unique et sobre : seuil d'usage, « Plus tard » = 14 jours d'usage,
« Ne plus demander » et « Mettre une étoile » définitifs ; dépôt privé, injoignable ou réglage éteint = rien,
et plus aucune écriture une fois l'invitation sans objet).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import fiches

RACINE_DEPOT = Path(__file__).resolve().parents[2]
DELAI_SONDE_S = 3.0
PAS_MAX_S = 300  # un envoi d'usage ne peut déclarer plus : borne une page laissée ouverte ou un client fautif
MOTIF_DEPOT = re.compile(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
CHOIX = ("etoile", "plus_tard", "jamais")


@dataclass
class ConfigEtoile:
    """Invitation unique à mettre une étoile GitHub (INV-ETOILE-1)."""
    actif: bool = True
    depot: str = ""  # vide = déduit de `origin` ; « proprietaire/depot » ou adresse GitHub
    seuil_h: float = 3.0  # heures d'usage actif avant l'invitation
    report_jours: int = 14  # jours d'usage après « Plus tard »
    essai: bool = False  # force l'affichage (essai à la main) ; ignore seuil et visibilité du dépôt


def depot_de(url: str) -> str | None:
    """`proprietaire/depot` d'une adresse GitHub (https ou ssh), sinon None."""
    m = MOTIF_DEPOT.search(url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def origine_git(racine: Path = RACINE_DEPOT) -> str:
    try:
        r = subprocess.run(["git", "-C", str(racine), "remote", "get-url", "origin"], capture_output=True,
                           text=True, encoding="utf-8", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def sonder_github(depot: str) -> bool:
    """Vrai si l'API publique répond sans jeton pour ce dépôt et le dit non privé ; tout échec = faux."""
    req = urllib.request.Request(f"https://api.github.com/repos/{depot}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "goldenbrain"})
    try:
        with urllib.request.urlopen(req, timeout=DELAI_SONDE_S) as r:  # noqa: S310 (adresse fixe https)
            return r.status == 200 and json.loads(r.read().decode("utf-8")).get("private") is False
    except (OSError, ValueError):
        return False


class Etoile:
    def __init__(self, config, *, maintenant=dt.datetime.now, sonder=None, origine=None):
        self.cfg = config.etoile
        self.fichier = config.donnees / "etat" / "etoile.json"
        # Résolus à l'appel (et non en défaut de signature) pour rester substituables en test.
        self.maintenant = maintenant
        self.sonder = sonder or (lambda d: sonder_github(d))
        self.origine = origine or (lambda: origine_git())
        self._depot: str | None | bool = False  # False = pas encore déduit

    def _lire(self) -> dict:
        try:
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _ecrire(self, etat: dict) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.fichier, json.dumps(etat, ensure_ascii=False))

    def depot(self) -> str | None:
        if self._depot is False:
            reglé = self.cfg.depot.strip().strip("/")
            if not reglé:
                self._depot = depot_de(self.origine())
            elif re.fullmatch(r"[\w.-]+/[\w.-]+", reglé):
                self._depot = reglé  # forme courte « proprietaire/depot »
            else:
                self._depot = depot_de(reglé)
        return self._depot

    def url(self) -> str | None:
        d = self.depot()
        return f"https://github.com/{d}" if d else None

    def _eteinte(self, etat: dict) -> bool:
        return (not self.cfg.actif or etat.get("desactive", False) or etat.get("statut") in ("fait", "jamais")
                or self.depot() is None)

    def _du(self, etat: dict) -> bool:
        if etat.get("statut") == "reporte":
            return len(etat.get("jours", [])) >= self.cfg.report_jours
        return etat.get("usage_s", 0) >= self.cfg.seuil_h * 3600

    def _public(self, etat: dict) -> bool:
        """Au plus une sonde par jour ; le résultat du jour, échec compris, est gardé."""
        jour = self.maintenant().date().isoformat()
        if etat.get("verif", {}).get("le") != jour:
            etat["verif"] = {"le": jour, "public": bool(self.sonder(self.depot()))}
            self._ecrire(etat)
        return etat["verif"]["public"]

    def etat(self) -> dict:
        """Ce que l'interface doit savoir : réglage, adresse et `afficher` (invitation due maintenant)."""
        etat = self._lire()
        reglage = self.cfg.actif and not etat.get("desactive", False)
        afficher = False
        if reglage and not self._eteinte(etat):
            afficher = self.cfg.essai or (self._du(etat) and self._public(etat))
        return {"actif": reglage, "afficher": afficher, "url": self.url(), "essai": self.cfg.essai}

    def usage(self, secondes: float) -> dict:
        """Ajoute un temps d'usage actif ; sans effet (et sans écriture) quand l'invitation n'a plus lieu d'être."""
        etat = self._lire()
        if not self._eteinte(etat) and not self._du(etat):
            if etat.get("statut") == "reporte":
                jour = self.maintenant().date().isoformat()
                if jour not in etat.setdefault("jours", []):
                    etat["jours"].append(jour)
                    self._ecrire(etat)
            else:
                etat["usage_s"] = etat.get("usage_s", 0) + max(0.0, min(float(secondes), PAS_MAX_S))
                self._ecrire(etat)
        return self.etat()

    def repondre(self, choix: str) -> dict:
        if choix not in CHOIX:
            raise ValueError(f"choix inconnu : {choix}")
        etat = self._lire()
        if choix == "plus_tard":
            etat.update(statut="reporte", jours=[])
        else:
            etat["statut"] = "fait" if choix == "etoile" else "jamais"
        self._ecrire(etat)
        return self.etat()

    def regler(self, actif: bool) -> dict:
        etat = self._lire()
        etat["desactive"] = not actif
        self._ecrire(etat)
        return self.etat()
