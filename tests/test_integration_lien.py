"""INV-INTEG-2 : une tâche créée par l'API (interface, `orch creer`, `orch deleguer`) dans un projet qui
déclare `integration:` alimente d'office sa tâche d'intégration ; jamais bloquant."""

import pytest
from fastapi.testclient import TestClient

from conftest import PORT, ecrire
from orchestrateur import api
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}
CTX = "---\ntype: contexte\ncasquette: C1-Pro\nparent: \"[[Operation-X]]\"\nnom: Alpha\nintegration: {cible}\n---\n"


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def _creer(client, **corps):
    r = client.post("/api/taches", json={"forcer": True, **corps}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_tache_creee_alimente_l_integration_declaree(client, vault, racine):
    ecrire(racine, "Projets/C1-Alpha/contexte.md", CTX.format(cible="mere"))
    ident = _creer(client, titre="Livrer une branche", conteneur="Projets/C1-Alpha")
    assert vault.tache(ident).fm.get("alimente") == ["mere"]
    beta = _creer(client, titre="Sans intégration", conteneur="Projets/C2-Beta")
    assert not vault.tache(beta).fm.get("alimente")  # projet sans déclaration : rien


def test_enfant_de_l_integration_ou_d_une_tache_qui_l_alimente_n_est_pas_double(client, vault, racine):
    ecrire(racine, "Projets/C1-Alpha/contexte.md", CTX.format(cible="mere"))
    assert not vault.tache(_creer(client, titre="Sous-agent", parent="mere")).fm.get("alimente")
    vault.modifier("enfant", {"alimente": ["mere"]})
    assert not vault.tache(_creer(client, titre="Sous-sous-agent", parent="enfant")).fm.get("alimente")


def test_cible_absente_n_empeche_pas_la_creation(client, vault, racine):
    ecrire(racine, "Projets/C1-Alpha/contexte.md", CTX.format(cible="introuvable"))
    assert not vault.tache(_creer(client, titre="Quand même", conteneur="Projets/C1-Alpha")).fm.get("alimente")
