"""Construit l'installateur Windows de GoldenBrain : `build/GoldenBrain-installation.exe`.

Rôle : prépare `build/windows/source` (Python 3.12 portable avec ses dépendances, Git portable
MinGit, graine de l'application en fins de ligne Windows, lanceur `GoldenBrain.cmd`, icône), puis
compile `installation/goldenbrain.iss` par Inno Setup, exécuté sous wine sur le poste Linux.
Frontières : n'exécute rien de Windows hors du compilateur Inno Setup ; installation par
utilisateur, sans droits administrateur. La copie de l'utilisateur (%LOCALAPPDATA%\\GoldenBrain\\app)
n'appartient pas à l'installateur (INV-PAQUET-1).
Usage : python scripts/construire_windows.py [--source <dépôt>] [--branche <branche>] [--sans-compilation]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import construction as c


def preparer(source: str, branche: str) -> tuple[Path, str]:
    dossier = c.CONSTRUCTION / "windows" / "source"
    shutil.rmtree(dossier, ignore_errors=True)
    python = c.extraire_python("python-windows-x86_64", dossier)
    c.installer_dependances(python / "Lib" / "site-packages", ["win_amd64"], supplements=("colorama",))
    with zipfile.ZipFile(c.telecharger("mingit-windows-x86_64")) as z:
        z.extractall(dossier / "git")
    app = c.graine(dossier / "graine", source, branche, crlf=True)
    # cmd.exe lit mal les étiquettes (goto) d'un fichier en fins de ligne LF.
    texte = (c.INSTALLATION / "GoldenBrain.cmd").read_text(encoding="utf-8")
    (dossier / "GoldenBrain.cmd").write_bytes(texte.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii"))
    for script in ("deja_lance.py", "langue.py"):
        shutil.copy2(c.INSTALLATION / script, dossier / script)
    c.ico(c.RACINE / "web" / "icone-192.png", dossier / "GoldenBrain.ico")
    c.controler_propre(dossier)
    return dossier, c.version(app)


def iscc() -> Path:
    """Compilateur Inno Setup, installé une fois sous wine dans le cache (préfixe wine dédié)."""
    prefixe = c.cache() / "wine"
    cible = c.cache() / "innosetup"
    compilateur = cible / "ISCC.exe"
    if not compilateur.exists():
        if shutil.which("wine") is None:
            raise c.ErreurConstruction("wine est requis pour compiler l'installateur (ou --sans-compilation)")
        subprocess.run(["wine", str(c.telecharger("innosetup")), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                        "/CURRENTUSER", "/NORESTART", f"/DIR=Z:{cible}"],
                       check=True, env={**os.environ, "WINEPREFIX": str(prefixe), "WINEDEBUG": "-all"})
    return compilateur


def compiler(dossier: Path, version: str) -> Path:
    env = {**os.environ, "WINEPREFIX": str(c.cache() / "wine"), "WINEDEBUG": "-all"}
    compilateur = iscc()
    # wine marque « cachés » les fichiers en point, qu'Inno Setup omet : sans .git, la copie
    # installée ne pourrait pas se mettre à jour (essai du 2026-11-19).
    subprocess.run(["wine", "reg", "add", r"HKCU\Software\Wine", "/v", "ShowDotFiles", "/d", "Y", "/f"],
                   check=True, env=env, capture_output=True)
    subprocess.run(["wine", str(compilateur), "/Q", f"/DSource=Z:{dossier}", f"/DVersion={version}",
                    f"/OZ:{c.CONSTRUCTION}", f"Z:{c.INSTALLATION / 'goldenbrain.iss'}"], check=True, env=env)
    sortie = c.CONSTRUCTION / "GoldenBrain-installation.exe"
    c.controler_artefact(sortie)
    print(f"Installateur : {sortie}")
    return sortie


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", default=c.DEPOT_PUBLIC)
    p.add_argument("--branche", default=c.BRANCHE_DIFFUSION)
    p.add_argument("--sans-compilation", action="store_true", help="préparer seulement build/windows/source")
    a = p.parse_args()
    dossier, version = preparer(a.source, a.branche)
    if a.sans_compilation:
        print(f"Source préparée : {dossier}")
    else:
        compiler(dossier, version)


if __name__ == "__main__":
    c.principal(main)
