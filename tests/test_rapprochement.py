"""Rapprochement avant création : score, classement, 409 + candidates, forcer, compléter, mesure, CLI."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, rapprochement
from orchestrateur.moteur import Moteur
from conftest import ecrire, tache_md

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
ALPHA = "Projets/C1-Alpha"


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, f"{ALPHA}/taches/porte.md", tache_md(titre="Stabiliser la porte d'interface"))
    ecrire(racine, "Projets/C2-Beta/taches/durand.md", tache_md(titre="Suivre le recouvrement Durand"))
    ecrire(racine, f"{ALPHA}/taches/ancienne.md",
           tache_md(statut="fait", extra="updated: 2020-01-01\n", titre="Stabiliser la porte d'interface hier"))
    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    ecrire(racine, f"{ALPHA}/taches/recente.md",
           tache_md(statut="fait", extra=f"updated: {aujourdhui}\n", titre="Recouvrement Durand clos"))
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def test_mots_sans_accents_ni_mots_vides():
    assert rapprochement.mots("Écrire les Échéances de la porte") == {"ecrire", "echeance", "porte"}


def test_doublon_evident_est_refuse_en_409_avec_candidates(client):
    r = client.post("/api/taches", json={"titre": "Stabiliser la porte d'interface",
                                         "conteneur": "Projets/C1-Alpha"}, headers=H)
    assert r.status_code == 409
    c = r.json()["candidates"]
    assert c[0]["id"].endswith("porte") and c[0]["forte"] and c[0]["ouverte"]
    assert client.get("/api/rapprochement/mesure").json()["evitees"] == 1


def test_forcer_cree_et_le_refus_ne_compte_plus(client):
    corps = {"titre": "Stabiliser la porte d'interface", "conteneur": "Projets/C1-Alpha"}
    assert client.post("/api/taches", json=corps, headers=H).status_code == 409
    r = client.post("/api/taches", json={**corps, "forcer": True}, headers=H)
    assert r.status_code == 201
    m = client.get("/api/rapprochement/mesure").json()
    assert m["evitees"] == 0 and m["forces_apres_refus"] == 1


def test_titre_sans_parente_cree_sans_friction(client):
    r = client.post("/api/taches", json={"titre": "Commander des ampoules pour le salon"}, headers=H)
    assert r.status_code == 201
    assert client.get("/api/rapprochement/mesure").json()["evitees"] == 0


def test_completer_ajoute_le_message_et_compte(client, faux):
    corps = {"titre": "Stabiliser la porte d'interface", "conteneur": "Projets/C1-Alpha"}
    ident = client.post("/api/taches", json=corps, headers=H).json()["candidates"][0]["id"]
    r = client.post(f"/api/rapprochement/taches/{ident}/completer",
                    json={"texte": "Ajouter le cas du délai", "titre": corps["titre"]}, headers=H)
    assert r.status_code == 202
    m = client.get("/api/rapprochement/mesure").json()
    assert m["evitees"] == 1 and m["complements"] == 1 and m["refus_non_forces"] == 0  # un seul compte


def test_proches_classe_ouvertes_d_abord_puis_closes_recentes(client):
    c = client.get("/api/rapprochement/proches", params={"titre": "Recouvrement Durand"}).json()["candidates"]
    assert [x["ouverte"] for x in c] == [True, False]  # la close de 2020 n'y est pas, la récente oui
    assert all(not x["id"].endswith("ancienne") for x in c)


def test_close_recente_est_proposee_mais_ne_bloque_jamais(client):
    r = client.post("/api/taches", json={"titre": "Recouvrement Durand clos"}, headers=H)
    assert r.status_code == 201


def test_autre_projet_propose_sans_bloquer(client):
    # deux mots sur trois en commun hors du projet : proposé (≈0,67), non bloquant
    r = client.get("/api/rapprochement/proches", params={"titre": "Corriger la porte d'interface",
                                                         "conteneur": "Projets/C2-Beta"}).json()
    assert r["candidates"] and not r["forte"]


def test_agent_ne_se_propose_pas_sa_propre_tache(client):
    r = client.post("/api/taches", json={"titre": "Stabiliser la porte d'interface", "parent": "porte",
                                         "description": "Découper le travail en lots testables."},
                    headers={**H, "X-Orch-Tache": "porte"})
    assert r.status_code == 201


def test_rendu_cli_du_409(monkeypatch, capsys):
    corps = {"candidates": [{"id": "t1", "statut": "a-faire", "titre": "Porte", "fil_ariane": ["C1"],
                             "score": 0.9, "forte": True}]}
    texte = cli.rendre_proches(corps)
    assert "t1" in texte and "orch dire <id>" in texte and "--nouvelle" in texte


def test_creer_cli_transmet_forcer(monkeypatch):
    envoyes = []
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: envoyes.append(corps) or {"id": "n", "titre": "T"})
    assert cli.main(["creer", "T", "--description", "Une phrase de description ici.", "--nouvelle"]) == 0
    assert envoyes[0]["forcer"] is True
