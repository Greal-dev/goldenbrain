"""Vault chargé « comme le vrai » pour mesurer la réactivité (tâche « Interface réactive »).

Rôle : `peupler(vault)` ajoute au vault des scénarios 260 tâches réparties sur 8 projets (mères et filles), dont 150 tâches
terminées à valider (donc 150 décisions) et une tâche au fil de 200 messages (`FIL_LONG`, transcript rejoué par le harnais factice).
Frontières : n'écrit que sous le vault passé ; aucun réseau. Les noms de fichiers sont propres à la charge.
"""

from __future__ import annotations

from pathlib import Path

import univers

PROJETS = 8
TACHES = 260
VALIDER = 150
FIL_LONG = "charge-fil-long"
MESSAGES_FIL = 200


def peupler(vault: Path) -> None:
    for p in range(PROJETS):
        univers.ecrire(vault, f"Projets/C1-Charge{p}/contexte.md", f"---\ntype: contexte\ncasquette: C1-Pro\nnom: Charge {p}\n---\n")
    for i in range(TACHES):
        p = i % PROJETS
        fait = i < VALIDER
        extra = (f'session: s-charge-{i}\n' if fait else '') + (f'parent: "[[charge-{i - PROJETS}]]"\n' if i >= 2 * PROJETS and i % 3 == 0 else '')
        univers.ecrire(vault, f"Projets/C1-Charge{p}/taches/charge-{i}.md",
                       univers.tache(f"Tâche de charge {i}", statut="fait" if fait else ("en-cours" if i % 7 == 0 else "a-faire"), extra=extra))
    univers.ecrire(vault, f"Projets/C1-Charge0/taches/{FIL_LONG}.md",
                   univers.tache("Tâche au long fil de discussion", statut="en-cours", extra="session: s-long\n"))
