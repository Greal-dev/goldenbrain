"""Points de restauration du code : instantané git hors branche avant un tour, plan et restauration.

Rôle : capturer l'arbre de travail d'un dépôt (fichiers suivis et non suivis non ignorés) dans un
commit référencé `refs/goldenbrain/points/<tâche>/<horodatage>`, sans toucher l'index réel, HEAD ni
aucune branche ; dresser le plan à blanc d'une restauration ; restaurer tout ou rien.
Frontières : git seul (liste d'arguments, jamais de shell) ; ne lit ni n'écrit le vault ; ne sait
rien des tours ni des journaux (voir `retour`).
Invariants portés : INV-RETOUR-3.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import langues

PREFIXE = "refs/goldenbrain/points"
# Auteur des commits de point : neutre, jamais l'identité de l'utilisateur.
IDENTITE = {"GIT_AUTHOR_NAME": "GoldenBrain", "GIT_AUTHOR_EMAIL": "goldenbrain@localhost",
            "GIT_COMMITTER_NAME": "GoldenBrain", "GIT_COMMITTER_EMAIL": "goldenbrain@localhost"}
ETATS = {"M": "modifie", "A": "recree", "D": "supprime"}  # vu depuis l'état courant vers le point


class ErreurPoint(Exception):
    pass


def _git(depot: Path, *args: str, env: dict | None = None, entree: str | None = None) -> str:
    r = subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", input=entree, timeout=120,
                       env={**os.environ, **(env or {})})
    if r.returncode:
        raise ErreurPoint(f"git {args[0]} : {r.stderr.strip()[:300]}")
    return r.stdout


def depot_de(dossier: str | Path) -> Path | None:
    """Racine du dépôt git qui contient `dossier`, ou None (pas de dépôt, pas de git)."""
    if not dossier or not Path(dossier).is_dir() or not shutil.which("git"):
        return None
    try:
        return Path(_git(Path(dossier), "rev-parse", "--show-toplevel").strip())
    except (ErreurPoint, OSError, subprocess.SubprocessError):
        return None


def _segment(texte: str) -> str:
    # Nom de référence git sûr : ni `..`, ni `.lock`, ni caractère interdit.
    return re.sub(r"[^A-Za-z0-9_-]+", "-", texte).strip("-")[:120] or "tache"


def _instantane(depot: Path) -> str:
    """Commit (non référencé) de l'arbre de travail courant ; l'index réel reste intact."""
    reel = Path(_git(depot, "rev-parse", "--path-format=absolute", "--git-path", "index").strip())
    with tempfile.TemporaryDirectory() as d:
        index = Path(d) / "index"
        if reel.is_file():
            # `copy2` : l'index garde sa date, sans quoi git ne détecte plus une réécriture de même taille dans la même fraction de seconde (« racy git »).
            shutil.copy2(reel, index)  # garde le cache des dates : `add -A` ne relit que le modifié
        env = {"GIT_INDEX_FILE": str(index), **IDENTITE}
        _git(depot, "add", "-A", "--", ".", env=env)
        arbre = _git(depot, "write-tree", env=env).strip()
    tete = subprocess.run(["git", "-C", str(depot), "rev-parse", "-q", "--verify", "HEAD"],
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()
    parents = ["-p", tete] if tete else []
    return _git(depot, "commit-tree", arbre, *parents, "-m", "GoldenBrain : point de restauration",
                env=IDENTITE).strip()


def creer(depot: Path, tache: str, nom: str = "") -> dict:
    """INV-RETOUR-3 : instantané référencé sous `refs/goldenbrain/points/<tâche>/<nom>`."""
    commit = _instantane(depot)
    nom = _segment(nom or dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    ref = f"{PREFIXE}/{_segment(tache)}/{nom}"
    _git(depot, "update-ref", ref, commit)
    return {"depot": str(depot), "ref": ref, "commit": commit}


def _diff(depot: Path, depuis: str, vers: str) -> list[tuple[str, str]]:
    sortie = _git(depot, "diff", "--name-status", "--no-renames", "-z", depuis, vers)
    champs = [c for c in sortie.split("\0") if c]
    return list(zip(champs[::2], champs[1::2]))


def plan(depot: Path, commit: str) -> list[dict]:
    """Plan à blanc : fichiers que la restauration au point `commit` changerait."""
    _git(depot, "cat-file", "-e", f"{commit}^{{commit}}")
    courant = _instantane(depot)
    return [{"etat": ETATS.get(s[:1], "modifie"), "chemin": c} for s, c in _diff(depot, courant, commit)]


def _appliquer(depot: Path, cible: str, depuis: str) -> None:
    changes = _diff(depot, depuis, cible)
    ecrire = [c for s, c in changes if s[:1] != "D"]
    with tempfile.TemporaryDirectory() as d:
        env = {"GIT_INDEX_FILE": str(Path(d) / "index")}
        _git(depot, "read-tree", cible, env=env)
        if ecrire:
            _git(depot, "checkout-index", "-f", "-z", "--stdin", env=env, entree="\0".join(ecrire))
    for s, c in changes:
        if s[:1] == "D":  # absent du point : retiré (il reste dans le point « avant-retour »)
            (depot / c).unlink(missing_ok=True)


def restaurer(depot: Path, tache: str, commit: str) -> dict:
    """Restaure les fichiers du dépôt à l'état du point, tout ou rien.

    Un point « avant-retour » capture d'abord l'état courant : la restauration est réversible ;
    en cas d'échec en cours de route, l'état d'avant est réappliqué. HEAD et branches inchangés."""
    _git(depot, "cat-file", "-e", f"{commit}^{{commit}}")
    avant = creer(depot, tache, "avant-retour-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    try:
        _appliquer(depot, commit, avant["commit"])
    except (ErreurPoint, OSError, subprocess.SubprocessError) as e:
        try:
            _appliquer(depot, avant["commit"], _instantane(depot))
        except (ErreurPoint, OSError, subprocess.SubprocessError):
            pass  # l'état d'avant reste intact dans sa référence
        raise ErreurPoint(langues.t("serveur.points.restauration_annulee", erreur=e, ref=avant["ref"])) from e
    return avant
