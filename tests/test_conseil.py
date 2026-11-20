"""Lot 7 : avis d'un agent rapide (`POST /conseil`), jamais d'écriture dans le vault."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, conseil
from orchestrateur.config import ConfigConseil
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import ecrire
from test_moteur import executer

H = {"X-Orchestrateur": "1"}


def bloc(avis):
    return f"Lu.\n<conseil>\navis: {avis}\nmotif: une phrase\n</conseil>"


def photo(racine):
    return {p.relative_to(racine).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(racine.rglob("*"))}


@pytest.fixture
def client(config, vault, faux):
    config.conseil = ConfigConseil(harnais="faux", modele="petit", delai_s=5)
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        yield c


@pytest.mark.parametrize("rendu,avis", [(bloc("favorable"), "favorable"),
                                        (bloc("défavorable"), "defavorable"),
                                        ("pas de bloc", "indisponible")])
def test_avis_et_vault_intact(client, faux, racine, config, rendu, avis):
    faux.scenario = [Evenement("fin", session="eph", texte=rendu)]
    avant = photo(racine)
    r = client.post("/api/conseil", headers=H, json={"action": "promouvoir", "tache": "mere"})
    assert r.status_code == 200 and r.json()["avis"] == avis
    assert isinstance(r.json()["duree_s"], float)
    if avis != "indisponible":
        assert r.json()["motif"] == "une phrase"
    lance = faux.lances[0]
    assert lance["session"] is None and lance["modele"] == "petit"
    assert "élever la tâche « Mère »" in lance["message"] and "Tâches enfants : 1" in lance["message"]
    assert "<conseil>" in lance["consigne"]
    assert photo(racine) == avant  # aucun fichier du vault touché
    assert list((config.donnees / "journal").rglob("conseil-promouvoir-*.jsonl"))
    assert client.get("/api/etat").json()["tours"] == []  # hors simultanes_max, rien en cours


def test_reduire_donne_les_faits(client, faux, racine):
    ecrire(racine, "Projets/C1-Alpha/notes/n.md", "x\n")
    faux.scenario = [Evenement("fin", texte=bloc("favorable"))]
    r = client.post("/api/conseil", headers=H,
                    json={"action": "reduire", "conteneur": "Projets/C1-Alpha"})
    assert r.json()["avis"] == "favorable"
    message = faux.lances[0]["message"]
    assert "réduire le projet « Alpha »" in message and "ouvertes : 3 ; fermées : 0" in message
    assert "- Petit (a-faire)" in message and "Autres notes du dossier : 1" in message


def test_delai_depasse_arrete_le_processus(config, vault, faux):
    config.conseil = ConfigConseil(harnais="faux", delai_s=0.05)
    faux.scenario = ["attendre"]
    m = Moteur(config, vault, {"faux": faux})
    r = executer(conseil.avis(m, "promouvoir", "mere"))
    assert r["avis"] == "indisponible" and "délai" in r["motif"]
    assert len(faux.arrets) == 1


def test_inactif_ou_harnais_inconnu_rien_lance(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    config.conseil = ConfigConseil(actif=False, harnais="faux")
    assert executer(conseil.avis(m, "promouvoir", "mere"))["avis"] == "indisponible"
    config.conseil = ConfigConseil(harnais="absent")
    r = executer(conseil.avis(m, "reduire", None, "Projets/C1-Alpha"))
    assert r["avis"] == "indisponible" and "absent" in r["motif"]
    assert faux.lances == []


def test_harnais_en_echec_indisponible(config, vault, faux):
    config.conseil = ConfigConseil(harnais="faux")
    faux.scenario = [FileNotFoundError("claude introuvable")]
    r = executer(conseil.avis(Moteur(config, vault, {"faux": faux}), "promouvoir", "mere"))
    assert r["avis"] == "indisponible" and "introuvable" in r["motif"]


def test_entrees_invalides(client):
    assert client.post("/api/conseil", headers=H, json={"action": "x"}).status_code == 400
    assert client.post("/api/conseil", headers=H, json={"action": "promouvoir"}).status_code == 400
    assert client.post("/api/conseil", headers=H,
                       json={"action": "promouvoir", "tache": "inconnue"}).status_code == 404
