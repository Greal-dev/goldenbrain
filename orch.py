"""Point d'entrée de la commande `orch` pour les agents.

Lancé directement par Python (sans passer par cmd.exe) : un chemin de dépôt avec
espaces et des arguments entre guillemets cassent un `.cmd` (essai réel du 12/11).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from orchestrateur.cli import main  # noqa: E402

sys.exit(main())
