"""Quatre langues (INV-LANGUE-1) : dictionnaires alignés, t() du serveur, réglage persisté, consignes et guide."""

import sys

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, guide, langues
from orchestrateur.config import ConfigInterface, RACINE_DEPOT
from orchestrateur.moteur import Moteur
from test_interface import H, charger_interface, client  # noqa: F401 (fixture)

sys.path.insert(0, str(RACINE_DEPOT / "scripts"))
import dictionnaires  # noqa: E402


@pytest.fixture(autouse=True)
def langue_source():
    yield
    langues.regler("fr")


def test_les_quatre_dictionnaires_ont_les_memes_cles_et_parametres():
    assert dictionnaires.parite() == []
    assert dictionnaires.cles_manquantes() == []


def test_t_remplace_les_parametres_et_se_replie_sur_le_francais():
    assert langues.t("appairer.ok", "de", nom="Pixel") == "Gerät „Pixel“ gekoppelt. Wird geöffnet …"
    langues.regler("es")
    assert langues.t("guide.titre") == "Guía"
    assert langues.t("cle.inconnue") == "cle.inconnue"
    langues.regler("xx")  # inconnue : langue source
    assert langues.courante() == "fr"


def test_libelle_en_dur_detecte_dans_un_js(tmp_path):
    f = tmp_path / "x.js"
    f.write_text("const a = t('ok.cle'); el.title = 'Nouvelle tâche'; const id = 'data-id';\n", encoding="utf-8")
    assert [e.split(" : ", 1)[1] for e in dictionnaires.en_dur([f])] == ["libellé en dur « Nouvelle tâche »"]


def test_langue_inconnue_refusee_par_la_configuration():
    with pytest.raises(ValueError):
        ConfigInterface(langue="it")


def test_la_langue_choisie_est_ecrite_dans_config_et_reglee(client, config):  # noqa: F811
    assert client.get("/api/interface").json()["langue"] == ""
    assert client.put("/api/interface", headers=H, json={"langue": "it"}).status_code == 400
    assert client.put("/api/interface", headers=H, json={"langue": "de"}).json()["langue"] == "de"
    assert charger_interface(config).langue == "de" and langues.courante() == "de"
    client.put("/api/interface", headers=H, json={"mode": "simple"})  # changer de niveau garde la langue
    assert charger_interface(config).langue == "de"


def test_la_consigne_des_agents_demande_la_langue_reglee():
    langues.regler("en")
    assert "English" in langues.consigne_langue() and "fiche" in langues.consigne_langue()
    assert "Deutsch" in langues.consigne_langue("de")


def test_les_guides_traduits_portent_toutes_les_ancres():
    assert guide.manquements_traduits() == []


def test_le_guide_est_servi_dans_la_langue_demandee(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        for code in ("en", "de", "es"):
            assert c.get(f"/api/guide?langue={code}").text == guide.lire(guide.fichier(code))
        assert c.get("/api/guide?langue=zz").text.startswith("# Guide de GoldenBrain")
