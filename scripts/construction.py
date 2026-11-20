"""Briques communes de la construction des installations « un clic » (scripts/construire_*.py).

Rôle : téléchargement vérifié des composants épinglés (`installation/versions.txt`), Python portable,
dépendances épinglées (`installation/contraintes.txt`) installées pour la plateforme cible, graine de
l'application (copie git dont `origin` est le dépôt public, pour que la mise à jour avance), icônes.
Frontières : s'exécute sur un poste Linux de construction ; n'écrit que sous `build/` et dans le cache
(`GB_CACHE`, défaut `~/.cache/goldenbrain-construction`) ; aucune dépendance hors bibliothèque standard,
git et l'outil pip du Python portable téléchargé.
Invariants portés : INV-PAQUET-1 (la graine porte l'historique git ; branche locale = branche de diffusion),
INV-PAQUET-2 (tout composant téléchargé est vérifié par empreinte SHA-256 avant usage).
"""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
INSTALLATION = RACINE / "installation"
CONSTRUCTION = RACINE / "build"
DEPOT_PUBLIC = "https://github.com/Greal-dev/goldenbrain.git"
BRANCHE_DIFFUSION = "main"  # défaut de [mise_a_jour] branche
DEPENDANCES = ["fastapi", "uvicorn", "PyYAML"]  # celles de pyproject.toml, rien d'autre


class ErreurConstruction(RuntimeError):
    pass


def composants() -> dict[str, tuple[str, str]]:
    """`versions.txt` : clé → (adresse, empreinte SHA-256)."""
    table = {}
    for ligne in (INSTALLATION / "versions.txt").read_text(encoding="utf-8").splitlines():
        if ligne.strip() and not ligne.startswith("#"):
            cle, url, empreinte = ligne.split()
            table[cle] = (url, empreinte)
    return table


def cache() -> Path:
    dossier = Path(os.environ.get("GB_CACHE") or Path.home() / ".cache" / "goldenbrain-construction")
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def empreinte(fichier: Path) -> str:
    h = hashlib.sha256()
    with fichier.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(cle: str) -> Path:
    """INV-PAQUET-2 : rend le fichier du cache, téléchargé au besoin, seulement si l'empreinte concorde."""
    url, attendue = composants()[cle]
    fichier = cache() / url.rsplit("/", 1)[-1].replace("%2B", "+")
    if not fichier.exists() or empreinte(fichier) != attendue:
        print(f"Téléchargement : {url}")
        partiel = fichier.with_suffix(fichier.suffix + ".partiel")
        with urllib.request.urlopen(url, timeout=120) as r, partiel.open("wb") as f:
            shutil.copyfileobj(r, f)
        partiel.replace(fichier)
    if empreinte(fichier) != attendue:
        fichier.unlink()
        raise ErreurConstruction(f"empreinte inattendue pour {cle} : téléchargement refusé")
    return fichier


def extraire_python(cle: str, dest: Path) -> Path:
    """Python portable (python-build-standalone, « install_only ») dans `dest/python`."""
    shutil.rmtree(dest / "python", ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    # Archive .tar.gz ouverte en binaire explicite (tarfile.open passerait pour un open() texte).
    with telecharger(cle).open("rb") as brut, gzip.GzipFile(fileobj=brut) as gz, tarfile.TarFile(fileobj=gz) as tar:
        tar.extractall(dest, filter="tar")
    return dest / "python"


def python_outil() -> Path:
    """Python portable Linux du poste de construction : il porte le pip qui prépare toutes les cibles."""
    dossier = cache() / "outil"
    py = dossier / "python" / "bin" / "python3"
    if not py.exists():
        extraire_python("python-linux-x86_64", dossier)
    return py


def installer_dependances(site_packages: Path, plateformes: list[str], supplements: tuple[str, ...] = ()) -> None:
    """Dépendances épinglées, roues binaires de la plateforme cible, directement dans `site_packages`."""
    commande = [str(python_outil()), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                "--no-compile", "--target", str(site_packages), "--python-version", "3.12",
                "--implementation", "cp", "--only-binary=:all:", "-c", str(INSTALLATION / "contraintes.txt")]
    for p in plateformes:
        commande += ["--platform", p]
    subprocess.run(commande + DEPENDANCES + list(supplements), check=True)


def graine(dest: Path, source: str = DEPOT_PUBLIC, branche: str = BRANCHE_DIFFUSION, crlf: bool = False) -> Path:
    """INV-PAQUET-1 : copie git de l'application, sur la branche locale de diffusion, `origin` = dépôt public.

    `source`/`branche` permettent de construire depuis une copie locale ; la mise à jour suivra
    `DEPOT_PUBLIC` quoi qu'il arrive. `crlf` : copie destinée à Windows (fins de ligne CRLF : un .cmd en LF lit mal ses étiquettes).
    """
    shutil.rmtree(dest, ignore_errors=True)
    # Windows ne garde pas le bit exécutable : sans filemode=false, lancer.sh paraît modifié et la
    # copie, « sale », refuserait la mise à jour (essai sous wine du 2026-11-19).
    options = ["--config", "core.autocrlf=true", "--config", "core.filemode=false"] if crlf else []
    subprocess.run(["git", "clone", "--quiet", *options, "--branch", branche, source, str(dest)], check=True)
    if branche != BRANCHE_DIFFUSION:
        subprocess.run(["git", "-C", str(dest), "branch", "-m", BRANCHE_DIFFUSION], check=True)
        subprocess.run(["git", "-C", str(dest), "config", f"branch.{BRANCHE_DIFFUSION}.merge",
                        f"refs/heads/{BRANCHE_DIFFUSION}"], check=True)
    subprocess.run(["git", "-C", str(dest), "remote", "set-url", "origin", DEPOT_PUBLIC], check=True)
    return dest


def version(app: Path) -> str:
    """Version lisible du paquet : date et empreinte courte de la graine (ex. 2026.11.19+02f9bef)."""
    date = subprocess.run(["git", "-C", str(app), "log", "-1", "--format=%cs"], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()
    sha = subprocess.run(["git", "-C", str(app), "rev-parse", "--short=7", "HEAD"], check=True,
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
    return f"{date.replace('-', '.')}+{sha}"


def ico(png: Path, dest: Path) -> None:
    """Icône Windows : un conteneur ICO qui embarque le PNG tel quel (pris en charge depuis Vista)."""
    donnees = png.read_bytes()
    entete = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(donnees), 22)
    dest.write_bytes(entete + donnees)


def icns(png512: Path, dest: Path) -> None:
    """Icône macOS : un conteneur ICNS avec l'entrée PNG 512 px (« ic09 »)."""
    donnees = png512.read_bytes()
    entree = b"ic09" + struct.pack(">I", len(donnees) + 8) + donnees
    dest.write_bytes(b"icns" + struct.pack(">I", len(entree) + 8) + entree)


def principal(fonction) -> None:
    """Point d'entrée commun : message lisible plutôt que trace en cas d'échec prévu."""
    try:
        fonction()
    except (ErreurConstruction, subprocess.CalledProcessError, OSError) as e:
        print(f"Construction impossible : {e}", file=sys.stderr)
        sys.exit(1)
