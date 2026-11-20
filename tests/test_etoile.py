"""INV-ETOILE-1 : invitation unique à l'étoile GitHub (seuil d'usage, report, refus, dépôt privé, réglage)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.config import ConfigEtoile
from orchestrateur.etoile import Etoile, depot_de
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}
H3 = 3 * 3600


class Horloge:
    def __init__(self):
        self.t = dt.datetime(2026, 11, 18, 10, 0)

    def __call__(self):
        return self.t

    def jours(self, n):
        self.t += dt.timedelta(days=n)


class Reseau:
    def __init__(self, public=True):
        self.public, self.appels = public, []

    def __call__(self, depot):
        self.appels.append(depot)
        return self.public


@pytest.fixture
def horloge():
    return Horloge()


def fabriquer(config, horloge, reseau=None, **cfg):
    config.etoile = ConfigEtoile(**cfg)
    reseau = reseau if reseau is not None else Reseau()
    return Etoile(config, maintenant=horloge, sonder=reseau, origine=lambda: "https://github.com/exemple/depot.git"), reseau


def user(e, secondes):
    while secondes > 0:
        e.usage(min(secondes, 300))
        secondes -= 300


def test_depot_deduit_des_adresses():
    assert depot_de("https://github.com/exemple/depot.git") == "exemple/depot"
    assert depot_de("git" + "@github.com:exemple/depot.git") == "exemple/depot"
    assert depot_de("https://gitlab.com/exemple/depot") is None


def test_rien_avant_le_seuil_puis_invitation(config, horloge):
    e, reseau = fabriquer(config, horloge)
    user(e, H3 - 300)
    assert e.etat()["afficher"] is False and reseau.appels == []  # pas de sonde avant d'être dû
    user(e, 300)
    etat = e.etat()
    assert etat["afficher"] is True and etat["url"] == "https://github.com/exemple/depot"


def test_depot_prive_ou_reseau_coupe_rien(config, horloge):
    e, reseau = fabriquer(config, horloge, reseau=Reseau(public=False))
    user(e, H3)
    assert e.etat()["afficher"] is False
    e.etat()
    assert len(reseau.appels) == 1  # une sonde par jour au plus, échec compris
    reseau.public = True
    assert e.etat()["afficher"] is False  # même jour : résultat gardé
    horloge.jours(1)
    assert e.etat()["afficher"] is True and len(reseau.appels) == 2


def test_plus_tard_redemande_apres_14_jours_d_usage(config, horloge):
    e, _ = fabriquer(config, horloge)
    user(e, H3)
    assert e.repondre("plus_tard")["afficher"] is False
    for _ in range(13):
        horloge.jours(1)
        assert e.usage(60)["afficher"] is False
    horloge.jours(1)
    assert e.usage(60)["afficher"] is True
    assert e.repondre("plus_tard")["afficher"] is False  # le cycle repart


def test_jours_sans_usage_ne_comptent_pas(config, horloge):
    e, _ = fabriquer(config, horloge)
    user(e, H3)
    e.repondre("plus_tard")
    horloge.jours(30)
    assert e.etat()["afficher"] is False


@pytest.mark.parametrize("choix", ["jamais", "etoile"])
def test_reponse_definitive(config, horloge, choix):
    e, _ = fabriquer(config, horloge)
    user(e, H3)
    assert e.repondre(choix)["afficher"] is False
    horloge.jours(400)
    e.usage(300)
    assert e.etat()["afficher"] is False
    avant = e.fichier.read_text(encoding="utf-8")
    e.usage(300)
    assert e.fichier.read_text(encoding="utf-8") == avant  # plus aucune écriture


def test_reglage_desactive_rien_et_rien_cumule(config, horloge):
    e, reseau = fabriquer(config, horloge)
    assert e.regler(False)["actif"] is False
    user(e, 2 * H3)
    assert e.etat()["afficher"] is False and not e.fichier.exists() or e.etat()["afficher"] is False
    assert reseau.appels == []
    assert e.regler(True)["actif"] is True


def test_config_eteinte_ou_sans_depot(config, horloge):
    e, _ = fabriquer(config, horloge, actif=False)
    user(e, H3)
    assert e.etat()["afficher"] is False
    config.etoile = ConfigEtoile()
    sans = Etoile(config, maintenant=horloge, sonder=Reseau(), origine=lambda: "")
    user(sans, H3)
    assert sans.etat()["afficher"] is False and sans.etat()["url"] is None


def test_depot_regle_dans_la_config(config, horloge):
    e, _ = fabriquer(config, horloge, depot="autre/projet")
    assert e.url() == "https://github.com/autre/projet"


def test_essai_force_l_affichage(config, horloge):
    e, reseau = fabriquer(config, horloge, essai=True, reseau=Reseau(public=False))
    assert e.etat()["afficher"] is True and reseau.appels == []
    assert e.repondre("jamais")["afficher"] is False


def test_pas_d_usage_demesure(config, horloge):
    e, _ = fabriquer(config, horloge)
    e.usage(10**9)
    assert e.etat()["afficher"] is False  # un envoi est borné à 5 minutes


def test_routes(config, vault, monkeypatch):
    from orchestrateur import etoile as module
    monkeypatch.setattr(module, "sonder_github", lambda d: True)
    monkeypatch.setattr(module, "origine_git", lambda *a: "https://github.com/exemple/depot")
    config.etoile = ConfigEtoile(seuil_h=0.01)
    with TestClient(api.creer_app(config, Moteur(config)), base_url=f"http://127.0.0.1:{config.port}") as c:
        _routes(c)


def _routes(c):
    assert c.get("/api/etoile").json()["afficher"] is False
    assert c.post("/api/etoile/usage", json={"secondes": 60}).status_code in (400, 403)  # garde INV-API-1
    r = c.post("/api/etoile/usage", json={"secondes": 60}, headers=H).json()
    assert r["afficher"] is True
    assert c.post("/api/etoile/reponse", json={"choix": "x"}, headers=H).status_code == 422
    assert c.post("/api/etoile/reponse", json={"choix": "jamais"}, headers=H).json()["afficher"] is False
    assert c.put("/api/etoile", json={"actif": False}, headers=H).json()["actif"] is False
