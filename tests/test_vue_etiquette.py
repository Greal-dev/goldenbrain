"""Vue par étiquette : tâches et routines réunies en une lecture, résultat de fiche, dernière et prochaine exécution,
mot inconnu, lecture seule (INV-ETIQUETTE-4)."""

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, vue_etiquette
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
ALPHA = "Projets/C1-Alpha/taches"
BLOC = ("\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : {fait}\n- **Résultat** : {res}\n"
        "- **Essai** : \n- **Situation** : \n- **Reste à faire** : \n- **Prochain pas** : \n<!-- orchestrateur:fin -->\n")


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, f"{ALPHA}/va.md", tache_md(titre="Relevés banque", extra="etiquettes: [banque, loyers]\n")
           + BLOC.format(fait="rien", res="Solde conforme. Deux écarts à voir."))
    ecrire(racine, f"{ALPHA}/vb.md", tache_md(statut="fait", titre="Ancien rapprochement", extra="etiquettes: [banque]\nupdated: 2020-01-01\n"))
    ecrire(racine, f"{ALPHA}/vc.md", tache_md(titre="Sans lien", extra="etiquettes: [maison]\n"))
    ecrire(racine, f"{ALPHA}/vd.md", tache_md(titre="Seulement fait", extra="etiquettes: [banque]\n")
           + BLOC.format(fait="Export téléchargé", res=""))
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def _routine(c, titre="Contrôle bancaire", mot="banque"):
    corps = {"titre": titre, "consigne": "Contrôle.", "programme": "chaque jour 08:00", "conteneur": "Projets/C1-Alpha", "harnais": "faux"}
    ident = c.post("/api/routines", json=corps, headers=H).json()["id"]
    assert c.post(f"/api/taches/{ident}/etiquettes", json={"ajouter": [mot]}, headers=H).status_code == 200
    return ident


def test_vue_reunit_taches_et_routines_routines_d_abord(client):
    rid = _routine(client)
    d = client.get("/api/etiquettes/banque/vue").json()
    ids = [x["id"] for x in d["taches"]]
    assert ids[0] == rid and set(ids) == {rid, "va", "vd"}  # fermée ancienne et autre étiquette exclues
    va = next(x for x in d["taches"] if x["id"] == "va")
    assert va["phrase"] == "Solde conforme." and va["resultat"].endswith("écarts à voir.") and va["autres"] == ["loyers"]
    assert next(x for x in d["taches"] if x["id"] == "vd")["phrase"] == "Export téléchargé"  # repli sur « Fait »


def test_vue_routine_donne_programme_prochaine_et_derniere_execution(client):
    rid = _routine(client)
    avant = next(x for x in client.get("/api/etiquettes/banque/vue").json()["taches"] if x["id"] == rid)["routine"]
    assert avant["programme"] == "chaque jour 08:00" and avant["prochaine"] and avant["derniere"] is None and not avant["en_pause"]
    assert client.post(f"/api/routines/{rid}/executer", headers=H).status_code == 202
    apres = next(x for x in client.get("/api/etiquettes/banque/vue").json()["taches"] if x["id"] == rid)["routine"]
    assert apres["derniere"]["origine"] == "manuelle"


def test_routine_en_pause_s_execute_sur_demande_explicite(client):
    rid = _routine(client)
    client.post(f"/api/routines/{rid}/modifier", json={"pause": True}, headers=H)
    ligne = next(x for x in client.get("/api/etiquettes/banque/vue").json()["taches"] if x["id"] == rid)
    assert ligne["routine"]["en_pause"] and ligne["routine"]["prochaine"] is None
    assert client.post(f"/api/routines/{rid}/executer", headers=H).status_code == 202


def test_mot_inconnu_donne_une_liste_vide(client):
    d = client.get("/api/etiquettes/inexistante/vue").json()
    assert d["taches"] == [] and d["mot"] == "inexistante"


def test_vue_n_ecrit_rien(client, racine):
    avant = (racine / ALPHA / "va.md").read_bytes()
    client.get("/api/etiquettes/banque/vue")
    assert (racine / ALPHA / "va.md").read_bytes() == avant


@pytest.mark.parametrize("texte,attendu", [("Un. Deux.", "Un."), ("Sans point", "Sans point"), ("", ""), ("A\nb ! c", "A b !")])
def test_premiere_phrase(texte, attendu):
    assert vue_etiquette.premiere_phrase(texte) == attendu
