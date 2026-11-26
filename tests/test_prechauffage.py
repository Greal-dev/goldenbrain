"""Préchauffage (INV-FROID-1) : les caches du premier écran sont remplis au démarrage, sans jamais bloquer le serveur."""

from orchestrateur import prechauffage
from orchestrateur.moteur import Moteur


def test_prechauffage_remplit_les_caches_de_l_index(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    assert not vault._cache  # cache de lecture vide à froid
    prechauffage.chauffer(m)
    assert vault._cache


def test_prechauffage_ne_leve_jamais(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.vault = None  # démarrage cassé : le préchauffage journalise et rend la main
    prechauffage.chauffer(m)
