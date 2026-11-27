"""« Trouver les tâches » d'une étiquette : création, classement local par synonymes, affinage IA (réponse valide,
invalide, délai dépassé → repli local), pose en bloc annulable (INV-ETIQUETTE-5)."""

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api
from orchestrateur.config import ConfigConseil
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}
BETA = "Projets/C2-Beta/taches"


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, f"{BETA}/caf.md", tache_md(titre="relevé CAF Bellevue"))
    ecrire(racine, f"{BETA}/quit.md", tache_md(titre="Quittances de loyer", extra="nature: routine\n"))
    ecrire(racine, f"{BETA}/jardin.md", tache_md(titre="Tailler la haie"))
    ecrire(racine, f"{BETA}/vieux.md", tache_md(statut="fait", titre="Banque ancienne"))
    config.conseil = ConfigConseil(harnais="faux", modele="petit", delai_s=5)
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        yield c


def _creer(c, mot="finances", consigne=""):
    r = c.put(f"/api/etiquettes/{mot}", headers=H, json={"consigne": consigne})
    assert r.status_code == 200
    return r.json()["mot"]


def test_creer_etiquette_la_declare_vide(client):
    assert _creer(client, "Finances", "Argent du foyer") == "finances"
    e = next(x for x in client.get("/api/etiquettes").json()["etiquettes"] if x["mot"] == "finances")
    assert e == {"mot": "finances", "n": 0, "consigne": "Argent du foyer"}
    assert client.get("/api/etiquettes/finances/vue").json()["taches"] == []


def test_creer_etiquette_refusee_a_un_agent(client):
    r = client.put("/api/etiquettes/finances", headers={**H, "X-Orch-Tache": "mere"}, json={"consigne": ""})
    assert r.status_code == 409


def test_classement_local_trouve_releve_caf_pour_finances(client):
    _creer(client)
    d = client.get("/api/etiquettes/finances/candidates").json()
    ids = [x["id"] for x in d["candidates"]]
    assert {"caf", "quit"} <= set(ids) and "jardin" not in ids and "vieux" not in ids  # fermée exclue
    caf = next(x for x in d["candidates"] if x["id"] == "caf")
    assert caf["pertinente"] and "caf" in caf["motif"] and not d["ia"]


def _ia(client, faux, rendu):
    faux.scenario = [Evenement("fin", session="eph", texte=rendu)]
    return client.post("/api/etiquettes/finances/candidates/ia", headers=H).json()


def test_affinage_ia_valide_coche_les_ids_et_ignore_les_inventes(client, faux):
    _creer(client)
    d = _ia(client, faux, "Vu.\n<etiquetage>\njardin | dépenses de jardinier\ninvente | rien\n</etiquetage>")
    assert d["ia"] and not d["erreur"]
    assert d["candidates"][0]["id"] == "jardin" and d["candidates"][0]["motif"] == "dépenses de jardinier"
    assert [x["id"] for x in d["candidates"] if x["pertinente"]] == ["jardin"]
    assert "invente" not in {x["id"] for x in d["candidates"]}
    lance = faux.lances[0]
    assert lance["modele"] == "petit" and "#finances" in lance["message"] and "caf | relevé CAF Bellevue" in lance["message"]
    assert "<etiquetage>" in lance["consigne"]


def test_affinage_ia_reponse_invalide_garde_le_classement_local(client, faux):
    _creer(client)
    d = _ia(client, faux, "je ne sais pas")
    assert not d["ia"] and "classement local" in d["erreur"]
    assert next(x for x in d["candidates"] if x["id"] == "caf")["pertinente"]


def test_affinage_ia_delai_depasse_repli_local_et_processus_arrete(client, faux, config):
    _creer(client)
    config.conseil = ConfigConseil(harnais="faux", delai_s=0.05)
    faux.scenario = ["attendre"]
    d = client.post("/api/etiquettes/finances/candidates/ia", headers=H).json()
    assert not d["ia"] and "délai" in d["erreur"]
    assert "caf" in {x["id"] for x in d["candidates"]} and len(faux.arrets) == 1


def test_pose_en_bloc_puis_vue_et_annulation(client):
    _creer(client)
    r = client.post("/api/lots", headers=H, json={"taches": ["caf", "quit"], "etiquettes": {"ajouter": ["finances"]}}).json()
    assert sorted(r["changees"]) == ["caf", "quit"]
    assert {x["id"] for x in client.get("/api/etiquettes/finances/vue").json()["taches"]} == {"caf", "quit"}
    assert "caf" not in {x["id"] for x in client.get("/api/etiquettes/finances/candidates").json()["candidates"]}
    client.post(f"/api/lots/{r['lot']}/annuler", headers=H)
    assert client.get("/api/etiquettes/finances/vue").json()["taches"] == []
