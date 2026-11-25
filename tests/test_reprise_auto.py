"""Reprise automatique (INV-REPRISE-1) et enregistrement d'étape (INV-REPRISE-2) : tests de régression."""

import subprocess
from types import SimpleNamespace

import pytest

from orchestrateur import depot, echecs, etape, reprise_auto


def faux_moteur(reprises=0, ouverte=True):
    vault = SimpleNamespace(tache=lambda i: i, ouverte=lambda t: ouverte)
    return SimpleNamespace(vault=vault, interrompus={"t": {"reprises": reprises}}, actifs={}, files={}, attente={},
                           etat_de=lambda i: "interrompu", tours={})


@pytest.fixture(autouse=True)
def sans_note(monkeypatch):
    monkeypatch.setattr(etape, "noter", lambda *a, **k: None)


def test_tour_arrete_par_la_regulation_memoire_repart_seul_sans_changer_le_statut():
    r = reprise_auto.RepriseAuto(faux_moteur())
    assert r.marquer("t", SimpleNamespace(arret="ram", depuis=None)) is True
    assert "t" in r.pendantes


def test_arret_humain_ne_reprend_jamais_seul():
    r = reprise_auto.RepriseAuto(faux_moteur())
    assert r.marquer("t", SimpleNamespace(arret="humain", depuis=None)) is False
    assert not r.pendantes


def test_apres_trois_reprises_le_tour_n_est_plus_repris_d_office():
    r = reprise_auto.RepriseAuto(faux_moteur(reprises=reprise_auto.MAX_REPRISES))
    assert r.permis("t") is False
    assert r.marquer("t", SimpleNamespace(arret="ram", depuis=None)) is False


def test_tache_terminee_n_est_jamais_reprise():
    assert reprise_auto.RepriseAuto(faux_moteur(ouverte=False)).permis("t") is False


@pytest.mark.parametrize("motif", ["No response from API", "API Error: 503 Service Unavailable", "overloaded_error"])
def test_erreur_no_response_from_api_est_passagere(motif):
    assert echecs.est_passagere(motif)


def test_quota_epuise_n_est_pas_une_erreur_passagere():
    assert not echecs.est_passagere("You've hit your usage limit, quota exceeded")


def depot_git(tmp_path):
    def git(*a, d=tmp_path / "depot"):
        subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                       capture_output=True, encoding="utf-8")
    (tmp_path / "depot").mkdir()
    git("init", "-q", "-b", "mvp")
    git("commit", "-q", "--allow-empty", "-m", "base")
    arbre = tmp_path / "arbre"
    git("worktree", "add", "-q", "-b", "gb/x", str(arbre))
    return tmp_path / "depot", arbre


def test_etape_retrouve_l_arbre_modifie_et_sa_branche(tmp_path, monkeypatch):
    principal, arbre = depot_git(tmp_path)
    monkeypatch.setattr(depot, "dossier_de_travail", lambda v, i: (str(principal), "test"))
    (arbre / "f.txt").write_text("x", encoding="utf-8")
    info = etape.retrouver(SimpleNamespace(vault=None), "t")
    assert info["branche"] == "gb/x" and info["sale"] is True and info["arbre"] == str(arbre)


def test_etape_sans_arbre_actif_ne_note_rien(tmp_path, monkeypatch):
    principal = tmp_path / "d"
    principal.mkdir()
    subprocess.run(["git", "-C", str(principal), "init", "-q"], check=True, capture_output=True)
    monkeypatch.setattr(depot, "dossier_de_travail", lambda v, i: (str(principal), "test"))
    assert etape.retrouver(SimpleNamespace(vault=None), "t") is None
