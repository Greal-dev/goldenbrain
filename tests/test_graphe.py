"""Second cerveau : mentions non liées (INV-NOTE-4) et graphe (INV-GRAPHE-1, INV-GRAPHE-2)."""

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire
from orchestrateur import api, graphe
from orchestrateur.config import ConfigNotes
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md",
           "---\ntype: tache\nstatut: a-faire\nalimente: [enfant]\ntags: []\n---\n\n# Mère\n\n"
           "Voir [[Concept Graphe]].\n")
    ecrire(racine, "Ressources/Concept Graphe.md",
           "---\ntype: concept\ntags: [cerveau, graphe]\n---\n# Concept Graphe\nRenvoie à [[Personne]].\n")
    ecrire(racine, "Ressources/Personne.md", "---\ntype: personne\ntags:\n  - équipe\n---\n# Personne\n")
    ecrire(racine, "Ressources/Lecture.md",
           "# Lecture\nUn passage sur le concept graphe, sans lien.\nAussi Personnelle.\n")
    ecrire(racine, "Ressources/Isolee.md", "# Isolée\n")
    config.notes = ConfigNotes(exclure=[], ttl_s=0.2)
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def _g(client, **params):
    r = client.get("/api/vault/graphe", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _aretes(g):
    ids = [n["id"] for n in g["noeuds"]]
    return {(ids[a], ids[b], genre) for a, b, genre in g["liens"]}


def test_mentions_non_liees_mot_entier_sans_les_notes_qui_lient(client):
    m = client.get("/api/vault/mentions", params={"chemin": "Ressources/Concept Graphe.md"}).json()
    assert [x["chemin"] for x in m] == ["Ressources/Lecture.md"]  # mère le lie déjà
    assert "concept graphe" in m[0]["extrait"]
    # « Personnelle » ne compte pas comme mention de « Personne » (mot entier).
    assert client.get("/api/vault/mentions", params={"chemin": "Ressources/Personne.md"}).json() == []


def test_graphe_global_noeuds_genres_et_aretes(client):
    g = _g(client)
    par_id = {n["id"]: n for n in g["noeuds"]}
    assert par_id["Projets/C1-Alpha/taches/mere.md"]["genre"] == "tache"
    assert par_id["Projets/C1-Alpha/taches/mere.md"]["tache"] == "mere"
    assert par_id["Projets/C1-Alpha/contexte.md"]["genre"] == "conteneur"
    assert par_id["Ressources/Personne.md"]["genre"] == "note"
    a = _aretes(g)
    assert ("Projets/C1-Alpha/taches/mere.md", "Ressources/Concept Graphe.md", "lien") in a
    assert ("Projets/C1-Alpha/taches/mere.md", "Projets/C1-Alpha/taches/enfant.md", "alimente") in a
    assert ("Projets/C1-Alpha/taches/mere.md", "Projets/C1-Alpha/contexte.md", "appartient") in a
    assert g["total"] == len(g["noeuds"]) and not g["tronque"]


def test_graphe_local_profondeur_un_et_deux(client):
    g1 = _g(client, centre="Ressources/Personne.md", profondeur=1)
    assert g1["centre"] == "Ressources/Personne.md"
    assert {n["id"] for n in g1["noeuds"]} == {"Ressources/Personne.md", "Ressources/Concept Graphe.md"}
    g2 = _g(client, centre="Ressources/Personne.md", profondeur=2)
    assert "Projets/C1-Alpha/taches/mere.md" in {n["id"] for n in g2["noeuds"]}
    # Une tâche se désigne aussi par son identifiant.
    assert _g(client, centre="mere")["centre"] == "Projets/C1-Alpha/taches/mere.md"
    assert _g(client, centre="inconnue")["noeuds"] == []


def test_graphe_global_filtres(client):
    assert {n["id"] for n in _g(client, tag="graphe")["noeuds"]} == {"Ressources/Concept Graphe.md"}
    assert {n["id"] for n in _g(client, tag="équipe")["noeuds"]} == set()  # tags normalisés
    assert {n["id"] for n in _g(client, tag="equipe")["noeuds"]} == {"Ressources/Personne.md"}
    assert {n["genre"] for n in _g(client, genre="tache")["noeuds"]} == {"tache"}
    assert {n["id"] for n in _g(client, type="personne")["noeuds"]} == {"Ressources/Personne.md"}
    projet = {n["projet"] for n in _g(client, projet="Projets/C1-Alpha")["noeuds"]}
    assert projet == {"Projets/C1-Alpha"}
    assert all(n["casquette"] == "C2" for n in _g(client, casquette="C2")["noeuds"])
    recents = {n["id"] for n in _g(client, jours=1)["noeuds"]}  # tout vient d'être écrit
    assert recents == {n["id"] for n in _g(client)["noeuds"] if n["id"].endswith(".md")}
    f = client.get("/api/vault/graphe/facettes").json()
    assert "graphe" in f["tags"] and "personne" in f["types"] and {"C1", "C2", "C3", "META"} <= set(f["casquettes"])


def test_graphe_plafond_garde_les_plus_relies(client, monkeypatch):
    monkeypatch.setattr(graphe, "PLAFOND", 2)
    g = _g(client, limite=50)
    assert len(g["noeuds"]) == 2 and g["tronque"] and g["total"] > 2
    degres = [n["degre"] for n in g["noeuds"]]
    assert degres == sorted(degres, reverse=True)
    assert len(_g(client, limite=1)["noeuds"]) == 1


def test_graphe_en_cache_et_perime_a_l_ecriture(client, monkeypatch):
    calculs = []
    construire = graphe.Graphe._construire
    monkeypatch.setattr(graphe.Graphe, "_construire",
                        lambda self, idx: calculs.append(1) or construire(self, idx))
    _g(client)
    _g(client, tag="graphe")
    _g(client, centre="mere")
    assert len(calculs) == 1  # servi du cache
    n = client.get("/api/vault/note", params={"chemin": "Ressources/Isolee.md"}).json()
    r = client.put("/api/vault/note", headers=H, json={
        "chemin": "Ressources/Isolee.md", "contenu": n["contenu"] + "Lien vers [[Personne]].\n",
        "mtime_ns": n["mtime_ns"]})
    assert r.status_code == 200, r.text
    assert ("Ressources/Isolee.md", "Ressources/Personne.md", "lien") in _aretes(_g(client))
    assert len(calculs) == 2
