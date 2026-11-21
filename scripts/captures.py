"""Captures d'écran et vidéo de démonstration du README : `python scripts/captures.py` (≈ 5 min).

Rôle : rejoue `tests/ui/scenario_captures.py` (vrai serveur, vault de démonstration fictif, harnais
factice) dans les quatre langues et dépose dans `docs/captures/`, par langue `<l>` : `arbre-<l>.png`,
`tache-<l>.png`, `travaux-<l>.png`, `graphe-<l>.png` et la vidéo `demo-<l>.webm`.
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
