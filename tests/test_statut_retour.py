"""INV-STATUT-1 : statut de retour réglable (`[vault] statut_retour`), jamais deviné."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, decisions
from orchestrateur.config import ConfigVault
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide, Vault
from test_api import H

T = "Projets/C1-Alpha/taches/"


def test_defaut_neutre_et_toujours_ouvert(tmp_path):
    c = ConfigVault(racine=tmp_path, taches=[])
    assert c.statut_retour == "retour-humain" and "retour-humain" in c.statuts_ouverts
    autre = ConfigVault(racine=tmp_path, taches=[], statuts_ouverts=["a-faire"], statut_retour="retour-alice")
    assert autre.statuts_ouverts == ["a-faire", "retour-alice"]


@pytest.mark.parametrize("nom", ["", "fait", "bloque", "Retour Alice", "retour_alice", "-retour"])
def test_nom_invalide_ou_deja_pris_refuse(tmp_path, nom):
    with pytest.raises(ValueError, match="statut_retour"):
        ConfigVault(racine=tmp_path, taches=[], statut_retour=nom)


@pytest.fixture
def ancien(config, racine, faux):
    """Vault qui garde un ancien nom, déclaré dans la configuration."""
    config.vault = replace(config.vault, statut_retour="retour-alice",
                           statuts_ouverts=["a-faire", "en-cours", "confier-agent", "bloque"])
    ecrire(racine, T + "declare.md", tache_md("retour-alice", titre="Déclaré"))
    ecrire(racine, T + "autre.md", tache_md("retour-humain", titre="Autre nom"))
    v = Vault(config.vault)
    return Moteur(config, v, {"faux": faux})


def test_nom_declare_reconnu_partout(ancien):
    v = ancien.vault
    assert v.statut_declare("en_attente") == "retour-alice"
    assert v.ouverte(v.tache("declare"))
    genres = {d["tache"]: d["genre"] for d in decisions.rassembler(ancien)["decisions"]}
    assert genres.get("declare") == "reponse"
    from orchestrateur import etat_main
    assert "declare" in etat_main.humain_par_id(ancien)  # INV-MAIN-4 : À moi = états « action humaine »
    v.poser_statut("mere", "retour-alice")
    assert v.tache("mere").statut == "retour-alice"


def test_statut_inconnu_jamais_pris_pour_le_retour(ancien):
    v = ancien.vault
    assert not v.ouverte(v.tache("autre"))
    assert "autre" not in {d["tache"] for d in decisions.rassembler(ancien)["decisions"]}
    with pytest.raises(Invalide):
        v.poser_statut("mere", "retour-humain")


def test_interface_recoit_le_nom_du_serveur(ancien, config):
    app = api.creer_app(config, ancien)
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        assert c.get("/api/interface").json()["statut_retour"] == "retour-alice"
        assert c.put("/api/interface", headers=H, json={"mode": "avance"}).json()["statut_retour"] == "retour-alice"
