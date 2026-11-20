"""Langue du système pour le lanceur Windows « un clic » (GoldenBrain.cmd).

Rôle : affiche le code de la langue de l'utilisateur (fr, en, de, es ; en sinon), lue dans la
langue d'affichage de Windows (ailleurs : LC_ALL, LC_MESSAGES, LANG) ; avec le dossier de
l'application en argument, écrit au premier lancement config.toml (réglages de départ et langue),
pour que l'interface s'ouvre dans la même langue.
Frontières : n'écrit jamais une configuration existante, ni quand ORCH_CONFIG en désigne une
autre, ni si cette version de GoldenBrain ignore le réglage `langue` (une clé inconnue
l'empêcherait de démarrer). Bibliothèque standard seulement.
Usage : python langue.py [<dossier de l'application>]
"""

from __future__ import annotations

import locale
import os
import sys
from pathlib import Path

LANGUES = ("fr", "en", "de", "es")


def code_systeme() -> str:
    nom = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    if sys.platform == "win32":
        import ctypes
        # Langue d'affichage de Windows (celle des menus), pas le format des dates.
        nom = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), nom)
    code = nom[:2].lower()
    return code if code in LANGUES else "en"


def ecrire_config(app: Path, code: str) -> None:
    config, depart = app / "config.toml", app / "config.depart.toml"
    if os.environ.get("ORCH_CONFIG") or config.exists() or not depart.exists():
        return
    exemple = app / "config.exemple.toml"
    if not exemple.exists() or "langue = " not in exemple.read_text(encoding="utf-8"):
        return
    lignes = depart.read_text(encoding="utf-8").splitlines()
    if "[interface]" in lignes:
        lignes.insert(lignes.index("[interface]") + 1, f'langue = "{code}"')
    else:
        lignes += ["", "[interface]", f'langue = "{code}"']
    config.write_text("\n".join(lignes) + "\n", encoding="utf-8")


if __name__ == "__main__":
    code = code_systeme()
    if len(sys.argv) > 1:
        ecrire_config(Path(sys.argv[1]), code)
    print(code)
