"""Verrou Paperclip (INV-VAULT-4) levé par configuration, sans toucher aux fichiers."""

from dataclasses import replace

from conftest import ecrire, tache_md
from orchestrateur.vault import Tache, Vault


def test_verrou_paperclip_leve_par_configuration(config, racine):
    chemin = ecrire(racine, "Projets/C1-Alpha/taches/pilotee.md", tache_md(extra="paperclip: abc\n"))
    avant = chemin.read_bytes()
    try:
        assert Vault(config.vault).tache("pilotee").verrouille
        libre = Vault(replace(config.vault, verrou_paperclip=False))
        assert not libre.tache("pilotee").verrouille
        libre.poser_statut("pilotee", "en-cours")
        assert libre.tache("pilotee").statut == "en-cours"
        assert b"paperclip: abc" in chemin.read_bytes() and chemin.read_bytes() != avant
    finally:
        Tache.verrou_actif = True
