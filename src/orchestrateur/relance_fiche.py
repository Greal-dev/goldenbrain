"""Fiche absente ≠ question : relance automatique bornée, puis `bloque` motivé.

Rôle : juger la fin d'un tour réussi qui ne rend aucun bloc `<fiche>` (texte libre, ou résultat vide) :
la première fois, redemander la fiche (le moteur resoumet `MESSAGE`) ; la seconde, bloquer la tâche avec
un motif lisible. Compter ces cas (`public`).
Frontières : ne touche ni au vault ni à la file (le moteur applique le verdict) ; un tour arrêté à la main
ou en échec n'est jamais jugé ici.
Invariants portés : INV-EXEC-12 (au plus une relance de fiche par tâche et par panne ; jamais de retour
vers l'utilisateur sur une simple fiche manquante).
"""

from __future__ import annotations

import logging

from . import fiches
from .vault import ErreurOrch

log = logging.getLogger(__name__)

MESSAGE = ("[GoldenBrain — fiche manquante] Ton dernier message ne se termine pas par le bloc <fiche>. "
           "Ne refais pas le travail : rends seulement le bloc <fiche> final (statut, fait, resultat, essai, "
           "situation, reste, prochain_pas, sous_taches). Statut en_attente uniquement si une décision de "
           "l'utilisateur est réellement requise.")
MOTIF = "fiche absente après relance : l'agent n'a pas rendu son bloc <fiche>"


class RelanceFiche:
    def __init__(self):
        self.relancees: set[str] = set()  # tâches déjà relancées, tant que leur fiche manque
        self.compte = {"absentes": 0, "relancees": 0, "bloquees": 0}

    def juger(self, ident: str, final: str | None) -> str | None:
        """None (fiche présente), `relancer` ou `bloquer`."""
        if final is not None and fiches.analyser_rendu(final) is not None:
            self.relancees.discard(ident)
            return None
        self.compte["absentes"] += 1
        if ident in self.relancees:
            self.relancees.discard(ident)
            self.compte["bloquees"] += 1
            return "bloquer"
        self.relancees.add(ident)
        self.compte["relancees"] += 1
        return "relancer"

    def public(self) -> dict:
        return dict(self.compte)


def redemander(moteur, ident: str) -> None:
    """Remet dans la file de la tâche la demande de fiche ; un refus de la file se journalise."""
    try:
        moteur.soumettre(ident, MESSAGE)
    except ErreurOrch as e:
        log.warning("relance de fiche de %s impossible : %s", ident, e)
