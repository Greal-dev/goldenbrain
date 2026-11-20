"""INV-NATIF-1 : interface native du harnais — ouverture dans un onglet, tâche « au terminal »
(aucun tour, messages en file), relais à la fermeture (fiche, reprise d'un tour coupé, file)."""

import asyncio
import json
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, fiches, natif
from orchestrateur.harnais import Message
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit
from conftest import RENDU, FauxHarnais, scenario_ok

H = {"X-Orchestrateur": "1"}


class FauxNatif(FauxHarnais):
    """Harnais factice qui sait ouvrir son interface native ; transcript piloté par le test."""

    echange: list = []

    def transcript(self, session, limite):
        return list(type(self).echange)

    def argv_natif(self, session, neuve, consigne, modele, message):
        return ["faux", "--session-id" if neuve else "--resume", session, consigne, message]


@pytest.fixture
def faux_natif(faux):
    return type("FauxN", (FauxNatif, faux), {"echange": []})


@pytest.fixture
def onglet(monkeypatch):
    """Remplace le terminal : enregistre l'onglet ; la fermeture = `ferme.set()`."""
    etat = {"onglets": [], "ferme": None}

    async def attendre(fichier_pid, demarrage_s=0):
        await etat["ferme"].wait()

    monkeypatch.setattr(natif, "ouvrir_onglet", lambda t, d, a: etat["onglets"].append((t, d, a)))
    monkeypatch.setattr(natif, "attendre_fin", attendre)
    return etat


async def _finir(m):
    for _ in range(50):
        await asyncio.sleep(0)
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def test_ouverture_sans_session_prepare_la_session_et_retient_les_messages(
        config, vault, faux_natif, onglet):
    async def scenario():
        onglet["ferme"] = asyncio.Event()
        m = Moteur(config, vault, {"faux": faux_natif})
        r = m.natif.ouvrir("mere")
        faux_natif.scenario = scenario_ok(session=r["session"])
        occ = m.occupation("mere")
        etat = m.soumettre("mere", "message pendant le terminal")
        await asyncio.sleep(0.05)
        lances = list(faux_natif.lances)
        onglet["ferme"].set()
        await _finir(m)
        return m, r, occ, etat, lances

    m, r, occ, etat, lances = asyncio.run(scenario())
    t = vault.tache("mere")
    assert t.fm["session"] == r["session"] and t.fm["harnais"] == "faux"
    spec = json.loads((config.donnees / "etat/natif/mere.json").read_text("utf-8"))
    assert spec["argv"][:3] == ["faux", "--session-id", r["session"]]
    assert "Tâche Mère" in spec["argv"][3] and "Interface native ouverte" in spec["argv"][4]
    assert spec["env"]["ORCH_TACHE"] == "mere"
    titre, _, argv = onglet["onglets"][0]
    assert titre == "Mère" and argv[-2:] == ["natif", str(config.donnees / "etat/natif/mere.json")]
    assert occ["terminal"] is True and occ["titre"] == "Mère"
    assert etat == "en_file" and lances == []  # aucun tour tant que l'interface est ouverte
    # Fermeture : la file est traitée sur la même session.
    assert [x["message"] for x in faux_natif.lances] == ["message pendant le terminal"]
    assert faux_natif.lances[0]["session"] == r["session"]
    assert m.occupation("mere") is None


def test_fermeture_en_plein_tour_reprend_en_arriere_plan_puis_traite_la_file(
        config, vault, faux_natif, onglet):
    vault.modifier("mere", {"session": "s-1", "harnais": "faux"})
    faux_natif.echange = [Message("assistant", "ancien échange")]

    async def scenario():
        onglet["ferme"] = asyncio.Event()
        m = Moteur(config, vault, {"faux": faux_natif})
        m._q = m.abonner()
        m.natif.ouvrir("mere")
        m.soumettre("mere", "message en attente")
        # L'utilisateur a demandé un travail ; l'agent appelait un outil quand l'onglet s'est fermé.
        faux_natif.echange += [Message("utilisateur", "corrige le module"),
                               Message("assistant", "je lis", ["Read"])]
        onglet["ferme"].set()
        await _finir(m)
        evts = []
        while not m._q.empty():
            evts.append(m._q.get_nowait())
        return evts

    evts = asyncio.run(scenario())
    messages = [x["message"] for x in faux_natif.lances]
    assert messages[0].startswith("[GoldenBrain — reprise]") and messages[1] == "message en attente"
    assert all(x["session"] == "s-1" for x in faux_natif.lances)
    assert {"type": "natif_fin", "tache": "mere", "reprise": True} in evts


