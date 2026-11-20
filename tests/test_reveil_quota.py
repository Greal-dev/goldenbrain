"""Réveil automatique sur quota épuisé (INV-EXEC-10) : programmation, relance, annulation, redémarrage."""

import asyncio
import datetime as dt
import json

import pytest

from orchestrateur import echecs, reveil
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import scenario_ok

QUOTA = "You’ve hit your usage limit. Upgrade to Pro, or try again at 3:14 PM."
SANS_HEURE = "429 rate limit exceeded"


def erreur(texte):
    return [Evenement("session", session="s-1"), Evenement("erreur", texte=texte)]


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


async def attendre(condition, delai=5.0):
    fin = asyncio.get_running_loop().time() + delai
    while not condition():
        assert asyncio.get_running_loop().time() < fin, "condition jamais atteinte"
        await asyncio.sleep(0.02)


@pytest.fixture
def rapide(monkeypatch):
    monkeypatch.setattr(reveil, "INTERVALLE_S", 0.4)


def test_heure_de_reprise_lue_dans_le_message_du_harnais():
    mat = dt.datetime(2026, 11, 15, 10, 0)
    assert echecs.heure_reprise(QUOTA, mat) == dt.datetime(2026, 11, 15, 15, 14)
    assert echecs.heure_reprise("usage limit, try again at 9:05 AM", mat) == dt.datetime(2026, 11, 16, 9, 5)
    assert echecs.heure_reprise("quota : retry in 2 hours", mat) == dt.datetime(2026, 11, 15, 12, 0)
    assert echecs.heure_reprise("resets 3pm", mat) == dt.datetime(2026, 11, 15, 15, 0)
    assert echecs.heure_reprise(SANS_HEURE, mat) is None
    assert echecs.heure_reprise("resets 3", mat) is None


def test_quota_codex_programme_la_relance_a_l_heure_plus_deux_minutes(config, vault, faux):
    faux.scenario = erreur(QUOTA)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        return m

    m = asyncio.run(scenario())
    a = dt.datetime.fromisoformat(m.reveils["mere"]["a"])
    assert (a.hour, a.minute) == (15, 16) and a > dt.datetime.now()
    assert m.pause_de("mere") == "En pause : quota faux, reprise à 15:16"
    assert m.etat_de("mere") == "en_pause"
    sur_disque = json.loads((config.donnees / "etat" / "reveils.json").read_text("utf-8"))
    assert sur_disque["mere"]["texte"] == "travaille"


def test_quota_sans_heure_reessaie_toutes_les_30_minutes(config, vault, faux):
    faux.scenario = erreur(SANS_HEURE)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        return m

    m = asyncio.run(scenario())
    delai = (dt.datetime.fromisoformat(m.reveils["mere"]["a"]) - dt.datetime.now()).total_seconds()
    assert 1700 < delai <= 1800


def test_erreur_sans_quota_ne_programme_aucun_reveil(config, vault, faux):
    faux.scenario = erreur("boum")

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        return m

    m = asyncio.run(scenario())
    assert m.reveils == {} and m.etat_de("mere") == "inactif"


def test_quota_epuise_le_message_est_relance_a_l_echeance_et_l_echec_s_efface(config, vault, faux, rapide):
    faux.scenario = erreur(SANS_HEURE)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        assert "mere" in m.reveils
        faux.scenario = scenario_ok()  # le quota est revenu
        await attendre(lambda: len(faux.lances) == 2)
        await finir(m)
        return m

    m = asyncio.run(scenario())
    assert "travaille" in faux.lances[1]["message"]  # le MÊME message repart
    assert not vault.tache("mere").fm.get("echec_tour") and m.reveils == {}


def test_quota_persistant_s_arrete_apres_huit_relances(config, vault, faux, rapide):
    faux.scenario = erreur(SANS_HEURE)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        await attendre(lambda: len(faux.lances) == 1 + reveil.ESSAIS_MAX and "mere" not in m.reveils)
        await finir(m)
        return m

    m = asyncio.run(scenario())
    assert len(faux.lances) == 9 and m.reveils == {}
    journaux = "".join(f.read_text("utf-8") for f in (config.donnees / "journal").rglob("mere-*.jsonl"))
    assert "plus de réveil automatique" in journaux


def test_arret_du_tour_annule_le_reveil(config, vault, faux):
    faux.scenario = erreur(QUOTA)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        assert "mere" in m.reveils
        await m.arreter("mere")
        return m

    m = asyncio.run(scenario())
    assert m.reveils == {} and m.etat_de("mere") == "inactif"
    assert json.loads((config.donnees / "etat" / "reveils.json").read_text("utf-8")) == {}


def test_reprendre_maintenant_relance_sans_attendre_l_heure(config, vault, faux):
    faux.scenario = erreur(QUOTA)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        faux.scenario = scenario_ok()
        m.reprendre_maintenant("mere")
        await attendre(lambda: len(faux.lances) == 2)
        await finir(m)
        return m

    m = asyncio.run(scenario())
    assert m.reveils == {} and not vault.tache("mere").fm.get("echec_tour")


def test_reveil_survit_a_un_redemarrage_du_serveur(config, vault, faux):
    faux.scenario = erreur(QUOTA)

    async def avant():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        await m.fermer()

    asyncio.run(avant())
    fichier = config.donnees / "etat" / "reveils.json"
    reveils = json.loads(fichier.read_text("utf-8"))
    assert "mere" in reveils  # l'arrêt du serveur garde l'état
    reveils["mere"]["a"] = (dt.datetime.now() - dt.timedelta(seconds=1)).isoformat(timespec="seconds")
    fichier.write_text(json.dumps(reveils), encoding="utf-8")
    faux.scenario = scenario_ok()

    async def apres():
        m = Moteur(config, vault, {"faux": faux})
        assert "mere" in m.reveils  # relu du disque
        m.demarrer_reveils()
        await attendre(lambda: len(faux.lances) == 2)
        await finir(m)
        return m

    m = asyncio.run(apres())
    assert m.reveils == {} and not vault.tache("mere").fm.get("echec_tour")


def test_tour_repris_d_office_apres_redemarrage_n_est_pas_aussi_reveille(config, vault, faux):
    from fastapi.testclient import TestClient
    from orchestrateur import api

    faux.scenario = erreur(QUOTA)

    async def avant():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "travaille")
        await finir(m)
        await m.fermer()

    asyncio.run(avant())  # un réveil est programmé pour demain ou plus tard
    (config.donnees / "etat" / "tours.json").write_text(json.dumps([{
        "tache": "mere", "texte": "travaille", "sauts": 0, "de": "", "source": "", "mandat": False,
        "role": "", "reprise": False}]), encoding="utf-8")  # …et un tour était actif à l'arrêt
    faux.scenario = scenario_ok()
    m2 = Moteur(config, vault, {"faux": faux})
    assert "mere" in m2.reveils and m2.interrompus.keys() == {"mere"}
    with TestClient(api.creer_app(config, m2), base_url="http://127.0.0.1:8399"):
        assert "mere" not in m2.reveils and "mere" not in m2.minuteries  # reprise OU réveil, pas les deux
        deadline = dt.datetime.now() + dt.timedelta(seconds=10)
        while len(faux.lances) < 2 and dt.datetime.now() < deadline:
            import time
            time.sleep(0.05)
    assert len(faux.lances) == 2  # la reprise d'office, une seule fois
