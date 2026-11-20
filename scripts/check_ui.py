"""Vérification d'interface : `python scripts/check_ui.py [args pytest]`.

Rôle : lance les scénarios `tests/ui/scenario_*.py` (Playwright) contre le vrai serveur, sur un vault
temporaire et un harnais factice. Hors de la porte rapide : `scripts/check.py` ne l'appelle pas.
Frontières : aucune installation ; si Playwright ou son navigateur manque, échec explicite.
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import verrou  # noqa: E402


def main() -> int:
    # Une seule porte d'interface à la fois : deux exemplaires pèsent ≈ 1,4 Go en pic.
    if (_verrou := verrou.prendre("check_ui")) is None:
        print("CHECK_UI : un autre exemplaire est déjà en cours ; attends sa fin")
        return 3
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("CHECK_UI : Playwright absent du Python embarqué (rien n'est installé automatiquement)")
        return 2
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/ui",
           "-o", "python_files=scenario_*.py", *sys.argv[1:]]
    code = subprocess.run(cmd, cwd=RACINE).returncode
    print("CHECK_UI : vert" if code == 0 else "CHECK_UI : rouge")
    return code


if __name__ == "__main__":
    sys.exit(main())
