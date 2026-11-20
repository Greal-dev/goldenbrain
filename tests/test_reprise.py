"""Reprise d'un tour interrompu (INV-EXEC-1) — anomalie A3 de la recette du 15/11 : un
redémarrage forcé du serveur tuait le tour en cours sans reprise ni moyen de le relancer."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, reprise
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import RENDU, scenario_ok

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def client(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url=BASE) as c:
        yield c


def attendre(predicat):
    for _ in range(300):
        if predicat():
            return
        time.sleep(0.01)
    raise AssertionError("condition jamais atteinte")


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def poser_tours(config, contenu):
    fichier = config.donnees / "etat" / "tours.json"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(contenu), encoding="utf-8")


def test_redemarrage_force_pendant_un_tour_le_reprend_dans_la_meme_session(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-9"), "attendre"]
    m1 = Moteur(config, vault, {"faux": faux})
    with TestClient(api.creer_app(config, m1), base_url=BASE) as c:
        c.post("/api/taches/mere/messages", headers=H, json={"texte": "long travail"})
        attendre(lambda: vault.tache("mere").fm.get("session") == "s-9")
    # Redémarrage : nouveau serveur sur les mêmes données ; le tour coupé repart seul.
    faux.scenario = scenario_ok(session="s-9")
    m2 = Moteur(config, vault, {"faux": faux})
    with TestClient(api.creer_app(config, m2), base_url=BASE) as c:
        attendre(lambda: len(faux.lances) == 2 and m2.etat_de("mere") == "inactif")
        assert c.get("/api/taches/mere").json()["etat_execution"] == "inactif"
    reprise_ = faux.lances[1]
    assert reprise_["session"] == "s-9"  # même session du harnais
    assert reprise_["message"].startswith("[GoldenBrain")  # signé GoldenBrain, pas l'utilisateur
    assert "redémarrage du serveur" in reprise_["message"]
    assert vault.tache("mere").fm["statut"] == "retour-humain"


def test_tour_deja_repris_une_fois_n_est_pas_repris_en_boucle(config, vault, faux):
    vault.modifier("mere", {"session": "s-1"})
    poser_tours(config, [{"tache": "mere", "texte": "x", "reprise": True}])

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        reprises = reprise.reprendre_au_demarrage(m)
        return reprises, m.etat_de("mere")

    assert asyncio.run(scenario()) == ([], "interrompu")
    assert faux.lances == []


def _tour_repris_enregistre(config, vault, faux, scenario_faux):
    faux.scenario = scenario_faux
    vault.modifier("mere", {"session": "s-1"})
    poser_tours(config, ["mere"])  # format d'une version antérieure : identifiants seuls

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        assert reprise.reprendre_au_demarrage(m) == ["mere"]
        await asyncio.sleep(0.05)
        enregistre = json.loads(m.fichier_tours.read_text("utf-8"))
        await m.arreter("mere")
        await finir(m)
        return enregistre

    return asyncio.run(scenario())


def test_tour_repris_d_office_sans_rien_produire_porte_la_marque(config, vault, faux):
    rec = _tour_repris_enregistre(config, vault, faux, ["attendre"])
    assert rec == [{"tache": "mere", "texte": faux.lances[0]["message"], "sauts": 0, "de": "",
                    "source": "", "mandat": False, "role": "", "reprise": True}]


def test_tour_repris_qui_a_progresse_redevient_eligible(config, vault, faux):
    rec = _tour_repris_enregistre(config, vault, faux, [Evenement("session", session="s-1"), "attendre"])
    assert rec[0]["reprise"] is False


def test_double_redemarrage_un_tour_qui_a_progresse_est_repris_de_nouveau(config, vault, faux):
    # Défaut du 16/11 : la reprise « une fois pour la vie du tour » bloquait le second redémarrage.
    faux.scenario = [Evenement("session", session="s-9"), "attendre"]
    for n in range(3):  # démarrage initial, puis deux redémarrages forcés
        m = Moteur(config, vault, {"faux": faux})
        with TestClient(api.creer_app(config, m), base_url=BASE) as c:
            if n == 0:
                c.post("/api/taches/mere/messages", headers=H, json={"texte": "long travail"})
            attendre(lambda: len(faux.lances) == n + 1 and vault.tache("mere").fm.get("session") == "s-9"
                     and m.actifs.get("mere", {}).get("reprise") is not True)
    assert len(faux.lances) == 3
    assert all("reprise après interruption" in l["message"] for l in faux.lances[1:])


def test_tour_repris_sans_progres_n_est_pas_repris_a_chaque_demarrage(config, vault, faux):
    poser_tours(config, [{"tache": "mere", "texte": "x", "reprise": True}])
    m = Moteur(config, vault, {"faux": faux})
    assert asyncio.run(_demarrer(m)) == [] and faux.lances == []


async def _demarrer(m):
    return reprise.reprendre_au_demarrage(m)


def test_file_restauree_apres_redemarrage_dans_l_ordre(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-1"), "attendre"]

    async def avant():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "premier")
        await asyncio.sleep(0.05)
        m.soumettre("mere", "deuxième")
        m.soumettre("mere", "troisième", de="autre")
        await asyncio.sleep(0)
        await m.fermer()  # redémarrage forcé : le tour est tué, la file reste sur disque
        await finir(m)

    asyncio.run(avant())
    sur_disque = json.loads((config.donnees / "etat" / "file.json").read_text("utf-8"))
    assert [e["texte"] for e in sur_disque] == ["deuxième", "[Message de la tâche autre]" + chr(10) + "troisième"]
    faux.scenario = scenario_ok(session="s-1")

    async def apres():
        m = Moteur(config, vault, {"faux": faux})
        reprise.reprendre_au_demarrage(m)
        await finir(m)
        return m

    m = asyncio.run(apres())
    messages = [l["message"] for l in faux.lances[1:]]
    assert "reprise après interruption" in messages[0]
    assert messages[1] == "deuxième"
    assert "troisième" in messages[2] and m.etat_de("mere") == "inactif"
    assert json.loads((config.donnees / "etat" / "file.json").read_text("utf-8")) == []


def test_file_d_une_tache_fermee_n_est_pas_restauree(config, vault, faux):
    fichier = config.donnees / "etat" / "file.json"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps([{"tache": "mere", "texte": "x"}, {"tache": "disparue", "texte": "y"}]), "utf-8")
    vault.poser_statut("mere", "fait")
    m = Moteur(config, vault, {"faux": faux})
    assert asyncio.run(_restaurer(m)) == [] and faux.lances == []


async def _restaurer(m):
    return reprise.restaurer_file(m)


def test_premier_tour_sans_session_repart_avec_son_message_d_origine(config, vault, faux):
    poser_tours(config, [{"tache": "mere", "texte": "écris le rapport", "sauts": 0, "de": "",
                          "source": "", "mandat": False, "role": "", "reprise": False}])

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        reprise.reprendre_au_demarrage(m)
        await finir(m)

    asyncio.run(scenario())
    assert len(faux.lances) == 1 and faux.lances[0]["session"] is None
    assert "écris le rapport" in faux.lances[0]["message"]


def test_tache_fermee_entre_temps_n_est_pas_reprise(config, vault, faux):
    vault.poser_statut("mere", "fait")
    poser_tours(config, [{"tache": "mere", "texte": "x"}])

    async def scenario():
        return reprise.reprendre_au_demarrage(Moteur(config, vault, {"faux": faux}))

    assert asyncio.run(scenario()) == [] and faux.lances == []


def test_tour_interrompu_par_arret_se_relance_par_le_bouton(client, vault, faux):
    faux.scenario = [Evenement("session", session="s-2"), "attendre"]
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    attendre(lambda: vault.tache("mere").fm.get("session") == "s-2")
    client.post("/api/taches/mere/arret", headers=H)
    attendre(lambda: client.get("/api/taches/mere").json()["etat_execution"] == "interrompu")
    faux.scenario = [Evenement("fin", session="s-2", texte=RENDU)]
    r = client.post("/api/taches/mere/relancer", headers=H)
    assert r.status_code == 202
    attendre(lambda: client.get("/api/taches/mere").json()["etat_execution"] == "inactif")
    assert faux.lances[1]["session"] == "s-2"
    assert faux.lances[1]["message"].startswith("[GoldenBrain")


def test_relancer_sans_tour_interrompu_est_refuse(client):
    r = client.post("/api/taches/mere/relancer", headers=H)
    assert r.status_code == 409
