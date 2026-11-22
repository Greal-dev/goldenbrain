"""Construit le paquet Debian/Ubuntu de GoldenBrain : `build/goldenbrain_<version>_amd64.deb`.

Rôle : /opt/goldenbrain = Python 3.12 portable avec ses dépendances, graine de l'application
(copie git), lanceur ; /usr/bin/goldenbrain ; entrée de menu et icônes. Un double-clic sur le
.deb l'installe (Logithèque, `apt install ./fichier.deb`) ; apt ajoute git, seule dépendance système.
Frontières : la graine sous /opt est en lecture seule ; le premier lancement la recopie chez
l'utilisateur (INV-PAQUET-1), et seule cette copie est mise à jour.
Usage : python scripts/construire_deb.py [--source <dépôt ou dossier git>] [--branche <branche>]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import construction as c

CONTROLE = """Package: goldenbrain
Version: {version}
Architecture: amd64
Maintainer: GoldenBrain <goldenbrain@example.org>
Depends: git, xdg-utils
Section: utils
Priority: optional
Installed-Size: {taille}
Homepage: https://github.com/Greal-dev/goldenbrain
Description: Confier des tâches à des assistants IA, rangées dans vos notes
 GoldenBrain organise des tâches confiées à des assistants IA en ligne de commande,
 chacune rangée dans un dossier de notes Markdown. Python et ses composants sont
 embarqués ; l'application se met à jour d'elle-même.
"""
LANCEUR = '#!/bin/sh\nexec /opt/goldenbrain/goldenbrain.sh "$@"\n'


def construire(source: str, branche: str) -> Path:
    racine = c.CONSTRUCTION / "deb" / "arbre"
    shutil.rmtree(racine, ignore_errors=True)
    opt = racine / "opt" / "goldenbrain"
    python = c.extraire_python("python-linux-x86_64", opt)
    site = python / "lib" / "python3.12" / "site-packages"
    c.installer_dependances(site, ["manylinux2014_x86_64", "manylinux_2_17_x86_64"])
    # /opt est en lecture seule pour l'utilisateur : le bytecode doit y être déjà.
    # -s/-p : le bytecode retient le chemin installé (/opt/…), pas celui du poste de construction.
    subprocess.run([str(python / "bin" / "python3"), "-m", "compileall", "-q", "-s", str(racine), "-p", "/",
                    str(site)], check=True)
    app = c.graine(opt / "app", source, branche)
    shutil.copy2(c.INSTALLATION / "goldenbrain.sh", opt / "goldenbrain.sh")
    (opt / "goldenbrain.sh").chmod(0o755)

    usr = racine / "usr"
    (usr / "bin").mkdir(parents=True)
    (usr / "bin" / "goldenbrain").write_text(LANCEUR, encoding="utf-8")
    (usr / "bin" / "goldenbrain").chmod(0o755)
    menu = (c.INSTALLATION / "goldenbrain.desktop").read_text(encoding="utf-8")
    (usr / "share" / "applications").mkdir(parents=True)
    (usr / "share" / "applications" / "goldenbrain.desktop").write_text(
        menu.replace("@LANCEUR@", "/usr/bin/goldenbrain").replace("@ICONE@", "goldenbrain"), encoding="utf-8")
    for taille in (192, 512):
        icones = usr / "share" / "icons" / "hicolor" / f"{taille}x{taille}" / "apps"
        icones.mkdir(parents=True)
        shutil.copy2(c.RACINE / "web" / f"icone-{taille}.png", icones / "goldenbrain.png")

    version = c.version(app)
    kio = sum(f.stat().st_size for f in racine.rglob("*") if f.is_file() and not f.is_symlink()) // 1024
    (racine / "DEBIAN").mkdir()
    (racine / "DEBIAN" / "control").write_text(CONTROLE.format(version=version, taille=kio), encoding="utf-8")
    sortie = c.CONSTRUCTION / f"goldenbrain_{version}_amd64.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(racine), str(sortie)], check=True)
    print(f"Paquet : {sortie}")
    return sortie


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", default=c.DEPOT_PUBLIC)
    p.add_argument("--branche", default=c.BRANCHE_DIFFUSION)
    a = p.parse_args()
    construire(a.source, a.branche)


if __name__ == "__main__":
    c.principal(main)
