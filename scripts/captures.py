"""Captures d'écran du README : `python scripts/captures.py`.

Rôle : rejoue `tests/ui/scenario_captures.py` (vrai serveur, vault de démonstration fictif, harnais
factice) et dépose `arbre.png` et `tache.png` dans `docs/captures/`.
Frontières : aucune installation (Playwright requis, comme `check_ui.py`) ; aucune donnée réelle (INV-PUB-1).
"""

import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def main() -> int:
    env = {**os.environ, "GB_CAPTURES": str(RACINE / "docs" / "captures")}
    return subprocess.run([sys.executable, str(RACINE / "scripts" / "check_ui.py"), "-k", "captures"],
                          cwd=RACINE, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
