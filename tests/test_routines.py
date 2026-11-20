"""Routines programmées : analyse des programmes, échéances, rattrapage, file, pause, issue (INV-ROUTINE-*)."""

import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import scenario_ok
from orchestrateur import api, decisions, programme
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.routines import Routines
from orchestrateur.vault import Conflit, Invalide
from test_api import BASE, H

D = dt.datetime
LUNDI = D(2026, 11, 16, 7, 0)  # un lundi


class Horloge:
    def __init__(self, t: D):
        self.t = t

    def __call__(self) -> D:
        return self.t


def executer(coro):
    return asyncio.run(coro)


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def monde(config, vault, faux, t=LUNDI, **opts):
    m = Moteur(config, vault, {"faux": faux})
    h = Horloge(t)
    r = Routines(m, horloge=h)
    m.routines = r
    ident = r.creer("Revue du matin", "Fais la revue.", opts.pop("prog", "chaque jour 08:00"),
                    "Projets/C1-Alpha", harnais="faux", **opts)
    return m, h, r, ident


# --- programme -------------------------------------------------------------------------
@pytest.mark.parametrize("texte, apres, attendu", [
    ("chaque jour 08:00", LUNDI, D(2026, 11, 16, 8, 0)),
    ("tous les jours à 8h", D(2026, 11, 16, 8, 0), D(2026, 11, 17, 8, 0)),
    ("chaque jour 08:00,18:00", D(2026, 11, 16, 9, 0), D(2026, 11, 16, 18, 0)),
    ("en semaine 18:00", D(2026, 11, 20, 19, 0), D(2026, 11, 23, 18, 0)),  # vendredi soir → lundi
    ("lundi,jeudi 09:30", D(2026, 11, 16, 10, 0), D(2026, 11, 19, 9, 30)),
    ("chaque mardi à 07:15", LUNDI, D(2026, 11, 17, 7, 15)),
    ("toutes les 15 min", D(2026, 11, 16, 7, 7), D(2026, 11, 16, 7, 15)),
    ("toutes les 2 h de 8 h à 12 h", D(2026, 11, 16, 12, 0), D(2026, 11, 17, 8, 0)),
    ("30 9 * * 1-5", D(2026, 11, 21, 0, 0), D(2026, 11, 23, 9, 30)),  # samedi → lundi
    ("0 6 1 * *", LUNDI, D(2026, 12, 1, 6, 0)),
    ("0 0 29 2 *", LUNDI, D(2028, 2, 29, 0, 0)),
])
def test_programme_lisible_ou_cron_donne_la_prochaine_echeance(texte, apres, attendu):
    assert programme.prochaine(programme.analyser(texte), apres) == attendu


@pytest.mark.parametrize("texte", ["", "parfois", "chaque jour 25:00", "toutes les 7 min",
                                   "chaque jour 08:00,18:30", "61 * * * *", "funday 09:00"])
def test_programme_illisible_refuse_jamais_devine(texte):
    with pytest.raises(Invalide):
        programme.analyser(texte)


# --- création et échéances ---------------------------------------------------------------
def test_creation_ecrit_une_note_routine_sans_executer(config, vault, faux):
    m, h, r, ident = monde(config, vault, faux)
    t = vault.tache(ident)
    assert t.fm["nature"] == "routine" and t.fm["programme"] == "chaque jour 08:00"
    assert t.fm["routine"] == "active" and t.chemin.parent.name == "taches"
    assert r.public(ident)["prochaine"] == "2026-11-16T08:00"
    assert r.verifier() == [] and faux.lances == []
    with pytest.raises(Invalide):
        r.creer("X", "y", "jamais", "Projets/C1-Alpha")


def test_echeance_atteinte_soumet_un_tour_par_la_file_puis_reussie(config, vault, faux):
    async def scenario():
        m, h, r, ident = monde(config, vault, faux)
        h.t = D(2026, 11, 16, 8, 0, 30)
        assert r.verifier() == [ident]
        await finir(m)
        assert len(faux.lances) == 1 and "Fais la revue." in faux.lances[0]["message"]
        assert "exécution programmée" in faux.lances[0]["message"]
        p = r.public(ident)
        assert p["derniere"]["issue"] == "reussie" and p["derniere"]["session"] == "s-1"
        assert p["prochaine"] == "2026-11-17T08:00"
        assert r.verifier() == []  # la même échéance ne repart pas
        assert vault.tache(ident).statut != "fait"  # INV-EXEC-7 : une routine ne se termine jamais
    executer(scenario())


def test_longue_absence_un_seul_rattrapage(config, vault, faux):
    async def scenario():
        m, h, r, ident = monde(config, vault, faux)
        h.t = D(2026, 11, 20, 12, 0)  # quatre échéances manquées
        assert r.verifier() == [ident]
        await finir(m)
        assert r.verifier() == [] and len(faux.lances) == 1
        assert "exécution rattrapée" in faux.lances[0]["message"]
        assert r.public(ident)["prochaine"] == "2026-11-21T08:00"
    executer(scenario())


def test_rattrapage_aucune_saute_l_echeance_manquee(config, vault, faux):
    m, h, r, ident = monde(config, vault, faux, rattrapage="aucune")
    h.t = D(2026, 11, 16, 9, 0)
    assert r.verifier() == [] and faux.lances == []
    assert r.public(ident)["historique"][0]["issue"] == "sautee"


