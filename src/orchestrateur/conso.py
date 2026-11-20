"""Mesure de la consommation : jetons et coût par tour, fenêtres de quota par harnais.

Rôle : registre d'adaptateurs. `JETONS[harnais](brut)` lit l'événement de fin d'un tour (Claude Code :
`result` du flux stream-json ; Codex : `turn.completed`) ; `QUOTAS[source](conf, harnais)` lit les
fenêtres de quota (Codex : `rate_limits` de ses journaux de session ; `fichier` : JSON au format des
données de la ligne d'état de Claude Code, `rate_limits.five_hour` / `seven_day`). Cumul par jour et par
harnais dans `<donnees>/etat/conso.json` (31 jours).
Frontières : aucune décision (module `economie`) ; aucune écriture vault ; aucune donnée personnelle
dans le code (les chemins viennent de la configuration ou du dossier personnel).
Invariants portés : INV-ECO-2 (une fenêtre illisible, périmée ou trop jeune ne produit aucun rythme :
jamais de valeur inventée).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from . import fiches

log = logging.getLogger(__name__)
DUREES = {"five_hour": 5 * 3600, "seven_day": 7 * 86400}
NOMS = {5 * 3600: "5 h", 7 * 86400: "hebdomadaire"}
CACHE_S = 60
QUEUE_OCTETS = 400_000  # fin du journal Codex relue : les limites y sont consignées à chaque tour


@dataclass
class Fenetre:
    nom: str             # « 5 h », « hebdomadaire »
    part: float          # part consommée, 0..1
    duree_s: float
    renouvellement: float  # instant du renouvellement (epoch)

    def ecoule(self, maintenant: float) -> float:
        """Part du temps de la fenêtre déjà écoulée, 0..1."""
        return min(1.0, max(0.0, 1 - (self.renouvellement - maintenant) / self.duree_s))

    def rythme(self, maintenant: float) -> float | None:
        """Indice P = part consommée / part du temps écoulé ; None si la fenêtre est trop jeune
        (moins de 5 % écoulés : un seul tour fausserait l'indice) ou déjà renouvelée (INV-ECO-2)."""
        e = self.ecoule(maintenant)
        if self.renouvellement <= maintenant or e < 0.05:
            return None
        return self.part / e


# --- jetons et coût par tour ----------------------------------------------------------------
def _claude(brut: dict) -> dict | None:
    if brut.get("type") != "result" or not isinstance(u := brut.get("usage"), dict):
        return None
    entree = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                               "cache_read_input_tokens"))
    return {"entree": entree, "sortie": int(u.get("output_tokens") or 0),
            "cout": float(brut.get("total_cost_usd") or 0)}


def _codex(brut: dict) -> dict | None:
    if brut.get("type") != "turn.completed" or not isinstance(u := brut.get("usage"), dict):
        return None
    return {"entree": int(u.get("input_tokens") or 0), "sortie": int(u.get("output_tokens") or 0),
            "cout": 0.0}  # Codex ne chiffre pas le coût d'un tour


# Antigravity, OpenCode et Copilot (aucun champ de jetons ni de quota documenté) : format de fin non vérifié ; aucune mesure plutôt qu'une mesure fausse.
JETONS = {"claude": _claude, "codex": _codex}


# --- fenêtres de quota -----------------------------------------------------------------------
def _codex_quotas(conf: dict, harn: dict) -> list[Fenetre]:
    racine = Path(conf.get("chemin") or harn.get("transcripts") or Path.home() / ".codex" / "sessions")
    journaux = sorted(racine.glob("*/*/*/*.jsonl"), reverse=True)[:5] if racine.is_dir() else []
    for j in journaux:  # le plus récent qui porte des limites
        with open(j, "rb") as f:
            f.seek(max(0, j.stat().st_size - QUEUE_OCTETS))
            lignes = f.read().decode("utf-8", "replace").splitlines()
        for ligne in reversed(lignes):
            if '"rate_limits"' not in ligne:
                continue
            try:
                rl = (json.loads(ligne).get("payload") or {}).get("rate_limits") or {}
            except ValueError:
                continue
            return [Fenetre(NOMS.get(int(w["window_minutes"]) * 60, f"{w['window_minutes']} min"),
                            float(w["used_percent"]) / 100, int(w["window_minutes"]) * 60,
                            float(w["resets_at"]))
                    for w in (rl.get("primary"), rl.get("secondary")) if isinstance(w, dict)
                    and {"used_percent", "window_minutes", "resets_at"} <= w.keys()]
    return []


def _fichier_quotas(conf: dict, harn: dict) -> list[Fenetre]:
    if not (chemin := conf.get("chemin")):
        return []
    donnees = json.loads(Path(chemin).expanduser().read_text(encoding="utf-8"))
    rl = donnees.get("rate_limits", donnees)
    return [Fenetre(NOMS[d], float(w["used_percentage"]) / 100, d, float(w["resets_at"]))
            for cle, d in DUREES.items() if isinstance(w := rl.get(cle), dict)
            and {"used_percentage", "resets_at"} <= w.keys()]


QUOTAS = {"codex": _codex_quotas, "fichier": _fichier_quotas}
SOURCE_DEFAUT = {"codex": "codex"}  # Claude Code n'expose ses quotas que dans sa ligne d'état


class Conso:
    def __init__(self, config):
        self.config = config
        self.fichier = config.donnees / "etat" / "conso.json"
        self._cache: dict[str, tuple[float, list[Fenetre]]] = {}

    def _lire(self) -> dict:
        try:
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def mesurer(self, harnais: str, brut: dict | None) -> None:
        """Ajoute au cumul du jour les jetons et le coût d'un tour, si le harnais les donne."""
        lecteur = JETONS.get(harnais)
        if not (brut and lecteur and (m := lecteur(brut))):
            return
        donnees = self._lire()
        jour = donnees.setdefault(dt.date.today().isoformat(), {}).setdefault(harnais, {})
        jour["tours"] = jour.get("tours", 0) + 1
        for k, v in m.items():
            jour[k] = round(jour.get(k, 0) + v, 6)
        garde = sorted(donnees)[-31:]
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier, json.dumps({k: donnees[k] for k in garde}, ensure_ascii=False))
        except OSError as e:
            log.warning("consommation non enregistrée : %s", e)

    def periode(self, jours: int = 7) -> dict[str, dict]:
        """Cumul par harnais sur les `jours` derniers jours."""
        debut = (dt.date.today() - dt.timedelta(days=jours - 1)).isoformat()
        total: dict[str, dict] = {}
        for jour, parh in self._lire().items():
            if jour >= debut:
                for h, m in parh.items():
                    cumul = total.setdefault(h, {})
                    for k, v in m.items():
                        cumul[k] = round(cumul.get(k, 0) + v, 6)
        return total

    def fenetres(self, harnais: str) -> list[Fenetre]:
        """Fenêtres de quota du harnais ; [] si la source manque ou est illisible (INV-ECO-2)."""
        instant, valeur = self._cache.get(harnais, (0.0, []))
        if time.monotonic() - instant < CACHE_S:
            return valeur
        conf = dict(self.config.economie.quotas.get(harnais) or {})
        lecteur = QUOTAS.get(conf.get("source") or SOURCE_DEFAUT.get(harnais, ""))
        try:
            valeur = lecteur(conf, self.config.harnais.get(harnais, {})) if lecteur else []
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("quotas de %s illisibles : %s", harnais, e)
            valeur = []
        self._cache[harnais] = (time.monotonic(), valeur)
        return valeur
