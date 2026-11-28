"""Étiquette automatique « recent » : entrée sur geste humain (création, message, relance), jamais pour un agent
ou une routine, sortie à la clôture et par « Non prioritaire », retour à la réouverture (INV-RECENT-1)."""

import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import RENDU

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
HA = {**H, "X-Orch-Tache": "enfant"}


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def attendre(condition):
    for _ in range(300):
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("délai dépassé")


def inactif(client, ident):
    attendre(lambda: client.get(f"/api/taches/{ident}").json()["etat_execution"] in ("inactif", "interrompu"))


def mots(vault, ident):
    return vault.tache(ident).fm.get("etiquettes") or []


def test_creation_par_l_utilisateur_pose_recent(client, vault):
    r = client.post("/api/taches", headers=H, json={"titre": "Préparer le bilan"})
    assert r.status_code == 201 and r.json()["etiquettes"] == ["recent"]
    assert mots(vault, r.json()["id"]) == ["recent"]


def test_creation_par_un_agent_ne_pose_pas_recent(client, vault):
    r = client.post("/api/taches", headers=HA, json={"titre": "Sous-travail", "description": "Détail utile à l'agent suivant."})
    assert r.status_code == 201 and mots(vault, r.json()["id"]) == []


def test_message_de_l_utilisateur_pose_recent(client, vault):
    assert client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"}).status_code == 202
    assert mots(vault, "mere") == ["recent"]


def test_message_d_un_agent_ne_pose_pas_recent(client, vault):
    assert client.post("/api/taches/petit/messages", headers=HA, json={"texte": "go"}).status_code == 202
    assert mots(vault, "petit") == []


def test_relance_de_l_utilisateur_pose_recent(client, vault, faux):
    faux.scenario = [Evenement("session", session="s-2"), "attendre"]
    client.post("/api/taches/mere/messages", headers=HA, json={"texte": "go"})
    attendre(lambda: vault.tache("mere").fm.get("session") == "s-2")
    client.post("/api/taches/mere/arret", headers=H)
    attendre(lambda: client.get("/api/taches/mere").json()["etat_execution"] == "interrompu")
    assert mots(vault, "mere") == []
    faux.scenario = [Evenement("fin", session="s-2", texte=RENDU)]
    assert client.post("/api/taches/mere/relancer", headers=H).status_code == 202
    assert mots(vault, "mere") == ["recent"]


def test_execution_de_routine_ne_pose_pas_recent(client, vault):
    r = client.post("/api/routines", headers=H, json={"titre": "Veille", "consigne": "Lis.", "programme": "en semaine 09:00",
                                                       "conteneur": "Projets/C1-Alpha", "harnais": "faux"})
    ident = r.json()["id"]
    assert client.post(f"/api/routines/{ident}/executer", headers=H).status_code == 202
    inactif(client, ident)
    assert mots(vault, ident) == []


def test_statut_fait_retire_recent_et_reouverture_humaine_le_rend(client, vault):
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    inactif(client, "mere")
    client.post("/api/taches/mere/statut", headers=H, json={"statut": "fait"})
    assert mots(vault, "mere") == []
    client.post("/api/taches/mere/statut", headers=H, json={"statut": "a-faire"})
    assert mots(vault, "mere") == ["recent"]


def test_reouverture_par_un_agent_ne_rend_pas_recent(vault):
    vault.poser_statut("fermee", "a-faire")  # humain=False : tour automatique, reprise d'office
    assert mots(vault, "fermee") == []


def test_non_prioritaire_retire_recent_sans_toucher_aux_autres(client, vault):
    client.post("/api/taches/mere/etiquettes", headers=H, json={"ajouter": ["banque"]})
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    r = client.post("/api/taches/mere/etiquettes", headers=H, json={"retirer": ["recent"]})
    assert r.json()["etiquettes"] == ["banque"]


def test_pastille_et_vue_listent_les_recentes(client):
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    client.post("/api/taches", headers=H, json={"titre": "Autre tâche"})
    assert client.get("/api/etat").json()["recent"] == 2
    vue = client.get("/api/etiquettes/recent/vue").json()
    assert {x["id"] for x in vue["taches"]} >= {"mere"} and len(vue["taches"]) == 2