def test_fermeture_apres_reponse_finale_met_la_fiche_a_jour_sans_reprise(
        config, vault, faux_natif, onglet):
    vault.modifier("mere", {"session": "s-1", "harnais": "faux", "statut": "en-cours"})

    async def scenario():
        onglet["ferme"] = asyncio.Event()
        m = Moteur(config, vault, {"faux": faux_natif})
        m.natif.ouvrir("mere")
        faux_natif.echange = [Message("utilisateur", "fais-le"), Message("assistant", "je lis", ["Read"]),
                              Message("assistant", RENDU)]
        onglet["ferme"].set()
        await _finir(m)

    asyncio.run(scenario())
    t = vault.tache("mere")
    assert fiches.lire_fiche(fiches.lire(t.chemin))["fait"] == "lu le dossier"
    assert t.fm["statut"] == "retour-humain"  # fiche sans `statut:` = en attente de l'utilisateur
    assert faux_natif.lances == []


def test_ouverture_refusee_pendant_un_tour_deux_fois_ou_sans_session_hors_claude(
        config, vault, faux, faux_natif, onglet):
    async def scenario():
        onglet["ferme"] = asyncio.Event()
        m = Moteur(config, vault, {"faux": faux})
        with pytest.raises(Conflit, match="ne sait pas démarrer"):
            m.natif.ouvrir("mere")  # harnais sans `argv_natif`, tâche sans session
        vault.modifier("mere", {"session": "s-1"})
        m.natif.ouvrir("mere")  # reprise : la commande de terminal du harnais suffit
        with pytest.raises(Conflit, match="déjà ouverte"):
            m.natif.ouvrir("mere")
        m.etats["enfant"] = "en_cours"
        with pytest.raises(Conflit, match="séance de travail est en cours"):
            m.natif.ouvrir("enfant")
        onglet["ferme"].set()
        await _finir(m)

    asyncio.run(scenario())
    spec = json.loads((config.donnees / "etat/natif/mere.json").read_text("utf-8"))
    assert spec["commande"] == "faux --resume s-1"


def test_route_natif_et_demi_verrou_vous_travaillez_au_terminal(config, vault, faux, onglet):
    vault.modifier("mere", {"session": "s-1"})
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url="http://127.0.0.1:8399") as c:
        onglet["ferme"] = asyncio.Event()
        r = c.post("/api/taches/mere/natif", headers=H)
        assert r.status_code == 200 and r.json()["session"] == "s-1"
        assert c.get("/api/etat").json()["occupees"]["mere"]["terminal"] is True
        r = c.post("/api/taches/mere/statut", headers=H, json={"statut": "fait"})
        assert r.status_code == 409 and r.json()["detail"].startswith("Vous travaillez au terminal")
        assert c.post("/api/taches/mere/natif", headers=H).status_code == 409


def test_relais_ecrit_son_pid_et_rend_le_code_du_harnais(tmp_path):
    fichier = tmp_path / "t.json"
    fichier.write_text(json.dumps({"argv": [sys.executable, "-c", "import sys; sys.exit(3)"],
                                   "dossier": str(tmp_path), "env": {"ORCH_TACHE": "t"}}), "utf-8")
    assert cli.main(["natif", str(fichier)]) == 3
    assert int((tmp_path / "t.pid").read_text("utf-8")) > 0


def test_attendre_fin_suit_le_processus_reel(tmp_path):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
    (tmp_path / "p.pid").write_text(str(proc.pid), "utf-8")
    debut = time.monotonic()
    asyncio.run(natif.attendre_fin(tmp_path / "p.pid"))
    assert time.monotonic() - debut >= 1 and proc.wait(5) == 0
    debut = time.monotonic()  # relais jamais lancé : l'attente se borne au délai de démarrage
    asyncio.run(natif.attendre_fin(tmp_path / "absent.pid", demarrage_s=0.2))
    assert time.monotonic() - debut < 3


def test_attendre_fin_rend_la_main_sur_un_zombie_non_reclame(tmp_path):
    # Symptôme (Linux) : le relais fini mais non « wait »-é restait vivant pour `kill 0`, attente infinie.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    (tmp_path / "z.pid").write_text(str(proc.pid), "utf-8")
    time.sleep(0.5)  # fini, jamais réclamé
    asyncio.run(asyncio.wait_for(natif.attendre_fin(tmp_path / "z.pid"), 5))
    proc.wait()
