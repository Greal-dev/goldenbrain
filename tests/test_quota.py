"""Quota épuisé : bascule unique (INV-QUOTA-1), guet du journal OpenCode (INV-QUOTA-2), incidents
(INV-INCIDENT-1), diagnostic Linux de la vigie. Faux harnais et vault temporaire seulement."""

import asyncio
import datetime as dt
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, diagnostic, incidents, roles
from orchestrateur.config import ConfigRole
from orchestrateur.harnais import Evenement
from orchestrateur.harnais import opencode
from orchestrateur.moteur import Moteur
from conftest import FauxHarnais, scenario_ok
from test_moteur import executer, finir
from test_revues import OK, evs, persona

QUOTA = "Free usage limit reached. Upgrade, or try again at 3:14 PM."


def erreur(texte=QUOTA):
    return [Evenement("session", session="s-1"), Evenement("erreur", texte=texte)]


@pytest.fixture(autouse=True)
def _executables(monkeypatch):
    monkeypatch.setattr(roles, "resoudre", lambda commande: [commande])


@pytest.fixture
def secours():
    return type("Secours", (FauxHarnais,), {"scenario": scenario_ok("s-2"), "lances": [], "arrets": [],
                                            "liberer": None})


@pytest.fixture
def reg(config, faux, secours):
    config.harnais = {"faux": {}, "secours": {}}
    faux.scenario = erreur()
    return {"faux": faux, "secours": secours}


def lancer(config, vault, reg, ident="mere"):
    async def scenario():
        m = Moteur(config, vault, reg)
        m.soumettre(ident, "travaille")
        await finir(m)
        return m

    return executer(scenario())


# --- bascule d'un tour de tâche ---------------------------------------------------------------
def test_quota_bascule_une_fois_sur_un_autre_compte_et_aboutit(config, vault, reg, secours):
    m = lancer(config, vault, reg)
    assert len(reg["faux"].lances) == 1 and len(secours.lances) == 1
    assert "travaille" in secours.lances[0]["message"]
    t = vault.tache("mere")
    assert t.fm["harnais"] == "secours" and not t.fm.get("moteur_impose")
    assert m.reveils == {} and m.quota.epuise("faux") and "faux" in m.economie.public()["epuises"]
    inc = m.incidents.public()[0]
    assert inc["cause"] == "quota" and "relancé une fois sur secours" in inc["action"]
    assert m.incidents.dernier("mere") is None  # tour de secours abouti : bandeau levé


def test_bascule_jamais_en_boucle_quand_le_secours_est_aussi_epuise(config, vault, reg, secours):
    secours.scenario = erreur("429 quota exceeded")
    m = lancer(config, vault, reg)
    assert len(reg["faux"].lances) == 1 and len(secours.lances) == 1  # une seule bascule
    assert "mere" in m.reveils  # puis attente de la reprise (INV-EXEC-10)
    assert m.incidents.dernier("mere")["action"].startswith("attente de la reprise")


def test_moteur_impose_attend_la_reprise_sans_basculer(config, vault, reg, secours):
    vault.modifier("mere", {"moteur_impose": True, "harnais": "faux"})
    m = lancer(config, vault, reg)
    assert not secours.lances and "mere" in m.reveils


def test_attente_desactivee_ne_programme_aucun_reveil(config, vault, reg, secours):
    config.economie.quota_bascule = False
    config.economie.quota_attente = False
    m = lancer(config, vault, reg)
    assert not secours.lances and m.reveils == {}
    assert m.incidents.dernier("mere")["action"] == "tâche bloquée, message gardé en file jusqu'au déblocage"


def test_compte_epuise_ecarte_du_secours_jusqu_a_sa_reprise(config, vault, reg):
    async def scenario():
        m = Moteur(config, vault, reg)
        m.quota.noter("secours", "usage limit, retry in 2 hours")
        return m

    m = executer(scenario())
    assert m.quota.secours("", set()) == ("faux", "")
    m.quota.epuises["secours"] = (dt.datetime.now() - dt.timedelta(minutes=1)).isoformat()
    assert m.quota.secours("", {"faux"}) == ("secours", "") and "secours" not in m.quota.public()


