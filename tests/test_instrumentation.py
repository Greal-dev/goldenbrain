"""Instrumentation (mesures.jsonl) : attentes avant lancement, RSS et petits-fils, contexte borné,
trace des sondes et durée de gel. Horloges et sondes factices ; aucun accès réseau."""

import asyncio
import json
import logging
import os

import pytest

from conftest import ecrire, scenario_ok, tache_md
from orchestrateur import instrumentation
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from test_reseau import COUPE, Sonde, finir, moteur as moteur_reseau


def lignes(m, type_=None):
    try:
        tous = [json.loads(x) for x in m.mesures.fichier.read_text("utf-8").splitlines()]
    except OSError:
        return []
    return [t for t in tous if t.get("type") == type_]


class Pas:
    """Horloge factice : chaque lecture avance d'un pas, `t` se règle à la main."""

    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# --- attentes ----------------------------------------------------------------------------
def test_attente_du_poste_et_de_la_file_mesurees_au_lancement(config, vault, faux, racine, monkeypatch):
    ecrire(racine, "Projets/C1-Alpha/taches/lourde.md", tache_md(extra="epreuves: lourdes\n", titre="Lourde"))
    h = Pas()
    monkeypatch.setattr(instrumentation, "horloge", h)

    async def essai():
        m = Moteur(config, vault, {"faux": faux})
        m.INTERVALLE_POSTE_S = 0.01
        m.poste.reserver("mere", "porte complète")
        m.soumettre("lourde", "go")  # mise en file à t = 100
        await asyncio.sleep(0.1)
        h.t = 142.0  # 42 s plus tard le poste est libéré
        m.poste.liberer("mere")
        await finir(m)
        return m

    m = asyncio.run(essai())
    (a,) = lignes(m, "attente")
    assert a["tache"] == "lourde" and a["poste_s"] == 42.0 and a["file_s"] == 42.0
    assert a["prerequis_s"] == 0.0 and a["reseau_s"] == 0.0 and a["creneau_s"] == 0.0


def test_attente_sans_poste_ni_prerequis_est_nulle(config, vault, faux):
    async def essai():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "go")
        await finir(m)
        return m

    (a,) = lignes(asyncio.run(essai()), "attente")
    assert a["poste_s"] == a["prerequis_s"] == a["reseau_s"] == 0.0 and a["file_s"] >= 0


# --- mémoire ------------------------------------------------------------------------------
def _faux_proc(tmp_path, arbre):
    """/proc factice : arbre = {pid: (ppid, rss_ko ou None)}."""
    for pid, (pp, rss) in arbre.items():
        d = tmp_path / str(pid)
        d.mkdir()
        corps = f"Name:\tx\nPPid:\t{pp}\n" + (f"VmRSS:\t{rss} kB\n" if rss else "")
        (d / "status").write_text(corps, encoding="utf-8")
    return str(tmp_path)


class FauxProc:
    def __init__(self, pid):
        self.pid = pid


class FauxHarnaisPid:
    def __init__(self, pid):
        self._proc = FauxProc(pid)


def test_rss_du_fils_et_petits_fils_comptes(tmp_path):
    racine = _faux_proc(tmp_path, {10: (1, 51200), 11: (10, 100), 12: (10, 100), 13: (11, 100),
                                   14: (13, 100), 99: (1, 100)})
    r = instrumentation.echantillon(FauxHarnaisPid(10), racine)
    assert r == {"rss_ko": 51200, "petits_fils": 2}  # 13 (fils de 11) et 14 (fils de 13) ; 11 et 12 sont des enfants directs


def test_rss_silencieux_sans_proc_ni_pid_ni_processus(tmp_path):
    assert instrumentation.echantillon(FauxHarnaisPid(10), str(tmp_path / "absent")) == {}
    assert instrumentation.echantillon(object(), str(tmp_path)) == {}
    assert instrumentation.echantillon(FauxHarnaisPid(777), str(tmp_path)) == {}


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="POSIX seulement")
def test_rss_du_processus_courant_lu_dans_proc():
    r = instrumentation.echantillon(FauxHarnaisPid(os.getpid()))
    assert r["rss_ko"] > 0 and r["petits_fils"] >= 0


