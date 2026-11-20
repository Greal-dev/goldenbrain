"""Réglage du compactage automatique des conversations (`[compactage]` de config.toml).

Rôle : porter et valider le seuil de compactage ; réexporté par `config`.
Frontières : aucun calcul de seuil (voir `compactage`), aucune lecture de fichier.
Invariants portés : INV-COMPACT-1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ConfigCompactage:
    """Compactage automatique des conversations (INV-COMPACT-1) : seuil en % de la fenêtre du modèle,
    plafond absolu facultatif en jetons (0 = désactivé) ; le premier atteint déclenche. `fenetres` :
    motif de modèle -> fenêtre en jetons (complète et prime sur les défauts du module `compactage`) ;
    `ordres` : harnais -> ordre de compactage du repli commun (complète les défauts)."""
    pct: float = 45
    plafond: int = 0
    fenetres: dict = field(default_factory=dict)
    ordres: dict = field(default_factory=dict)

    def __post_init__(self):
        from . import langues  # import tardif : langues importe config
        if not isinstance(self.pct, (int, float)) or isinstance(self.pct, bool)                 or not math.isfinite(self.pct) or not 1 <= self.pct <= 100:
            raise ValueError(langues.t("serveur.config_compactage.pct"))
        if not isinstance(self.plafond, int) or isinstance(self.plafond, bool) or self.plafond < 0:
            raise ValueError(langues.t("serveur.config_compactage.plafond"))
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in self.fenetres.values()):
            raise ValueError(langues.t("serveur.config_compactage.fenetres"))
        if not all(isinstance(v, str) for v in self.ordres.values()):
            raise ValueError(langues.t("serveur.config_compactage.ordres"))
