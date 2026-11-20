"""Pastille « intégration en retard » : une tâche terminée dont la branche gb/* n'est pas dans la branche d'intégration.

Rôle : repérer, dans la fiche d'une tâche `fait`/`cloture`, les branches `gb/*` citées ; dire par lecture
git seule si la pointe est contenue dans la branche d'intégration et depuis quand elle attend (date de
sa dernière validation) ; marquer en retard celles qui attendent plus de `retard_h` heures.
Frontières : `git` en lecture (rev-parse, merge-base --is-ancestor, log -1), par liste d'arguments, sans
shell ; aucune écriture dans le dépôt ni le vault. Section `[integration]` de `config.toml`, lue ici
(pas de champ dans `Config`). Le calcul tourne dans un fil d'arrière-plan : `annoter` ne lit que le
cache et ne bloque jamais l'arbre ; branche ou dépôt introuvable = aucune pastille.
Invariants portés : INV-INTEG-1.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import langues
from .config import RACINE_DEPOT

STATUTS = ("fait", "cloture")
CHAMPS_BRANCHE = ("fait", "resultat")
BRANCHE = re.compile(r"(?<![\w/.-])gb/[A-Za-z0-9_][A-Za-z0-9_./-]*")
SUR = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")
DELAI_GIT_S = 10
ATTENTE_PREMIERE_S = 0.5  # plafond de l'attente, jamais plus : l'arbre ne dépend pas de git


@dataclass
class ConfigIntegration:
    branche: str = "gb/integration"  # branche où doivent finir les branches gb/* terminées
    retard_h: float = 2.0  # attente tolérée avant la pastille
    cache_s: float = 60.0  # durée de validité d'une lecture git
    depot: str = ""  # dépôt git à lire ; vide = le dépôt de GoldenBrain

    def __post_init__(self) -> None:
        if not SUR.fullmatch(str(self.branche)) or ".." in str(self.branche):
            raise ValueError(langues.t("serveur.integration.branche"))
        if not 0 < float(self.retard_h) <= 24 * 365:
            raise ValueError(langues.t("serveur.integration.retard_h"))
        if not float(self.cache_s) >= 0:
            raise ValueError(langues.t("serveur.integration.cache_s"))


def charger(chemin: Path | None) -> ConfigIntegration:
    """`[integration]` de `config.toml` ; absente ou illisible = défauts."""
    try:
        brut = tomllib.loads(Path(chemin).read_text(encoding="utf-8")).get("integration", {})
        return ConfigIntegration(**brut)
    except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return ConfigIntegration()


def branches_citees(fiche: dict, integration: str = "") -> list[str]:
    """Branches `gb/*` citées par les champs « fait » et « résultat » de la fiche, sans doublon."""
    texte = " ".join(str(fiche.get(c) or "") for c in CHAMPS_BRANCHE)
    vues: list[str] = []
    for m in BRANCHE.finditer(texte):
        b = m.group(0).rstrip(".,;:/")
        if b != integration and b not in vues and SUR.fullmatch(b):
            vues.append(b)
    return vues


def _git(depot: Path, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=DELAI_GIT_S,
                           env={"GIT_TERMINAL_PROMPT": "0", **os.environ})
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout.strip()


def _refs(depot: Path, branche: str) -> list[str]:
    """Refs existantes de la branche : la copie distante d'abord (l'état poussé fait foi), puis la locale."""
    return [ref for ref in (f"refs/remotes/origin/{branche}", f"refs/heads/{branche}")
            if _git(depot, "rev-parse", "--verify", "--quiet", ref + "^{commit}")[0] == 0]


def lire(depot: Path, branche: str, integration: str) -> tuple[bool, float] | None:
    """(contenue dans l'intégration ?, date epoch de la pointe) ; None si la branche ou l'intégration manque."""
    pointes, cibles = _refs(depot, branche), _refs(depot, integration)
    if not pointes or not cibles:
        return None
    code, date = _git(depot, "log", "-1", "--format=%ct", pointes[0])
    if code or not date.isdigit():
        return None
    contenue = any(_git(depot, "merge-base", "--is-ancestor", pointes[0], c)[0] == 0 for c in cibles)
    return contenue, float(date)


class Suivi:
    """Cache des lectures git, rafraîchi en arrière-plan (INV-INTEG-1)."""

    def __init__(self, config: ConfigIntegration, depot: Path | None = None, horloge=time.time):
        self.config = config
        self._depot = depot
        self._horloge = horloge
        self._cache: dict[tuple[str, str], tuple[float, tuple[bool, float] | None]] = {}
        self._verrou = threading.Lock()
        self._fil: threading.Thread | None = None
        self._demande: set[str] = set()
        self._attendues: set[tuple[str, str]] = set()  # clés demandées, pas encore lues une première fois

    @property
    def depot(self) -> Path:
        return Path(self.config.depot).expanduser() if self.config.depot else (self._depot or RACINE_DEPOT)

    def _rafraichir(self) -> None:
        while True:
            with self._verrou:
                if not self._demande:
                    self._fil = None
                    return
                branche, integration = self._demande.pop(), self.config.branche
            resultat = lire(self.depot, branche, integration)
            with self._verrou:
                self._cache[(branche, integration)] = (self._horloge(), resultat)

    def attendre(self, delai: float = 30) -> None:
        """Attend au plus `delai` s la fin du calcul en cours."""
        with self._verrou:
            fil = self._fil
        if fil:
            fil.join(delai)

    def etat(self, branche: str) -> dict | None:
        """`{branche, heures}` si la branche attend (non contenue) depuis plus de `retard_h` heures, sinon None.
        Ne lit que le cache : une valeur absente ou périmée lance un calcul en arrière-plan."""
        cle = (branche, self.config.branche)
        with self._verrou:
            vu = self._cache.get(cle)
            if vu is None or self._horloge() - vu[0] > self.config.cache_s:
                self._demande.add(branche)
                self._attendues.add(cle)
                if self._fil is None:
                    self._fil = threading.Thread(target=self._rafraichir, daemon=True, name="integration")
                    self._fil.start()
        if vu is None or vu[1] is None or vu[1][0]:
            return None
        heures = (self._horloge() - vu[1][1]) / 3600
        return {"branche": branche, "heures": int(heures)} if heures > self.config.retard_h else None

    def annoter(self, noeuds: list[dict], taches: dict) -> None:
        """Ajoute `integration_retard` aux nœuds-tâches terminés dont une branche cité est en retard."""
        self._poser(noeuds, taches)
        with self._verrou:
            premier = self._fil is not None and any(c not in self._cache for c in self._attendues)
        if premier:  # première lecture : attente bornée, pour que la pastille soit là dès le premier affichage
            self.attendre(ATTENTE_PREMIERE_S)
            self._poser(noeuds, taches)

    def _poser(self, noeuds: list[dict], taches: dict) -> None:
        for n in noeuds:
            if n.get("type") == "tache" and n.get("statut") in STATUTS and n["id"] in taches:
                retards = [e for b in branches_citees(taches[n["id"]].fiche, self.config.branche)
                           if (e := self.etat(b))]
                if retards:
                    n["integration_retard"] = max(retards, key=lambda e: e["heures"])
            self._poser(n.get("enfants") or [], taches)

    def public(self) -> dict:
        c = self.config
        return {"branche": c.branche, "retard_h": c.retard_h, "cache_s": c.cache_s}