def test_rss_et_petits_fils_ecrits_en_fin_de_tour(config, vault, faux, monkeypatch):
    monkeypatch.setattr(instrumentation, "echantillon", lambda h: {"rss_ko": 4242, "petits_fils": 3})

    async def essai():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "go")
        await finir(m)
        return m

    m = asyncio.run(essai())
    t = [x for x in (json.loads(l) for l in m.mesures.fichier.read_text("utf-8").splitlines()) if "type" not in x]
    assert t[0]["rss_ko"] == 4242 and t[0]["petits_fils"] == 3


# --- contexte borné -----------------------------------------------------------------------
def test_contexte_superieur_a_la_fenetre_est_ecarte():
    b = instrumentation.borner_contexte
    assert b(250_000, 200_000) is None and b(150_000, 200_000) == 150_000
    assert b(None, 200_000) is None and b(-1, 200_000) is None and b(True, 200_000) is None


def test_mesure_contexte_d_un_harnais_non_claude_hors_fenetre_est_nulle(config, vault, faux):
    classe = type("FauxCodex", (faux,), {"lances": [], "arrets": [], "scenario": [
        Evenement("fin", session="s", texte="ok", mesure={"contexte": 9_000_000, "cout": None})]})

    async def essai():
        m = Moteur(config, vault, {"faux": classe})
        m.soumettre("mere", "go")
        await finir(m)
        return m

    m = asyncio.run(essai())
    t = [x for x in (json.loads(l) for l in m.mesures.fichier.read_text("utf-8").splitlines()) if "type" not in x]
    assert t[0]["contexte"] is None and not m._dernier.get("mere")  # pas de compactage déclenché à tort


def test_synthese_ignore_les_lignes_d_instrumentation(config, vault, faux):
    async def essai():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "go")
        await finir(m)
        return m

    m = asyncio.run(essai())
    assert lignes(m, "attente") and sum(s["tours"] for s in m.mesures.synthese()) == 1


# --- gel réseau ---------------------------------------------------------------------------
def test_gel_simule_une_ligne_par_sonde_et_duree_de_gel_a_la_levee(config, vault, faux, caplog):
    horloge, pauses = [0.0], []

    async def dormir(d):
        pauses.append(d)
        horloge[0] += d
        await asyncio.sleep(0)

    sonde = Sonde(a=False, b=False)
    m = moteur_reseau(config, vault, faux, sonde, dormir=dormir)
    m.reseau.dormir, m.reseau.horloge = dormir, lambda: horloge[0]
    faux.scenario = [Evenement("erreur", texte=COUPE)]
    caplog.set_level(logging.INFO, logger="orchestrateur.reseau")

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        faux.scenario = scenario_ok()
        while len(pauses) < 3:
            await asyncio.sleep(0)
        sonde.etat.update(a=True, b=True)
        await m.reseau._veille
        await finir(m)

    asyncio.run(essai())
    sondes = [r.getMessage() for r in caplog.records if r.getMessage().startswith("réseau : sonde ")]
    # 2 hôtes (a, b) × 4 tours de sonde : confirmation + 2 de veille muets, puis 1 qui répond
    assert len(sondes) == 2 * 4 and sum("-> muet" in s for s in sondes) == 6
    assert all(" en " in s and " s" in s for s in sondes)
    arret = [r.getMessage() for r in caplog.records if "boucle de veille arrêtée" in r.getMessage()]
    assert len(arret) == 1 and "tous les fournisseurs répondent" in arret[0]
    gels = lignes(m, "gel")
    glob = [g for g in gels if g["portee"] == "reseau"]
    tache = [g for g in gels if g["portee"] == "tache"]
    assert len(glob) == 1 and glob[0]["gel_s"] == 360.0  # 3 pauses de 2 min sur l'horloge factice
    assert len(tache) == 1 and tache[0]["tache"] == "mere" and tache[0]["gel_s"] == 360.0


def test_arret_de_la_veille_sur_fermeture_du_serveur_est_trace(config, vault, faux, caplog):
    sonde = Sonde(a=False, b=False)

    async def dormir(d):
        await asyncio.sleep(0)

    m = moteur_reseau(config, vault, faux, sonde, dormir=dormir)
    faux.scenario = [Evenement("erreur", texte=COUPE)]
    caplog.set_level(logging.INFO, logger="orchestrateur.reseau")

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        m.ferme = True
        await m.reseau._veille

    asyncio.run(essai())
    assert any("boucle de veille arrêtée" in r.getMessage() and "serveur fermé" in r.getMessage()
               for r in caplog.records)