# --- tours de rôle (revue, persona) -------------------------------------------------------------
def test_revue_en_quota_secourue_une_fois_sur_un_autre_compte(config, vault, reg, secours):
    config.harnais["tiers"] = {}
    reg["tiers"] = type("Tiers", (FauxHarnais,), {"scenario": evs("p-1", OK), "lances": [], "arrets": [],
                                                  "liberer": None})
    secours.scenario = erreur("429 quota exceeded")
    config.moteurs_par_role = {"persona": ConfigRole("secours", "flash")}

    async def scenario():
        m = Moteur(config, vault, reg)
        for p in m.revues.equipe.lister():
            m.revues.equipe.retirer(p["id"])
        persona(m, "rssi", "RSSI")
        return m, await m.revues._tour("mere", m.revues.equipe.lister()[0], "revue")

    m, avis = executer(scenario())
    assert avis["verdict"] == "ok" and len(reg["tiers"].lances) == 1
    assert m.quota.epuise("secours") and m.quota.epuise("faux")


# --- guet du journal OpenCode ---------------------------------------------------------------------
LIGNE = ('ERROR 2026-11-18T10:00:00 +1ms service=llm session.id={sid} level=ERROR '
         'error.error="AI_APICallError: Free usage limit reached. Please try again later." stream error\n')


def test_quota_lu_dans_le_journal_pour_la_seule_session_du_tour():
    lignes = [LIGNE.format(sid="ses_a"), "INFO service=bus level=INFO type=message"]
    assert "Free usage limit" in opencode.quota_du_journal(lignes, "ses_a")
    assert opencode.quota_du_journal(lignes, "ses_b") == ""


class ProcVivant:
    """Processus d'`opencode run` qui reste vivant après l'erreur : ne s'arrête que sur ordre."""

    code = None

    def __init__(self):
        self.stop = asyncio.Event()

    async def lignes(self, argv, message, dossier, env):
        yield {"type": "step_start", "sessionID": "ses_a"}
        await self.stop.wait()

    async def arreter(self):
        self.stop.set()
        self.code = -15

    def fin_anormale(self):
        return "arrêté"


def test_harnais_reste_vivant_apres_un_quota_le_guet_arrete_le_tour(tmp_path, monkeypatch):
    monkeypatch.setattr(opencode, "GUET_S", 0.05)
    journal = tmp_path / "log"
    journal.mkdir()
    (journal / "a.log").write_text("ancien\n", encoding="utf-8")
    h = opencode.HarnaisOpencode({"journal": str(journal)})
    h._p = ProcVivant()

    async def scenario():
        evs_ = []

        async def ecrire():
            await asyncio.sleep(0.15)
            with open(journal / "a.log", "a", encoding="utf-8") as f:
                f.write(LIGNE.format(sid="ses_a"))

        tache = asyncio.ensure_future(ecrire())
        async for ev in h.lancer("x", session=None, deriver=False, consigne="", env={}):
            evs_.append(ev)
        await tache
        return evs_

    evs_ = asyncio.run(asyncio.wait_for(scenario(), 5))
    assert [e.type for e in evs_] == ["session", "erreur"] and "Free usage limit" in evs_[-1].texte
    assert "Free usage limit" in h.derniere_trace()


# --- diagnostic Linux de la vigie -----------------------------------------------------------------
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="lecture de /proc")
def test_diagnostic_linux_voit_le_processus_courant_et_son_temps_processeur():
    procs = diagnostic.processus()
    moi = next(p for p in procs if p.pid == os.getpid())
    assert moi.parent == os.getppid() and "python" in moi.commande.lower()
    sum(i * i for i in range(200000))
    assert diagnostic.temps_cpu([os.getpid()]) > 0


# --- incidents ------------------------------------------------------------------------------------
def test_classer_donne_cause_lisible_et_geste():
    assert incidents.classer(QUOTA)[0] == "quota" and "3:14 PM" in incidents.classer(QUOTA)[1]
    assert incidents.classer("tour interrompu")[0] == "arret"
    assert incidents.classer("durée maximale du tour dépassée")[0] == "duree"
    assert incidents.classer("boum")[0] == "autre"


def test_incidents_persistent_et_s_exposent_par_l_api(config, vault, reg):
    lancer(config, vault, {"faux": reg["faux"]})  # pas de secours : attente
    sur_disque = json.loads((config.donnees / "etat" / "incidents.json").read_text("utf-8"))
    assert sur_disque[-1]["tache"] == "mere" and sur_disque[-1]["cause"] == "quota"
    m2 = Moteur(config, vault, {"faux": reg["faux"]})
    assert m2.incidents.dernier("mere")["libelle"].startswith("Quota épuisé")
    with TestClient(api.creer_app(config, m2), base_url="http://127.0.0.1:8399") as c:
        d = c.get("/api/incidents").json()
        assert d["incidents"][0]["titre"] == "Mère" and "faux" in d["epuises"]
        assert c.get("/api/taches/mere/vigie").json()["incident"]["cause"] == "quota"
