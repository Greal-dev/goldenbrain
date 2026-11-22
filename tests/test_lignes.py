"""Lignes de tâche, plafond par parent et natures : fiche, API, rangement à la création, CLI, jardinier, réflexes."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, cli_lignes, fiches, rangement, reflexes
from orchestrateur.config_rangement import ConfigRangement
from orchestrateur.moteur import Moteur
from conftest import ecrire, tache_md

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
ALPHA = "Projets/C1-Alpha"


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, f"{ALPHA}/taches/chantier.md", tache_md(titre="Chantier de la mère"))
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def lignes(client, ident="chantier"):
    return client.get(f"/api/taches/{ident}").json()["fiche"]["lignes"]


# --- fiche : bloc géré -------------------------------------------------------------------------
def test_bloc_lignes_aller_retour_et_reste_intact():
    texte = "---\ntype: tache\n---\n\n# T\n\nprose · avec point médian\n"
    ls = [{"fait": False, "texte": "a · b", "date": "2026-11-22", "auteur": "moi", "lien": ""},
          {"fait": True, "texte": "c", "date": "2026-11-22", "auteur": "ia", "lien": "[[doc]]"}]
    ecrit = fiches.ecrire_lignes(texte, ls)
    assert fiches.lire_lignes(ecrit) == ls
    assert ecrit.startswith(texte.rstrip("\n"))
    assert "prose" in fiches.corps_sans_fiche(ecrit) and "Lignes" not in fiches.corps_sans_fiche(ecrit)
    assert fiches.ecrire_lignes(ecrit, []) == texte  # vide : le bloc disparaît, rien d'autre ne bouge


def test_bloc_lignes_survit_a_la_reecriture_de_la_fiche():
    t = fiches.ecrire_lignes("# T\n", [{"fait": False, "texte": "x", "date": "2026-11-22", "auteur": "moi", "lien": ""}])
    t = fiches.ecrire_fiche(t, {**fiches.fiche_vide(), "fait": "ok"})
    assert [x["texte"] for x in fiches.lire_lignes(t)] == ["x"] and fiches.lire_fiche(t)["fait"] == "ok"


# --- API des lignes ----------------------------------------------------------------------------
def test_ajouter_cocher_retirer(client):
    assert client.post("/api/taches/chantier/lignes", json={"texte": "  Vérifier  le mail "}, headers=H).status_code == 201
    l = lignes(client)
    assert l[0]["texte"] == "Vérifier le mail" and l[0]["auteur"] == "moi" and not l[0]["fait"]
    client.post("/api/taches/chantier/lignes/basculer", json={"index": 0}, headers=H)
    assert lignes(client)[0]["fait"]
    assert client.post("/api/taches/chantier/lignes/basculer", json={"index": 5}, headers=H).status_code == 400
    client.post("/api/taches/chantier/lignes/retirer", json={"index": 0}, headers=H)
    assert lignes(client) == []


def test_auteur_ia_par_en_tete_agent_et_texte_obligatoire(client):
    client.post("/api/taches/chantier/lignes", json={"texte": "fait par l'agent", "fait": True},
                headers={**H, "X-Orch-Tache": "chantier"})
    assert lignes(client)[0]["auteur"] == "ia" and lignes(client)[0]["fait"]
    assert client.post("/api/taches/chantier/lignes", json={"texte": " "}, headers=H).status_code == 400
    assert client.post("/api/taches/chantier/lignes", json={"texte": "x" * 400}, headers=H).status_code == 400


def test_promouvoir_une_ligne_en_tache_fille_puis_l_inverse(client):
    client.post("/api/taches/chantier/lignes", json={"texte": "Envoyer le mail de relance"}, headers=H)
    r = client.post("/api/taches/chantier/lignes/promouvoir", json={"index": 0}, headers=H)
    assert r.status_code == 201 and r.json()["lignes"] == []
    fille = r.json()["id"]
    d = client.get(f"/api/taches/{fille}").json()
    assert d["parent"] == "chantier" and d["titre"] == "Envoyer le mail de relance" and d["genre"] == "operation"
    # l'inverse : la tâche redevient une ligne de sa mère, close et liée (rien n'est supprimé)
    r = client.post(f"/api/taches/{fille}/en-ligne", json={}, headers=H)
    assert r.status_code == 200 and r.json()["vers"] == "chantier"
    ligne = lignes(client)[0]
    assert ligne["texte"] == "Envoyer le mail de relance" and fille.rsplit("/", 1)[-1] in ligne["lien"]
    assert client.get(f"/api/taches/{fille}").json()["statut"] == "cloture"


def test_en_ligne_refuse_sans_mere_et_avec_enfants_ouverts(client):
    assert client.post("/api/taches/chantier/en-ligne", json={}, headers=H).status_code == 400
    f = client.post("/api/taches", json={"titre": "Fille alpha", "parent": "chantier"}, headers=H).json()["id"]
    client.post("/api/taches", json={"titre": "Petite fille", "parent": f}, headers=H)
    assert client.post(f"/api/taches/{f}/en-ligne", json={}, headers=H).status_code == 409


def test_agent_peut_ajouter_une_ligne_sur_une_tache_tenue_par_l_humain(client, racine):
    ecrire(racine, f"{ALPHA}/taches/moi.md", tache_md(titre="Mienne", extra="executant: humain\n"))
    h = {**H, "X-Orch-Tache": "chantier"}
    assert client.post("/api/taches/moi/lignes", json={"texte": "ajout"}, headers=h).status_code == 201
    assert client.post("/api/taches/moi/en-ligne", json={"vers": "chantier"}, headers=h).status_code == 409


# --- natures ----------------------------------------------------------------------------------
def test_deduction_de_la_nature():
    assert rangement.deduire("Corriger le bug de la branche d'intégration") == "developpement"
    assert rangement.deduire("Relancer le mail du compte") == "operation"
    assert rangement.deduire("Décider de la licence et du nom") == "pilotage"
    assert rangement.deduire("Quelque chose") == ""


def test_nature_posee_a_la_creation_modifiable_et_dans_l_arbre(client):
    d = client.post("/api/taches", json={"titre": "Corriger le bug de l'API", "conteneur": ALPHA}, headers=H).json()
    assert d["genre"] == "developpement" and d["genre_pose"]
    assert client.post("/api/taches", json={"titre": "Autre", "conteneur": ALPHA, "genre": "magie"}, headers=H).status_code == 400
    r = client.post(f"/api/taches/{d['id']}/genre", json={"genre": "pilotage"}, headers=H).json()
    assert r["genre"] == "pilotage"
    assert client.post(f"/api/taches/{d['id']}/genre", json={"genre": "x"}, headers=H).status_code == 400
    r = client.post(f"/api/taches/{d['id']}/genre", json={"genre": ""}, headers=H).json()
    assert not r["genre_pose"] and r["genre"] == "developpement"  # de nouveau déduite
    noeuds = []
    def parcourir(ns):
        for n in ns:
            noeuds.append(n); parcourir(n["enfants"])
    parcourir(client.get("/api/arbre").json()["noeuds"])
    assert any(n.get("genre") == "developpement" for n in noeuds if n["type"] == "tache")


# --- plafond et mélange à la création -----------------------------------------------------------
def remplir(client, n, parent="chantier", prefixe="Tache"):
    for i in range(n):
        assert client.post("/api/taches", json={"titre": f"{prefixe} numero{i} zz{i}", "parent": parent,
                                                "genre": "pilotage", "forcer": True}, headers=H).status_code == 201


def test_plafond_refuse_doucement_avec_rangements_puis_passe_si_force(client):
    remplir(client, 10)
    r = client.post("/api/taches", json={"titre": "Onzième affaire distincte", "parent": "chantier"}, headers=H)
    assert r.status_code == 409
    rang = r.json()["rangement"]
    assert rang["raison"] == "plafond" and rang["ouvertes"] == 10 and rang["plafond"] == 10
    gestes = [p["geste"] for p in rang["propositions"]]
    assert gestes[0] == "ligne" and rang["propositions"][0]["tache"] == "chantier" and gestes[-1] == "nouveau_groupe"
    assert client.post("/api/taches", json={"titre": "Onzième affaire distincte", "parent": "chantier", "forcer": True},
                       headers=H).status_code == 201


def test_nouveau_groupe_cree_le_regroupement_et_y_range(client):
    remplir(client, 10)
    r = client.post("/api/taches", json={"titre": "Corriger le bug du module", "parent": "chantier",
                                         "groupe": "Développement — chantier"}, headers=H)
    assert r.status_code == 201
    d = r.json()
    groupe = client.get(f"/api/taches/{d['parent']}").json()
    assert groupe["titre"] == "Développement — chantier" and groupe["parent"] == "chantier" and groupe["genre"] == "developpement"


def test_pas_de_melange_des_natures_sous_un_meme_parent(client):
    remplir(client, 2)  # deux tâches de pilotage sous « mere »
    r = client.post("/api/taches", json={"titre": "Corriger le bug du module", "parent": "chantier"}, headers=H)
    assert r.status_code == 409 and r.json()["rangement"]["raison"] == "nature"
    # même nature, ou nature indéterminée : aucune friction
    assert client.post("/api/taches", json={"titre": "Décider du nom", "parent": "chantier"}, headers=H).status_code == 201
    assert client.post("/api/taches", json={"titre": "Quelque chose", "parent": "chantier"}, headers=H).status_code == 201


def test_reglage_natures_separees_et_plafond(client, config):
    r = client.put("/api/rangement", json={"plafond": 3, "natures_separees": False}, headers=H)
    assert r.json() == {"plafond": 3, "natures_separees": False} and config.rangement.plafond == 3
    assert client.put("/api/rangement", json={"plafond": 1}, headers=H).status_code == 400
    remplir(client, 2)
    assert client.post("/api/taches", json={"titre": "Corriger le bug du module", "parent": "chantier"}, headers=H).status_code == 201
    assert client.post("/api/taches", json={"titre": "Encore une affaire", "parent": "chantier"}, headers=H).status_code == 409


def test_config_rangement_valide():
    with pytest.raises(ValueError):
        ConfigRangement(plafond=1)
    with pytest.raises(ValueError):
        ConfigRangement(natures_separees="oui")


# --- jardinier, CLI, réflexes -------------------------------------------------------------------
def test_le_jardinier_recoit_les_parents_en_exces(client, vault, config, faux):
    from orchestrateur.jardinage import Jardinier
    remplir(client, 11)
    moteur = Moteur(config, vault, {"faux": faux})
    assert "chantier" in Jardinier(moteur)._excedents() and "11 ouvertes" in Jardinier(moteur)._excedents()


def test_cli_ligne_et_rendu_du_rangement():
    sortie = cli_lignes.rendre_rangement({"rangement": {"raison": "plafond", "ouvertes": 10, "plafond": 10, "parent": "p",
        "propositions": [{"geste": "ligne", "tache": "t1", "titre": "T"},
                         {"geste": "sous_groupe", "tache": "t2", "titre": "U"},
                         {"geste": "nouveau_groupe", "titre": "Opération — P"}]}})
    assert "orch ligne t1" in sortie and "--parent t2" in sortie and "--parent p" in sortie and "--nouvelle" in sortie
    assert cli.rendre_proches({"rangement": None}) == ""

    class A:
        id, texte, document, fait, cocher = "t", "du travail", "", False, 0
    appels = []
    def appeler(m, chemin, corps=None):
        appels.append((m, chemin, corps)); return {"lignes": [{"fait": True}, {"fait": False}]}
    assert cli_lignes.executer(A, appeler, str)[0] == "t : 2 ligne(s), 1 faite(s)"
    assert appels[0][:2] == ("POST", "/taches/t/lignes")


def test_reflexes_portent_les_regles_de_rangement_dans_les_quatre_langues():
    assert "ranger" in reflexes.CLES and reflexes.VERSION >= 3
    for langue in ("fr", "en", "de", "es"):
        b = reflexes.bloc(langue)
        assert "orch ligne" in b and "10" in b
