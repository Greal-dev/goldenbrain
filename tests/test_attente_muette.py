"""Pas d'attente muette (INV-MAIN-1 à INV-MAIN-5) : lecture d'état, renvoi borné, gestes humains seuls."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, etat_main
from orchestrateur.moteur import Moteur
from conftest import RENDU, ecrire, scenario_ok, tache_md

EN_COURS = "<fiche>\nstatut: en_cours\nfait: un morceau\nreste: la suite\nprochain_pas:\n</fiche>"
TERMINE = "<fiche>\nstatut: terminee\nfait: tout\nresultat: livré\nprochain_pas:\n</fiche>"
QUESTION = "<fiche>\nstatut: en_attente\nfait: x\nprochain_pas: Choisis A ou B ?\n</fiche>"


@pytest.fixture
def client(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url="http://127.0.0.1:8399") as c:
        yield c


def moteur(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m._q = m.abonner()
    return m


def jouer(config, vault, faux, rendu, ident="mere"):
    faux.scenario = scenario_ok(rendu=rendu)

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre(ident, "go")
        while any(not b.done() for b in m.boucles.values()):
            await asyncio.gather(*m.boucles.values(), return_exceptions=True)
        return m

    return asyncio.run(scenario())


def test_tour_en_cours_sans_agent_ni_attente_est_renvoye_deux_fois_puis_pose_a_l_humain(config, vault, faux):
    m = jouer(config, vault, faux, EN_COURS)
    messages = [x["message"] for x in faux.lances]
    assert len(messages) == 3 and all(x.startswith("[GoldenBrain — conclus]") for x in messages[1:])  # 2 renvois, pas plus
    assert vault.tache("mere").statut == vault.retour and m.attente_muette.epuise("mere")
    lu = etat_main.lire(m, vault.tache("mere"))
    assert lu["cle"] == "humain" and lu["motif"] == "epuise" and lu["muette"] and lu["geste"] == "renvoyer"


def test_fin_de_tour_avec_demande_precise_n_est_jamais_renvoyee(config, vault, faux):
    m = jouer(config, vault, faux, QUESTION)
    assert len(faux.lances) == 1 and m.attente_muette.renvois("mere") == 0
    lu = etat_main.lire(m, vault.tache("mere"))
    assert lu["cle"] == "humain" and lu["geste"] == "repondre" and "A ou B" in lu["phrase"]


def test_fin_de_tour_terminee_est_lue_terminee(config, vault, faux):
    m = jouer(config, vault, faux, TERMINE)
    assert len(faux.lances) == 1
    assert etat_main.lire(m, vault.tache("mere"))["cle"] in ("humain", "termine")  # fait avec session : à valider


def test_geste_humain_remet_le_compteur_de_renvois_a_zero(config, vault, faux):
    m = jouer(config, vault, faux, EN_COURS)
    assert m.attente_muette.epuise("mere")

    async def geste():
        m.soumettre("mere", "voici une consigne", humain=True)
        remis = not m.attente_muette.epuise("mere") and m.attente_muette.renvois("mere") == 0  # avant que le tour ne rejuge
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)
        return remis

    assert asyncio.run(geste())


def test_tache_jamais_lancee_se_lit_a_confier_sans_compter_dans_a_moi(config, vault, faux):
    """Symptôme (25/11) : « À moi » passait de 59 à 207 parce que les jamais lancées de l'IA comptaient comme humaines."""
    m = moteur(config, vault, faux)
    lu = etat_main.lire(m, vault.tache("petit"))
    assert lu["cle"] == "humain" and lu["geste"] == "confier" and lu["categorie"] == "confier" and lu["suggere"] is not False
    assert "petit" not in etat_main.humain_par_id(m) and m.etat_global()["a_moi"] == 0


def test_groupe_dit_ses_enfants_et_ne_compte_pas(config, vault, faux):
    """Symptôme (25/11) : un groupe (« Développement ») sans travail propre se lisait « action humaine » ; il synthétise ses enfants (INV-MAIN-6)."""
    m = moteur(config, vault, faux)
    lu = etat_main.lire(m, vault.tache("mere"))
    assert lu["cle"] == "termine" and lu["motif"] == "groupe" and "mere" not in etat_main.humain_par_id(m)


def test_permanente_est_en_veille_hors_a_moi(config, vault, faux):
    """Symptôme (25/11) : « Intégrer les branches terminées » se lisait « action humaine » alors qu'elle n'a rien à faire (INV-MAIN-6)."""
    m = moteur(config, vault, faux)
    vault.modifier("petit", {"nature": "permanente"})
    lu = etat_main.lire(m, vault.tache("petit"))
    assert lu["cle"] == "termine" and lu["motif"] == "veille" and "petit" not in etat_main.humain_par_id(m)


def test_executant_humain_est_a_faire_par_vous_sans_confier_suggere(config, vault, faux):
    """Symptôme (25/11) : un appel à l'avocat se voyait proposer « Renvoyer à l'IA » ; l'exécutant humain se lit « à faire par vous » (INV-MAIN-7)."""
    m = moteur(config, vault, faux)
    vault.modifier("petit", {"executant": "humain"})
    lu = etat_main.lire(m, vault.tache("petit"))
    assert lu["cle"] == "humain" and lu["categorie"] == "faire" and lu["suggere"] is False
    assert m.etat_global()["moi_faire"] == 1 == m.etat_global()["a_moi"]
    assert [x["id"] for x in etat_main.par_categorie(m)["faire"]] == ["petit"]


def test_demarche_dans_le_titre_est_a_faire_par_vous(config, vault, faux):
    m = moteur(config, vault, faux)
    ecrire(vault.racine, "Projets/C1-Alpha/taches/petit.md", tache_md(extra="parent: enfant\n", titre="Appeler l'avocat pour le bail"))
    assert etat_main.lire(m, vault.tache("petit"))["categorie"] == "faire"


def test_compteur_a_moi_egale_les_taches_en_action_humaine(config, vault, faux):
    m = moteur(config, vault, faux)
    vault.modifier("petit", {"executant": "humain"})
    e = m.etat_global()
    assert e["a_moi"] == len(etat_main.humain_par_id(m)) == e["moi_valider"] + e["moi_questions"] + e["moi_faire"] > 0


def test_geste_confier_refuse_a_un_agent(client):
    r = client.post("/api/taches/mere/ia", json={}, headers={"X-Orchestrateur": "1", "X-Orch-Tache": "autre"})
    assert r.status_code == 403
    r = client.post("/api/lots/ia", json={"taches": ["mere"]}, headers={"X-Orchestrateur": "1", "X-Orch-Tache": "autre"})
    assert r.status_code == 403
    r = client.post("/api/taches/mere/confier", json={}, headers={"X-Orchestrateur": "1", "X-Orch-Tache": "autre"})
    assert r.status_code == 403
