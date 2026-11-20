"""Modèles de tâches prêts à l'emploi : un fichier Markdown par modèle, dans le dossier `modeles/`.

Rôle : lire le dossier des modèles (en-tête `titre`, `resume`, `ordre` ; le corps est la mission) et les
servir à la galerie de « Nouvelle tâche » (`GET /api/modeles`). Ajouter un modèle = déposer un fichier.
Langue : `modeles/<code>/` (en, de, es) porte la traduction d'un modèle sous le même nom ; à défaut, le français.
Frontières : lecture seule, bornée ; n'écrit rien, ne crée aucune tâche (le formulaire est seulement
pré-rempli, la création reste le geste de l'utilisateur) ; un fichier illisible est écarté, jamais fatal.
Invariants portés : INV-MODELES-1, INV-LANGUE-1.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter

from . import langues

DOSSIER = Path(__file__).resolve().parents[2] / "modeles"
MAX_FICHIERS = 60
MAX_OCTETS = 20_000
log = logging.getLogger(__name__)


def lire(fichier: Path) -> dict | None:
    """Un modèle `{id, titre, resume, mission, ordre}`, ou None si le fichier n'en est pas un."""
    try:
        if fichier.is_symlink() or fichier.stat().st_size > MAX_OCTETS:
            return None
        texte = fichier.read_text(encoding="utf-8")
        _, entete, corps = texte.split("---", 2) if texte.startswith("---") else ("", "", texte)
        fm = yaml.safe_load(entete) or {}
    except (OSError, ValueError, yaml.YAMLError) as e:
        log.warning("modèle écarté %s : %s", fichier.name, e)
        return None
    if not isinstance(fm, dict) or not str(fm.get("titre") or "").strip() or not corps.strip():
        return None
    ordre = fm.get("ordre")
    return {"id": fichier.stem, "titre": str(fm["titre"]).strip()[:120], "resume": str(fm.get("resume") or "").strip()[:200],
            "mission": corps.strip(), "ordre": ordre if isinstance(ordre, int) else 999}


def traduit(fichier: Path, langue: str) -> Path:
    """INV-LANGUE-1 : la version `<dossier>/<langue>/<nom>` du modèle si elle existe, sinon le fichier français."""
    autre = fichier.parent / langue / fichier.name
    return autre if langue != langues.SOURCE and autre.is_file() else fichier


def lister(dossier: Path = DOSSIER, langue: str | None = None) -> list[dict]:
    """INV-MODELES-1 : modèles valides du dossier, triés par `ordre` puis titre ; dossier absent = liste vide.
    Les modèles sont ceux du dossier français ; chacun est lu dans `langue` (défaut : langue réglée) s'il y est traduit."""
    if not dossier.is_dir():
        return []
    code = langue or langues.courante()
    fichiers = sorted(dossier.glob("*.md"))[:MAX_FICHIERS]
    modeles = [m for f in fichiers if (m := lire(traduit(f, code)) or lire(f))]
    return sorted(modeles, key=lambda m: (m["ordre"], m["titre"].casefold()))


def routes(dossier: Path = DOSSIER) -> APIRouter:
    r = APIRouter()

    @r.get("/api/modeles")
    async def modeles():
        return lister(dossier)

    return r
