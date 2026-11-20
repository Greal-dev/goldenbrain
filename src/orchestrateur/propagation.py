"""Propagation des liens `alimente` à la fin d'un tour réussi (partie du moteur).

Rôle : prévenir par un message les tâches ouvertes qu'une tâche alimente.
Frontières : passe par `Moteur.soumettre` (aucun second chemin d'exécution) ; n'écrit rien au vault.
Invariants portés : INV-LIEN-1 (seulement après un tour réussi, vers les tâches alimentées ouvertes),
INV-MSG-1 (compteur de sauts), INV-MSG-2 (jamais vers la tâche source du tour).
"""

from __future__ import annotations

import logging

from . import liens
from .vault import ErreurOrch

log = logging.getLogger(__name__)


class MixinPropagation:
    """Partie du moteur : propagation INV-LIEN-1 (extraite de `moteur.py`, plafonné à 500 lignes)."""

    def _propager(self, ident: str, fiche: dict, sauts: int, source: str = "") -> None:
        # INV-LIEN-1 : seulement après un tour réussi, vers les tâches ouvertes alimentées ;
        # le compteur de sauts (INV-MSG-1) coupe une chaîne qui reboucle par messages.
        taches = self.vault.index()[0]
        texte = (f"[La tâche « {taches[ident].titre} » ({ident}), qui t'alimente, vient "
                 f"d'avancer. Fait : {fiche.get('fait', '')} Situation : "
                 f"{fiche.get('situation', '')} Mets à jour ce qui en dépend ; s'il n'y a rien "
                 f"à faire, dis-le en une ligne.]")
        for cible in liens.alimentees(taches, ident):
            if cible == source:
                continue  # INV-MSG-2 : la tâche qui a déclenché ce tour est déjà informée
            # Ouverte au sens large : une tâche « terminée, à valider » reçoit encore (constat du
            # 14/11 : une tâche d'intégration qui s'était déclarée terminée a manqué une branche).
            if not self.vault.ouverte(taches[cible]):
                continue
            try:
                self.soumettre(cible, texte, sauts=sauts, source=ident)
            except ErreurOrch as e:
                log.info("propagation %s -> %s non transmise : %s", ident, cible, e)
