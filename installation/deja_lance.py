"""GoldenBrain déjà lancé ? Alors ouvrir seulement sa page (lanceur Windows `GoldenBrain.cmd`).

Rôle : lit le port de la configuration (`ORCH_CONFIG`, sinon `<app>/config.toml` ; 8300 par défaut), interroge http://127.0.0.1:<port>/ ;
s'il répond, ouvre le navigateur et sort avec 0, sinon sort avec 1 (le lanceur démarre le serveur).
Frontières : bibliothèque standard seule ; ne démarre ni n'arrête rien.
"""

import os
import sys
import tomllib
import urllib.request
import webbrowser
from pathlib import Path


def port(app: Path) -> int:
    try:
        with Path(os.environ.get("ORCH_CONFIG") or app / "config.toml").open("rb") as f:
            return int(tomllib.load(f).get("serveur", {}).get("port", 8300))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return 8300


def main(app: Path) -> int:
    url = f"http://127.0.0.1:{port(app)}"
    try:
        urllib.request.urlopen(url + "/", timeout=2).close()
    except OSError:
        return 1
    webbrowser.open(url)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
