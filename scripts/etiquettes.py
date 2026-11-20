"""Étiquettes standard des tickets du dépôt public, posées de façon reproductible par `gh label create --force`.

Rôle : un seul registre (`ETIQUETTES`) des étiquettes que citent les formulaires `.github/ISSUE_TEMPLATE/` ;
relancer le script remet noms, couleurs et descriptions à l'identique. `--essai` affiche sans rien envoyer.
Frontières : écrit seulement les étiquettes du registre, n'en supprime aucune ; `gh` déjà connecté, aucun secret.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

DEPOT_PUBLIC = "https://github.com/Greal-dev/goldenbrain".removeprefix("https://github.com/")
# nom, couleur, description (anglais : le dépôt public est lu par tous ; aide française entre parenthèses)
ETIQUETTES = [
    ("bug", "d73a4a", "Something does not work as expected (anomalie)"),
    ("évolution", "a2eeef", "New feature or improvement (demande d'évolution)"),
    ("bon premier ticket", "7057ff", "Good first issue: small, well scoped (bon premier ticket)"),
    ("aide bienvenue", "008672", "Help wanted (aide bienvenue)"),
    ("à trier", "fbca04", "Not yet triaged by a maintainer (à trier)"),
]


def commandes(depot: str) -> list[list[str]]:
    return [["gh", "label", "create", nom, "-R", depot, "--color", couleur, "--description", desc, "--force"]
            for nom, couleur, desc in ETIQUETTES]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--depot", default=DEPOT_PUBLIC)
    p.add_argument("--essai", action="store_true", help="afficher les commandes sans rien envoyer")
    a = p.parse_args(argv)
    for c in commandes(a.depot):
        if a.essai:
            print(" ".join(c))
        elif subprocess.run(c).returncode:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
