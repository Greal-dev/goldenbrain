"""Agents de Claude Code : inventaire, regroupement, rattachement, gestes (INV-AGENTSCC-1)."""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import agents_cc, api, decisions
from orchestrateur.config import ConfigAgentsCC
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from test_api import BASE, H


def job(jobs, nom_dossier, nom, session, maj, dossier, etat="done", detail="dernier mot de l'agent", **plus):
    d = jobs / nom_dossier
    d.mkdir(parents=True)
    etat_json = {"name": nom, "state": etat, "cwd": dossier, "sessionId": session, "resumeSessionId": session,
                 "createdAt": "2026-11-01T10:00:00.000Z", "updatedAt": maj, "detail": detail, **plus}
    (d / "state.json").write_text(json.dumps(etat_json), encoding="utf-8")


@pytest.fixture
def jobs(tmp_path):
    return tmp_path / "jobs"


@pytest.fixture
def depot_dir(tmp_path):
    return tmp_path / "depot-alpha"


@pytest.fixture
def monde(config, vault, faux, racine, jobs, depot_dir):
    depot_dir.mkdir()
    ecrire(racine, "Projets/C1-Depot/contexte.md",
           f"---\ntype: contexte\ncasquette: C1-Pro\nnom: Depot\ndepot: \"{depot_dir.as_posix()}\"\n---\n")
    ecrire(racine, "Projets/C1-Alpha/taches/audit-contrat.md", tache_md(titre="Audit du contrat fournisseur"))
    ecrire(racine, "Projets/C1-Alpha/taches/deja-pris.md", tache_md("a-faire", "session: autre\n", "Audit du contrat client"))
    ecrire(racine, "Projets/C1-Alpha/taches/lie.md", tache_md("en-cours", "session: s-lie-vieux\n", "Tâche liée"))
    config.agents_cc = ConfigAgentsCC(dossier=str(jobs))
    return Moteur(config, vault, {"faux": faux, "claude": faux})


def peupler(jobs, depot_dir):
    job(jobs, "a1", "Audit du contrat fournisseur", "s-a1", "2026-11-10T10:00:00.000Z", "C:\\Divers")
    job(jobs, "b1", "Atlas Audit", "s-b1", "2026-11-05T10:00:00.000Z", "C:\\Atlas")
    job(jobs, "b2", "atlas audit ⑂", "s-b2", "2026-11-12T10:00:00.000Z", "c:/atlas/")
    job(jobs, "b3", "Atlas Audit (2)", "s-b3", "2026-11-08T10:00:00.000Z", "C:\\Atlas")
    job(jobs, "b4", "Atlas Audit", "s-b4", "2026-11-09T10:00:00.000Z", "C:\\Ailleurs")
    job(jobs, "c1", "Avec le fil", "s-lie-vieux", "2026-11-11T10:00:00.000Z", "C:\\Divers")
    job(jobs, "d1", "Silencieux", "s-d1", "2026-11-02T10:00:00.000Z", str(depot_dir), detail="")
    job(jobs, "e1", "Dans le dépôt", "s-e1", "2026-11-13T10:00:00.000Z", str(depot_dir / "src"),
        detail="Il faut décider du format.")
    (jobs / "casse").mkdir()
    (jobs / "casse" / "state.json").write_text("{pas du json", encoding="utf-8")
    job(jobs, "sans-session", "Sans session", "", "2026-11-01T10:00:00.000Z", "C:\\X")


def par_nom(vue):
    return {(g["nom"], g["dossier"]): g for g in vue}


