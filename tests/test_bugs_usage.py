"""Défauts relevés à l'usage (14/11) : INV-EXEC-6, INV-EXEC-7, mandat sans tour, conversation."""

import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, conseil
from orchestrateur import transformations as T
from orchestrateur.config import ConfigConseil
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import ecrire, tache_md
from test_moteur import executer, finir, moteur, vider

H = {"X-Orchestrateur": "1"}


@pytest.mark.parametrize("nature,statut", [("permanente", "en-cours"), ("recurrente", "en-cours"),
                                           ("ponctuelle", "fait")])
def test_tache_permanente_ne_passe_jamais_a_terminee(config, vault, faux, racine, nature, statut):
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md",
           tache_md(extra=f"nature: {nature}\n", titre="Mère"))
    faux.scenario = [Evenement("fin", session="s", texte=(
        "ok\n<fiche>\nstatut: terminee\nfait: x\nsituation: y\nreste: z\nprochain_pas: p\n"
        "sous_taches:\n</fiche>"))]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
    executer(scenario())
    assert vault.tache("mere").statut == statut


def test_exception_de_conclusion_journalisee_et_publiee(config, vault, faux, caplog, monkeypatch):
    def boum(*a, **k):
        raise RuntimeError("boum")
    monkeypatch.setattr(T, "conclure", boum)

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        m.soumettre("mere", "encore")
        await finir(m)
        return m, vider(m)
    with caplog.at_level(logging.ERROR):
        m, evs = executer(scenario())
    assert "boucle de la tâche mere" in caplog.text
    assert any(e["type"] == "tour_fin" and "boum" in e.get("erreur", "") for e in evs)
    assert len(faux.lances) == 2  # la file continue


def test_mandat_sans_tour_signale(config, vault, faux, monkeypatch):
    async def echec(self, ident, envoi):
        raise RuntimeError("avant le tour")
    monkeypatch.setattr(Moteur, "_tour", echec)

    async def scenario():
        m = moteur(config, vault, faux)
        m.mandats.poser("mere", "decoupage", "Lancement")
        m.soumettre("mere", "mandat", mandat=True)
        await finir(m)
        return m, vider(m)
    m, evs = executer(scenario())
    assert {"type": "mandat_sans_tour", "tache": "mere"} in evs
    assert m.etat_global()["mandats_sans_tour"] == ["mere"]


def test_mandat_avec_tour_pas_signale(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.mandats.poser("mere", "decoupage", "Lancement")
        m.soumettre("mere", "mandat", mandat=True)
        await finir(m)
        return m, vider(m)
    m, evs = executer(scenario())
    assert not any(e["type"] == "mandat_sans_tour" for e in evs)
    assert m.etat_global()["mandats_sans_tour"] == []


def test_conseil_transmet_le_corps_de_la_tache(config, vault, faux, racine):
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md", tache_md(titre="Mère").replace(
        "Corps.", "Refaire toute la facturation des loyers."))
    config.conseil = ConfigConseil(harnais="faux", modele="petit", delai_s=5)
    faux.scenario = [Evenement("fin", texte="<conseil>\navis: favorable\nmotif: ok\n</conseil>")]
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        c.post("/api/conseil", headers=H, json={"action": "promouvoir", "tache": "mere"})
    assert "Refaire toute la facturation des loyers." in faux.lances[0]["message"]


def test_conversation_montre_le_message_du_tour_en_cours(config, vault, faux):
    faux.scenario = ["attendre"]
    faux.liberer = None

    async def scenario():
        m = moteur(config, vault, faux)
        app = api.creer_app(config, m)
        m.soumettre("mere", "Premier message")
        await asyncio.sleep(0.2)
        with TestClient(app, base_url="http://127.0.0.1:8399") as c:
            r = await asyncio.to_thread(c.get, "/api/taches/mere/conversation")
        await m.arreter("mere")
        await finir(m)
        return r
    r = executer(scenario())
    assert [(x["role"], x["texte"]) for x in r.json()] == [("utilisateur", "Premier message")]