def test_jamais_deux_executions_simultanees(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-1"), "attendre", *scenario_ok()[1:]]
    faux.liberer = None

    async def scenario():
        m, h, r, ident = monde(config, vault, faux, prog="toutes les 5 min")
        h.t = D(2026, 11, 16, 7, 5)
        assert r.verifier() == [ident]
        await asyncio.sleep(0.05)
        with pytest.raises(Conflit):  # INV-ROUTINE-1 : « Exécuter maintenant » refusé
            r.executer(ident)
        h.t = D(2026, 11, 16, 7, 10)
        assert r.verifier() == []
        assert r.public(ident)["historique"][0]["motif"] == "exécution précédente non terminée"
        await m.arreter(ident)
        await finir(m)
        assert len(faux.lances) == 1
    executer(scenario())


def test_pause_suspend_et_reprise_ne_rattrape_pas(config, vault, faux):
    m, h, r, ident = monde(config, vault, faux)
    p = r.modifier(ident, pause=True)
    assert p["etat"] == "en-pause" and p["prochaine"] is None
    h.t = D(2026, 11, 18, 12, 0)
    assert r.verifier() == []
    p = r.modifier(ident, pause=False)
    assert p["etat"] == "active" and p["prochaine"] == "2026-11-19T08:00"
    assert r.verifier() == [] and faux.lances == []


def test_modifier_le_programme_recalcule_et_refuse_l_illisible(config, vault, faux):
    m, h, r, ident = monde(config, vault, faux)
    assert r.modifier(ident, "lundi 07:30")["prochaine"] == "2026-11-16T07:30"
    with pytest.raises(Invalide):
        r.modifier(ident, "bientôt")
    assert vault.tache(ident).fm["programme"] == "lundi 07:30"


def test_contexte_neuf_ouvre_une_conversation_neuve(config, vault, faux):
    async def scenario():
        m, h, r, ident = monde(config, vault, faux, contexte="neuf")
        r.executer(ident)
        await finir(m)
        r.executer(ident)
        await finir(m)
        assert [x["session"] for x in faux.lances] == [None, None]
    executer(scenario())


def test_echec_visible_dans_decisions_puis_efface_au_succes(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-1"), Evenement("erreur", texte="boum")]

    async def scenario():
        m, h, r, ident = monde(config, vault, faux)
        r.executer(ident)
        await finir(m)
        assert r.public(ident)["derniere"]["issue"] == "echouee"
        lignes = [d for d in decisions.rassembler(m)["decisions"] if d["genre"] == "routine"]
        assert len(lignes) == 1 and "boum" in lignes[0]["question"]
        r.modifier(ident, pause=True)  # la pause vaut réponse
        assert not [d for d in decisions.rassembler(m)["decisions"] if d["genre"] == "routine"]
        r.modifier(ident, pause=False)
        faux.scenario = scenario_ok()
        r.executer(ident)
        await finir(m)
        assert not [d for d in decisions.rassembler(m)["decisions"] if d["genre"] == "routine"]
    executer(scenario())


# --- API et arbre -------------------------------------------------------------------------
def test_api_creer_modifier_executer_et_arbre_annote(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        corps = {"titre": "Veille", "consigne": "Lis les nouvelles.", "programme": "en semaine 09:00",
                 "conteneur": "Projets/C1-Alpha", "harnais": "faux"}
        res = c.post("/api/routines", json=corps, headers=H)
        assert res.status_code == 201, res.text
        ident = res.json()["id"]
        assert c.post("/api/routines", json={**corps, "programme": "jamais"}, headers=H).status_code == 400
        assert c.post(f"/api/routines/{ident}/modifier", json={"pause": True}, headers=H).json()["etat"] == "en-pause"
        assert c.post(f"/api/routines/{ident}/executer", headers=H).status_code == 202
        for _ in range(200):
            if c.get(f"/api/taches/{ident}").json()["etat_execution"] == "inactif":
                break
        noeuds = [n for n in _aplatir(c.get("/api/arbre").json()) if n.get("id") == ident]
        assert noeuds and noeuds[0]["routine"]["etat"] == "en-pause"
        assert [x["id"] for x in c.get("/api/routines").json()["routines"]] == [ident]


def _aplatir(arbre):
    pile = list(arbre["noeuds"])
    while pile:
        n = pile.pop()
        pile.extend(n.get("enfants") or [])
        yield n


def test_convertir_une_tache_existante_puis_la_retirer(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    r = Routines(m, horloge=Horloge(LUNDI))
    m.routines = r
    ident = m.creer("Revue", "Fais la revue.", "Projets/C1-Alpha", harnais="faux")
    avant = vault.tache(ident)
    p = r.convertir(ident, "chaque jour 08:00")
    t = vault.tache(ident)
    assert p["prochaine"] == "2026-11-16T08:00" and t.fm["nature"] == "routine"
    assert t.statut == avant.statut and t.chemin == avant.chemin  # sur place, statut intact
    with pytest.raises(Conflit):
        r.convertir(ident, "chaque jour 09:00")
    r.retirer(ident)
    assert "nature" not in vault.tache(ident).fm and ident not in r._routines()


def test_convertir_programme_illisible_n_ecrit_rien(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    r = Routines(m, horloge=Horloge(LUNDI))
    ident = m.creer("Revue", "x", "Projets/C1-Alpha", harnais="faux")
    with pytest.raises(Invalide):
        r.convertir(ident, "quand ça me chante")
    assert "nature" not in vault.tache(ident).fm
