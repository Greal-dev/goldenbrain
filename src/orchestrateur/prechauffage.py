"""Préchauffage du premier écran : index du vault, arbre et état global lus une fois avant d'accepter une requête.

Rôle : à froid, la première lecture de l'index (frontmatter de chaque fiche) coûtait 3,5 s au premier affichage.
Frontières : lecture seule, aucune écriture ; une erreur n'empêche jamais le démarrage (journal, puis on continue).
Invariant porté : INV-FROID-1.
"""

import logging

from . import etat_main

log = logging.getLogger(__name__)


def chauffer(moteur) -> None:
    """INV-FROID-1 : remplit les caches (méta des fiches, états) que lit le premier chargement de l'interface."""
    try:
        taches = moteur.vault.index()[0]
        etat_main.annoter(moteur, moteur.vault.arbre(False, moteur.etat_de))
        moteur.etat_global()
        log.info("préchauffage : %d tâches lues", len(taches))
    except Exception:  # noqa: BLE001 — le préchauffage ne doit jamais empêcher le démarrage
        log.exception("préchauffage ignoré")
