"""Premiers pas (INV-PREMIERS-PAS-1) : état de chaque assistant IA lu sur un poste factice, commande et page
officielle pour celui qui manque, proposition au seul premier lancement, routes sous la garde de l'accueil."""

import pytest
from fastapi.testclient import TestClient

from conftest import PORT
from orchestrateur import api, installation, premiers_pas
from orchestrateur.moteur import Moteur
from test_installation import Faux

H = {"X-Orchestrateur": "1"}


def _par_id(liste):
    return {a["id"]: a for a in liste}


def test_assistants_installe_absent_a_connecter_et_hors_catalogue():
    poste = Faux(presents=("python", "git", "node", "claude", "codex"), connectes=("claude",))
    liste = _par_id(premiers_pas.assistants(installation.Assistant(poste), {"claude": 1, "codex": 1, "faux": 1}))
    assert liste["claude"]["installe"] and liste["claude"]["connexion"] == "ok" and liste["claude"]["pilotable"]
    assert liste["codex"]["connexion"] == "a_connecter" and not liste["codex"]["pilotable"]
    assert "codex" in liste["codex"]["aide_connexion"]
    absent = liste["opencode"]
    assert not absent["installe"] and not absent["pilotable"] and absent["commande"] and absent["lien"].startswith("https://")
    assert liste["faux"]["pilotable"] and liste["faux"]["installe"]  # posé à la main dans la configuration


def test_assistant_installe_mais_non_pilotable_hors_registre():
    poste = Faux(presents=("python", "git", "claude"), connectes=("claude",))
    liste = _par_id(premiers_pas.assistants(installation.Assistant(poste), {}))
    assert liste["claude"]["installe"] and not liste["claude"]["pilotable"]


def test_sans_node_l_assistant_attend_node():
    liste = _par_id(premiers_pas.assistants(installation.Assistant(Faux()), {}))
    assert "node" in liste["codex"]["attend"] and not liste["codex"]["installe"]


@pytest.fixture
def client(config, vault, faux, monkeypatch):
    monkeypatch.setattr(installation, "Systeme", lambda: Faux())
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_propose_seulement_vault_vide_et_premiers_pas_non_faits(client, config, racine):
    assert client.get("/api/accueil/premiers-pas").json() == {"propose": False, "etat": "jamais"}  # vault déjà garni
    for f in racine.rglob("taches/*.md"):
        f.unlink()
    lu = client.get("/api/accueil/premiers-pas").json()
    assert lu["propose"] is True
    assert client.post("/api/accueil/premiers-pas/fait", headers=H).json() == {"etat": "fait"}
    assert (config.donnees / "etat" / "premiers-pas.json").exists()
    assert client.get("/api/accueil/premiers-pas").json() == {"propose": False, "etat": "fait"}


def test_assistants_par_la_route(client):
    r = client.get("/api/accueil/premiers-pas/assistants").json()
    assert r["defaut"] == "faux"
    ids = [a["id"] for a in r["assistants"]]
    assert ids[:len(installation.HARNAIS_CHOISIS)] == list(installation.HARNAIS_CHOISIS) and "faux" in ids


def test_routes_sous_la_garde_de_l_accueil():
    assert premiers_pas.ROUTE.startswith("/api/accueil/")
