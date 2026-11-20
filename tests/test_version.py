"""Lot 7 : INV-VERSION-1 (empreinte, `a_jour`, `perime` des 404, `POST /redemarrer`)."""

import asyncio
import os
import tomllib

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.config import RACINE_DEPOT, ConfigConseil, ConfigTransformations
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.version import Version, empreinte
from conftest import ecrire

H = {"X-Orchestrateur": "1"}


@pytest.fixture
def code(tmp_path):
    racine = tmp_path / "code"
    ecrire(racine, "a.py", "x = 1\n")
    ecrire(racine, "sous/b.py", "y = 2\n")
    return racine


def toucher(p):
    p.write_text(p.read_text(encoding="utf-8") + "# modifié\n", encoding="utf-8")
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))


def test_empreinte_stable_puis_changee(code):
    e = empreinte(code)
    assert e == empreinte(code) and len(e) == 12
    (code / "notes.txt").write_text("ignoré", encoding="utf-8")
    assert empreinte(code) == e
    toucher(code / "sous/b.py")
    assert empreinte(code) != e


def test_a_jour_recalcule_au_plus_toutes_les_n_secondes(code):
    lent, vif = Version(code, 3600), Version(code, 0)
    toucher(code / "a.py")
    assert asyncio.run(lent.etat())["a_jour"] is True  # pas encore recalculé
    etat = asyncio.run(vif.etat())
    assert etat["a_jour"] is False and etat["demarree"] != etat["disque"] and etat["depuis"]


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        c.app_ = app
        yield c


def test_perime_sur_les_404_seulement_si_le_code_a_change(client, code):
    assert "perime" not in client.get("/api/taches/inconnue").json()
    client.app_.state.version = Version(code, 0)
    toucher(code / "a.py")
    r = client.get("/api/taches/inconnue")
    assert r.status_code == 404 and r.json()["perime"] is True and "inconnue" in r.json()["detail"]
    r = client.get("/api/route-future")
    assert r.status_code == 404 and r.json()["perime"] is True
    assert client.get("/api/etat").json()["version"]["a_jour"] is False
    assert client.get("/api/arbre").status_code == 200


def test_redemarrer_409_si_tour_actif_202_sinon_sans_tuer(client, faux):
    client.app_.state.version.garde_s = 0
    faux.scenario = [Evenement("session", session="s"), "attendre"]
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    assert client.post("/api/redemarrer", headers=H).status_code == 409
    assert client.app_.state.version.code_sortie == 0
    assert client.post("/api/redemarrer").status_code == 403  # INV-API-1
    r = client.post("/api/redemarrer", headers=H, json={"force": True})
    assert r.status_code == 202 and client.app_.state.version.code_sortie == 3


def test_redemarrer_inactif_pose_le_code_et_demande_l_arret(client):
    client.app_.state.version.garde_s = 0
    arrets = []
    client.app_.state.version.arreter = lambda: arrets.append(1)
    r = client.post("/api/redemarrer", headers=H)
    assert r.status_code == 202 and r.json() == {"code_sortie": 3}
    for _ in range(100):
        if arrets:
            break
        asyncio.run(asyncio.sleep(0.01))
    assert arrets == [1]


def test_redemarrer_refuse_en_rafale(client, caplog):
    """688 redémarrages en 2 h 53 : un serveur à peine lancé refuse (429) sans `force`."""
    v = client.app_.state.version
    v.garde_s = 3600  # INV-VERSION-2 : garde hors de portée de la latence de la suite (0,3 s expirait sous charge)
    assert client.post("/api/redemarrer", headers=H).status_code == 429
    assert v.code_sortie == 0 and v.redemarrages == 0
    assert client.get("/api/etat").json()["version"]["redemarrages"] == 0
    with caplog.at_level("WARNING"):
        r = client.post("/api/redemarrer", headers={**H, "User-Agent": "essai-ua"}, json={"force": True, "par": "essai"})
    assert r.status_code == 202 and v.redemarrages == 1
    assert "par='essai'" in caplog.text and "essai-ua" in caplog.text
    assert client.get("/api/etat").json()["version"]["redemarrages"] == 1


def test_redemarrer_accepte_une_fois_la_garde_ecoulee(client):
    v = client.app_.state.version
    v.garde_s = 0.05
    asyncio.run(asyncio.sleep(0.1))
    assert client.post("/api/redemarrer", headers=H).status_code == 202


def test_valeurs_par_defaut_egales_a_l_exemple():
    ex = tomllib.loads((RACINE_DEPOT / "config.exemple.toml").read_text("utf-8"))
    assert ConfigConseil(**ex["conseil"]) == ConfigConseil()
    assert ConfigTransformations(**ex["transformations"]) == ConfigTransformations()


def test_redemarrage_differe_attend_la_fin_des_tours_puis_redemarre(client, faux):
    """INV-VERSION-3 : armé pendant un tour, le serveur ne redémarre qu'une fois le tour fini ; annulable."""
    v = client.app_.state.version
    v.garde_s, v.sonde_differe_s = 0, 0.02
    arrets = []
    v.arreter = lambda: arrets.append(1)
    faux.scenario = [Evenement("session", session="s"), "attendre"]
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    assert client.post("/api/redemarrer", headers=H).status_code == 409
    assert client.post("/api/redemarrer-differe", headers=H).json() == {"differe": True}
    assert client.get("/api/etat").json()["version"]["differe"] is True
    asyncio.run(asyncio.sleep(0.15))
    assert arrets == [] and v.code_sortie == 0  # un tour tourne encore
    assert client.delete("/api/redemarrer-differe", headers=H).json() == {"differe": False}
    assert client.get("/api/etat").json()["version"]["differe"] is False
    client.post("/api/redemarrer-differe", headers=H)
    client.post("/api/taches/mere/arret", headers=H)  # le tour finit
    for _ in range(200):
        if arrets:
            break
        asyncio.run(asyncio.sleep(0.02))
    assert arrets == [1] and v.code_sortie == 3 and v.redemarrages == 1
