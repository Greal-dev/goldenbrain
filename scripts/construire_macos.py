"""Construit l'application macOS de GoldenBrain : `build/GoldenBrain-macos-<arch>.zip` (GoldenBrain.app).

Rôle : GoldenBrain.app = Contents/Info.plist, MacOS/GoldenBrain (lanceur), Resources/{python
(Python 3.12 portable avec ses dépendances), app (graine), goldenbrain.sh, GoldenBrain.icns}.
L'utilisateur dézippe et glisse l'application dans Applications ; git vient des outils en ligne de
commande d'Apple, que macOS propose d'installer au premier besoin.
Frontières : construite sur Linux, ni signée ni notarisée (Gatekeeper : clic droit, Ouvrir) ;
la graine est recopiée chez l'utilisateur au premier lancement (INV-PAQUET-1).
Usage : python scripts/construire_macos.py [--arch arm64|x86_64] [--source <dépôt>] [--branche <branche>]
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import zipfile
from pathlib import Path

import construction as c

LANCEUR = '#!/bin/sh\nexec "$(dirname "$0")/../Resources/goldenbrain.sh" "$@"\n'
PLATEFORMES = {"arm64": "macosx_11_0_arm64", "x86_64": "macosx_10_13_x86_64"}


def construire_app(arch: str, source: str, branche: str) -> Path:
    racine = c.CONSTRUCTION / "macos" / arch
    shutil.rmtree(racine, ignore_errors=True)
    contenu = racine / "GoldenBrain.app" / "Contents"
    ressources = contenu / "Resources"
    python = c.extraire_python(f"python-macos-{arch}", ressources)
    c.installer_dependances(python / "lib" / "python3.12" / "site-packages", [PLATEFORMES[arch]])
    app = c.graine(ressources / "app", source, branche)
    shutil.copy2(c.INSTALLATION / "goldenbrain.sh", ressources / "goldenbrain.sh")
    (ressources / "goldenbrain.sh").chmod(0o755)
    c.icns(c.RACINE / "web" / "icone-512.png", ressources / "GoldenBrain.icns")
    (contenu / "MacOS").mkdir()
    (contenu / "MacOS" / "GoldenBrain").write_text(LANCEUR, encoding="utf-8")
    (contenu / "MacOS" / "GoldenBrain").chmod(0o755)
    plist = (c.INSTALLATION / "Info.plist").read_text(encoding="utf-8")
    (contenu / "Info.plist").write_text(plist.replace("@VERSION@", c.version(app).split("+")[0]), encoding="utf-8")
    return racine / "GoldenBrain.app"


def zipper(dossier: Path, sortie: Path) -> None:
    """Zip qui garde droits d'exécution et liens symboliques (le Python portable en contient)."""
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        for chemin in sorted(dossier.rglob("*")):
            nom = chemin.relative_to(dossier.parent).as_posix()
            mode = os.lstat(chemin).st_mode
            if chemin.is_symlink():
                info = zipfile.ZipInfo(nom)
                info.create_system = 3  # Unix : external_attr porte le mode, lien compris
                info.external_attr = mode << 16
                z.writestr(info, os.readlink(chemin))
            elif chemin.is_dir():
                continue
            else:
                info = zipfile.ZipInfo.from_file(chemin, nom)
                info.external_attr = (stat.S_IFREG | stat.S_IMODE(mode)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with chemin.open("rb") as f:
                    z.writestr(info, f.read())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--arch", choices=sorted(PLATEFORMES), default="arm64")
    p.add_argument("--source", default=c.DEPOT_PUBLIC)
    p.add_argument("--branche", default=c.BRANCHE_DIFFUSION)
    a = p.parse_args()
    app = construire_app(a.arch, a.source, a.branche)
    sortie = c.CONSTRUCTION / f"GoldenBrain-macos-{a.arch}.zip"
    zipper(app, sortie)
    print(f"Application : {sortie}")


if __name__ == "__main__":
    c.principal(main)
