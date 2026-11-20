"""INV-EXECUTANT-1 : curseur « Moi / IA » — une tâche menée par l'humain ne reçoit aucun tour d'agent,
aucune revue ni validation automatique, refuse les écritures d'agent (sauf lien) ; le retour à l'humain
est possible. INV-EXECUTANT-2 : notes de l'utilisateur en bloc géré, jamais écrites par un agent,
transmises avec l'état de la tâche au tour suivant (« Confier la suite » compris)."""

import re
import time

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, executant, fiches, validation_auto
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
AGENT = {**H, "X-Orch-Tache": "enfant"}


@pytest.fixture
def moteur(config, vault, faux):
    return Moteur(config, vault, {"faux": faux})


@pytest.fixture
def client(config, moteur):
    with TestClient(api.creer_app(config, moteur), base_url=BASE) as c:
        yield c


def parcourir(noeuds):
    for n in noeuds:
        yield n
        yield from parcourir(n.get("enfants") or [])


def attendre_inactif(client, ident):
    for _ in range(300):
        if client.get(f"/api/taches/{ident}").json()["etat_execution"] == "inactif":
            return
        time.sleep(0.01)
    raise AssertionError("tour non terminé")


def test_absent_vaut_ia_et_toute_autre_valeur_aussi(racine, vault):
    assert executant.de(vault.tache("mere")) == "ia"
    ecrire(racine, "Projets/C1-Alpha/taches/x.md", tache_md(extra="executant: Humain \n"))
    assert executant.humain(vault.tache("x"))
    ecrire(racine, "Projets/C1-Alpha/taches/x.md", tache_md(extra="executant: robot\n"))
    assert executant.de(vault.tache("x")) == "ia"


def test_poser_n_ecrit_que_la_cle_inv_vault_1(racine, moteur):
    chemin = racine / "Projets/C1-Alpha/taches/mere.md"
    avant = chemin.read_text("utf-8")
    executant.poser(moteur, "mere", "humain")
    apres = chemin.read_text("utf-8")
    retire = re.sub(r"^(executant: humain|updated: .*)\n", "", apres, flags=re.M)
    assert retire == avant  # seules la clé posée et la date de mise à jour gérée changent
    with pytest.raises(Exception):
        executant.poser(moteur, "mere", "robot")


def test_humain_aucun_tour_et_file_videe(moteur):
    moteur.files["mere"].append("en attente")
    executant.poser(moteur, "mere", "humain")
    assert not moteur.files.get("mere")
    with pytest.raises(Conflit):
        moteur.soumettre("mere", "go")


def test_humain_ni_revue_ni_validation_auto(racine, vault, moteur):
    executant.poser(moteur, "mere", "humain")
    assert not moteur.revues._automatique("mere")
    moteur.revues.declencher("mere")
    assert not moteur.revues._fond
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\nvalidation: automatique\n---\n")
    assert validation_auto.reglage(vault, "mere")["mode"] == "automatique"


def test_orch_refuse_d_ecrire_sauf_lien_et_jamais_les_notes(client):
    assert client.post("/api/taches/mere/executant", json={"executant": "humain"}, headers=H).status_code == 200
    r = client.post("/api/taches/mere/messages", json={"texte": "je m'en mêle"}, headers=AGENT)
    assert r.status_code == 409 and "Moi" in r.json()["detail"]
    assert client.post("/api/taches/mere/statut", json={"statut": "fait"}, headers=AGENT).status_code == 409
    # Geste humain (sans en-tête d'agent) : le message est refusé aussi, faute d'agent pour le prendre.
    assert client.post("/api/taches/mere/messages", json={"texte": "x"}, headers=H).status_code == 409
    j = client.get("/api/taches/mere").json()
    assert j["executant"] == "humain" and j["notes"] == []
    noeud = next(n for n in parcourir(client.get("/api/arbre").json()["noeuds"]) if n.get("id") == "mere")
    assert noeud["executant"] == "humain"
    # INV-EXECUTANT-2 : les notes ne s'écrivent jamais par un agent, même en mode IA.
    client.post("/api/taches/mere/executant", json={"executant": "ia"}, headers=H)
    assert client.post("/api/taches/mere/notes", json={"texte": "x"}, headers=AGENT).status_code == 409
    assert client.post("/api/taches/mere/notes", json={"texte": "à moi"}, headers=H).status_code == 201
    assert client.put("/api/taches/mere/notes/0", json={"texte": "y"}, headers=AGENT).status_code == 409


