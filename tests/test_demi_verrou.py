"""INV-VERROU-1 : occupation d'une tâche par un agent, demi-verrou des gestes humains (409
`occupee` sauf `forcer`), messages et arrêt libres, INV-ALIGN-2 jamais outrepassé."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def client(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url=BASE) as c:
        yield c


def occuper(client, ident: str) -> None:
    client.app.state.moteur.etats[ident] = "en_cours"


def note(client, chemin: str) -> dict:
    return client.get("/api/vault/note", params={"chemin": chemin}).json()


# --- occupation -----------------------------------------------------------------------------
def test_occupation_none_puis_dict_pendant_un_tour(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-1"), "attendre"]

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        assert m.occupation("mere") is None and m.occupees() == {}
        m.soumettre("mere", "travaille")
        en_file = m.occupation("mere")
        assert en_file["tache"] == "mere" and en_file["titre"] == "Mère" and en_file["depuis"]
        while "mere" not in m.tours:
            await asyncio.sleep(0.01)
        o = m.occupation("mere")
        assert o == {"tache": "mere", "titre": "Mère", "depuis": m.tours["mere"].depuis,
                     "moteur": "faux"}
        assert m.etat_global()["occupees"] == {"mere": o}
        await m.arreter("mere")
        while any(not b.done() for b in m.boucles.values()):
            await asyncio.sleep(0.01)
        m.etats["mere"] = "inactif"
        assert m.occupation("mere") is None and m.etat_global()["occupees"] == {}

    asyncio.run(scenario())


def test_occupees_sous_descendance_par_projet_et_par_parent(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.etats["petit"] = "en_file"  # petit -> enfant -> mere, dans Projets/C1-Alpha
    for noeud in ("petit", "enfant", "mere", "Projets/C1-Alpha", "casquette:C1"):
        assert [o["tache"] for o in m.occupees_sous(noeud)] == ["petit"], noeud
    assert m.occupees_sous("Projets/C2-Beta") == []
    assert m.occupees_sous("doublon") == []


# --- routes gardées : 409 `occupee` sans forcer, succès avec ---------------------------------
def garde(client, methode, chemin, corps, occupee):
    r = client.request(methode, chemin, headers=H, json=corps)
    assert r.status_code == 409, r.text
    assert r.json()["occupee"]["tache"] == occupee
    assert r.json()["detail"].startswith("Un agent travaille sur « ")
    r = client.request(methode, chemin, headers=H, json={**corps, "forcer": True})
    assert r.status_code in (200, 202), r.text
    return r


def test_arbre_deplacer_et_monter(client):
    occuper(client, "petit")
    garde(client, "POST", "/api/arbre/deplacer", {"noeud": "mere", "sous": "Projets/C2-Beta"},
          "petit")
    garde(client, "POST", "/api/arbre/monter", {"noeud": "petit"}, "petit")


def test_arbre_plan_d_un_projet_dont_une_descendante_travaille(client):
    occuper(client, "petit")
    r = garde(client, "POST", "/api/arbre/plan", {"noeud": "Projets/C1-Alpha",
                                                   "sous": "casquette:C2"}, "petit")
    assert "jeton" in r.json()


def test_taches_deplacer(client):
    occuper(client, "petit")
    garde(client, "POST", "/api/taches/mere/deplacer", {"conteneur": "Projets/C2-Beta"}, "petit")


def test_taches_promouvoir(config, vault, faux):
    config.vault.taches.append("Projets/*/*/taches/*.md")  # le projet né doit être visible
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url=BASE) as c:
        occuper(c, "doublon")
        garde(c, "POST", "/api/taches/doublon/promouvoir", {"decouper": False}, "doublon")


def test_statut_valider_renvoyer_tache_seule(client):
    occuper(client, "enfant")
    # La tâche seule : une descendante au travail ne garde pas le statut de sa mère.
    r = client.post("/api/taches/mere/statut", headers=H, json={"statut": "en-cours"})
    assert r.status_code == 200
    garde(client, "POST", "/api/taches/enfant/statut", {"statut": "en-cours"}, "enfant")
    client.post("/api/taches/enfant/statut", headers=H, json={"statut": "fait", "forcer": True})  # B6 : on ne valide que le « fait »
    garde(client, "POST", "/api/taches/enfant/valider", {}, "enfant")
    client.post("/api/taches/enfant/statut", headers=H, json={"statut": "fait", "forcer": True})  # rouverte : renvoyer une close est refusé
    garde(client, "POST", "/api/taches/enfant/renvoyer", {"texte": "reprends"}, "enfant")


def test_valider_sans_corps_reste_admis(client):
    client.post("/api/taches/mere/statut", headers=H, json={"statut": "fait"})
    assert client.post("/api/taches/mere/valider", headers=H).status_code == 200


def test_edition_de_note_de_tache_et_de_contexte(client):
    occuper(client, "mere")
    n = note(client, "Projets/C1-Alpha/taches/mere.md")
    garde(client, "PUT", "/api/vault/note", {"chemin": n["chemin"], "contenu": n["contenu"] + "x\n",
                                             "mtime_ns": n["mtime_ns"]}, "mere")
    c = note(client, "Projets/C1-Alpha/contexte.md")
    garde(client, "PUT", "/api/vault/note", {"chemin": c["chemin"], "contenu": c["contenu"] + "x\n",
                                             "mtime_ns": c["mtime_ns"]}, "mere")
    autre = note(client, "Projets/C2-Beta/taches/doublon.md")
    r = client.put("/api/vault/note", headers=H, json={
        "chemin": autre["chemin"], "contenu": autre["contenu"] + "x\n", "mtime_ns": autre["mtime_ns"]})
    assert r.status_code == 200  # aucune tâche occupée : rien à confirmer


def test_renommage_de_note_garde_la_descendance(client):
    occuper(client, "enfant")
    garde(client, "POST", "/api/vault/note/deplacer",
          {"chemin": "Projets/C1-Alpha/taches/mere.md", "vers": "Projets/C2-Beta/taches/mere.md"},
          "enfant")


# --- libres et verrou dur ---------------------------------------------------------------------
def test_messages_et_arret_restent_libres(client):
    occuper(client, "mere")
    assert client.post("/api/taches/mere/messages", headers=H,
                       json={"texte": "encore"}).status_code == 202
    assert client.post("/api/taches/mere/arret", headers=H).status_code == 200


def test_forcer_n_outrepasse_pas_inv_align_2_a_la_reduction(client, config):
    occuper(client, "petit")
    r = client.post("/api/conteneurs/reduire", headers=H,
                    json={"conteneur": "Projets/C1-Alpha", "point_git": False})
    assert r.status_code == 409 and r.json()["occupee"]["tache"] == "petit"
    r = client.post("/api/conteneurs/reduire", headers=H,
                    json={"conteneur": "Projets/C1-Alpha", "point_git": False, "forcer": True})
    assert r.status_code == 409 and "occupee" not in r.json()
    assert "Petit" in r.json()["detail"]
    assert (config.vault.racine / "Projets/C1-Alpha/contexte.md").is_file()


def test_etat_expose_les_occupees(client):
    occuper(client, "mere")
    for _ in range(50):
        o = client.get("/api/etat").json()["occupees"]
        if o:
            break
        time.sleep(0.01)
    assert o["mere"]["titre"] == "Mère" and o["mere"]["moteur"] == "faux"
