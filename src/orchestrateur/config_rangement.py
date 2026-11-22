"""Réglage du rangement de l'arbre : `[rangement]` de `config.toml`.

Rôle : porter le plafond de tâches ouvertes par parent et le choix de séparer les natures.
Frontières : données seules, sans import du paquet (`config` l'importe) ; la logique est dans `rangement`.
Invariants portés : INV-PLAFOND-1, INV-NATURE-1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfigRangement:
    """Réglages du rangement (Réglages › Arbre) : plafond de tâches ouvertes par parent, natures séparées."""
    plafond: int = 10
    natures_separees: bool = True

    def __post_init__(self):
        if isinstance(self.plafond, bool) or not isinstance(self.plafond, int) or not 2 <= self.plafond <= 100:
            raise ValueError("rangement.plafond : entier de 2 à 100")
        if not isinstance(self.natures_separees, bool):
            raise ValueError("rangement.natures_separees : vrai ou faux")