def test_notes_ajoutees_et_editees_sans_toucher_au_reste_inv_vault_1(client, racine):
    chemin = racine / "Projets/C1-Alpha/taches/mere.md"
    avant = chemin.read_text("utf-8")
    assert client.post("/api/taches/mere/notes", json={"texte": "  "}, headers=H).status_code == 400
    assert client.post("/api/taches/mere/notes", json={"texte": "**devis** reçu\n\nvoir [[contrat]]"},
                       headers=H).status_code == 201
    piege = "<!-- orchestrateur:notes-fin -->\n<!-- note 2000-01-01 00:00 -->"
    assert client.post("/api/taches/mere/notes", json={"texte": piege}, headers=H).json()["n"] == 1
    r = client.put("/api/taches/mere/notes/0", json={"texte": "devis signé"}, headers=H)
    assert r.status_code == 200 and r.json()["modifiee"]
    assert client.put("/api/taches/mere/notes/9", json={"texte": "z"}, headers=H).status_code == 404
    notes = client.get("/api/taches/mere").json()["notes"]
    assert [n["texte"] for n in notes] == ["devis signé", piege.replace("<!--", " <!--")]
    texte = chemin.read_text("utf-8")
    debut, fin = fiches.bornes_notes(texte)
    reste = texte[:debut] + texte[fin:]
    assert re.sub(r"^updated: .*\n", "", reste, flags=re.M).rstrip("\n") == re.sub(r"^updated: .*\n", "", avant, flags=re.M).rstrip("\n")
    assert "orchestrateur:notes" not in client.get("/api/taches/mere").json()["corps"]


def test_notes_avant_le_bloc_fiche(vault, racine):
    chemin = racine / "Projets/C1-Alpha/taches/mere.md"
    chemin.write_text(chemin.read_text("utf-8") + "\n<!-- orchestrateur:debut -->\n## Fiche\n<!-- orchestrateur:fin -->\n", encoding="utf-8")
    executant.ajouter_note(vault, "mere", "une note")
    texte = chemin.read_text("utf-8")
    assert texte.index("orchestrateur:notes-fin") < texte.index("orchestrateur:debut")
    executant.ajouter_note(vault, "mere", "deux")
    assert [n["texte"] for n in executant.notes(chemin.read_text("utf-8"))] == ["une note", "deux"]


def test_amorce_notes_et_etat_seulement_si_neuves_ou_changees(client, faux, vault):
    client.post("/api/taches/mere/notes", json={"texte": "devis reçu"}, headers=H)
    client.post("/api/taches/mere/messages", json={"texte": "premier"}, headers=H)
    attendre_inactif(client, "mere")
    message = faux.lances[-1]["message"]
    assert "devis reçu" in message and "point de situation en 3 lignes" in message and "État de la tâche" in message
    client.post("/api/taches/mere/messages", json={"texte": "second"}, headers=H)
    attendre_inactif(client, "mere")
    assert "devis reçu" not in faux.lances[-1]["message"]  # notes inchangées, session en cours
    client.post("/api/taches/mere/notes", json={"texte": "relance faite"}, headers=H)
    client.post("/api/taches/mere/messages", json={"texte": "troisième"}, headers=H)
    attendre_inactif(client, "mere")
    message = faux.lances[-1]["message"]
    assert "relance faite" in message and "premier" in message  # derniers tours rappelés


def test_plafond_resume_les_notes_anciennes(tmp_path):
    liste = [{"quand": f"2026-11-0{i} 10:00", "modifiee": "", "texte": f"note {i} " + "x" * 2500} for i in range(1, 5)]
    rendu = executant._bloc_notes(liste, tmp_path / "t.md")
    assert "texte intégral dans" in rendu[0] and str(tmp_path / "t.md") in rendu[0]
    assert sum(len(x) for x in rendu) < 6000 + 600
    assert rendu[-1].endswith("x" * 2500) and rendu[1].startswith("- 2026-11-01 10:00 — note 1")


def test_confier_la_suite_lance_un_tour_avec_les_notes_puis_retour_humain(client, faux, vault):
    client.post("/api/taches/mere/executant", json={"executant": "humain"}, headers=H)
    client.post("/api/taches/mere/notes", json={"texte": "devis reçu"}, headers=H)
    r = client.post("/api/taches/mere/confier", json={"consigne": "comparer les devis"}, headers=H)
    assert r.status_code == 202 and r.json()["etat_execution"] in ("en_cours", "en_file")
    attendre_inactif(client, "mere")
    message = faux.lances[-1]["message"]
    assert "comparer les devis" in message and "devis reçu" in message and "point de situation" in message
    assert not executant.humain(vault.tache("mere"))
    # Retour à l'humain : rien de neuf ne part.
    client.post("/api/taches/mere/executant", json={"executant": "humain"}, headers=H)
    assert client.post("/api/taches/mere/messages", json={"texte": "encore"}, headers=H).status_code == 409