def test_inventaire_ignore_etat_illisible_et_agent_sans_session(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    agents = agents_cc.lire_jobs(jobs)
    assert len(agents) == 8 and all(a.session for a in agents)


def test_doublons_meme_nom_meme_dossier_un_groupe_le_plus_recent_titulaire(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    groupes = {g.titulaire.session: g for g in agents_cc.regrouper(agents_cc.lire_jobs(jobs))}
    atlas = groupes["s-b2"]  # « ⑂ », casse, « (2) » et barre finale ne séparent pas les doublons
    assert [a.session for a in atlas.historique] == ["s-b3", "s-b1"]
    assert "s-b4" in groupes  # même nom, autre dossier : un autre groupe


def test_rattachement_par_session_connue_aucune_decision(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    g = par_nom(monde.agents_cc.vue())[("Avec le fil", "C:\\Divers")]
    assert (g["action"], g["tache"], g["decision"]) == ("deja", "lie", False)


def test_rattachement_par_titre_jamais_une_tache_qui_a_deja_sa_conversation(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    g = par_nom(monde.agents_cc.vue())[("Audit du contrat fournisseur", "C:\\Divers")]
    assert (g["action"], g["tache"]) == ("rattacher", "audit-contrat")
    assert [c["tache"] for c in g["candidats"]] == ["audit-contrat"]  # « deja-pris » porte une session


def test_creation_proposee_dossier_vers_projet_et_clos_sans_message_ignore(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    vue = par_nom(monde.agents_cc.vue())
    e = vue[("Dans le dépôt", str(depot_dir / "src"))]
    assert (e["action"], e["conteneur"]) == ("creer", "Projets/C1-Depot")
    assert vue[("Silencieux", str(depot_dir))]["action"] == "ignorer"


def test_application_rattacher_pose_la_session_titulaire(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    g = par_nom(monde.agents_cc.vue())[("Audit du contrat fournisseur", "C:\\Divers")]
    res = monde.agents_cc.appliquer([{"id": g["id"], "action": "rattacher", "tache": "audit-contrat"}])
    assert res == {"faits": [g["id"]], "echecs": []}
    fm = monde.vault.tache("audit-contrat").fm
    assert (fm["session"], fm["harnais"]) == ("s-a1", "claude")  # reprise de la conversation d'origine
    assert not par_nom(monde.agents_cc.vue())[("Audit du contrat fournisseur", "C:\\Divers")]["decision"]


def test_application_creer_tache_dans_le_projet_avec_session_et_description(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    g = par_nom(monde.agents_cc.vue())[("Dans le dépôt", str(depot_dir / "src"))]
    monde.agents_cc.appliquer([{"id": g["id"], "action": "creer"}])
    t = next(t for t in monde.vault.index()[0].values() if t.titre == "Dans le dépôt")
    assert t.conteneur == "Projets/C1-Depot" and t.fm["session"] == "s-e1"
    assert "Il faut décider du format." in t.chemin.read_text("utf-8")


def test_titulaire_d_un_groupe_de_doublons_est_la_session_reprise(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    g = next(v for v in monde.agents_cc.vue() if v["nom"] == "atlas audit ⑂")
    assert g["session"] == "s-b2" and [h["session"] for h in g["historique"]] == ["s-b3", "s-b1"]
    monde.agents_cc.appliquer([{"id": g["id"], "action": "creer"}])
    t = next(t for t in monde.vault.index()[0].values() if t.titre == "atlas audit ⑂")
    assert t.fm["session"] == "s-b2"


def test_ignorer_persiste_et_une_session_plus_recente_reapparait(monde, jobs, depot_dir, config):
    peupler(jobs, depot_dir)
    g = par_nom(monde.agents_cc.vue())[("Silencieux", str(depot_dir))]
    monde.agents_cc.appliquer([{"id": g["id"], "action": "ignorer"}])
    assert not par_nom(monde.agents_cc.vue())[("Silencieux", str(depot_dir))]["decision"]
    relu = Moteur(config, monde.vault, {"faux": monde.registre["faux"]}).agents_cc  # état relu du disque
    assert not par_nom(relu.vue())[("Silencieux", str(depot_dir))]["decision"]
    job(jobs, "d2", "Silencieux", "s-d2", "2026-11-14T10:00:00.000Z", str(depot_dir), detail="reprise")
    relu.relever()
    assert par_nom(relu.vue())[("Silencieux", str(depot_dir))]["decision"] is True


def test_lot_un_refus_n_arrete_pas_le_lot(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    vue = par_nom(monde.agents_cc.vue())
    a, b = vue[("Audit du contrat fournisseur", "C:\\Divers")], vue[("Dans le dépôt", str(depot_dir / "src"))]
    res = monde.agents_cc.appliquer([{"id": a["id"], "action": "rattacher", "tache": "deja-pris"},
                                     {"id": b["id"], "action": "creer"}, {"id": "inconnu", "action": "creer"}])
    assert res["faits"] == [b["id"]] and len(res["echecs"]) == 2
    assert "déjà une conversation" in res["echecs"][0]["erreur"]


def test_aucune_ecriture_dans_le_dossier_de_claude_code(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    avant = {p: p.read_bytes() for p in jobs.rglob("*") if p.is_file()}
    for g in monde.agents_cc.vue():
        monde.agents_cc.appliquer([{"id": g["id"], "action": "ignorer"}])
    assert {p: p.read_bytes() for p in jobs.rglob("*") if p.is_file()} == avant


def test_action_inconnue_refusee(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    with pytest.raises(Invalide):
        monde.agents_cc._un(monde.agents_cc.vue()[0]["id"], "supprimer", "")


def test_page_decisions_porte_les_agents_apres_les_taches(monde, jobs, depot_dir):
    peupler(jobs, depot_dir)
    res = decisions.rassembler(monde)
    agents = [d for d in res["decisions"] if d["genre"] == "agent"]
    assert len(agents) == 5 and res["decisions"][-len(agents):] == agents
    assert agents[0]["agent"]["nom"] == "Dans le dépôt" and agents[0]["projet"] == "Agents Claude Code"
    assert decisions.compter(monde) == res["total"]


def test_releve_periodique_du_selon_le_rythme(monde):
    r = monde.agents_cc
    maintenant = dt.datetime(2026, 11, 16, 12, 0)
    assert r.due(maintenant) is True  # jamais relevé
    r.etat["derniere"] = "2026-11-16T11:30:00"
    assert r.due(maintenant) is False  # quotidien : pas encore
    r.etat["derniere"] = "2026-11-15T11:30:00"
    assert r.due(maintenant) is True
    r.cfg.rythme = "a-la-demande"
    assert r.due(maintenant) is False


def test_releve_debraye_sans_dossier(monde):
    monde.agents_cc.cfg.dossier = ""
    monde.agents_cc.groupes = None
    assert monde.agents_cc.vue() == [] and decisions.compter(monde) == 0


def test_routes_releve_et_lot(monde, config, jobs, depot_dir):
    peupler(jobs, depot_dir)
    with TestClient(api.creer_app(config, monde), base_url=BASE) as c:
        r = c.get("/api/agents-cc?relever=true").json()
        assert r["actif"] and len(r["groupes"]) == 6
        g = next(x for x in r["groupes"] if x["nom"] == "Silencieux")
        res = c.post("/api/decisions/agents", json={"choix": [{"id": g["id"], "action": "ignorer"}]}, headers=H).json()
        assert res["faits"] == [g["id"]]
        assert c.get("/api/etat").json()["decisions"] == decisions.compter(monde)
