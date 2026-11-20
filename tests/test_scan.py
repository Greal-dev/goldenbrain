"""Scan du système : préconisations classées, toujours en attente du geste humain (INV-SCAN-1)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, decisions, scan
from orchestrateur.moteur import Moteur
from test_api import BASE, H

JOUR = dt.date(2026, 11, 17)
A, B = "Projets/C1-Alpha/taches/", "Projets/C2-Beta/taches/"


@pytest.fixture
def monde(config, vault, faux, racine):
    ecrire(racine, A + "conf-a.md", tache_md(extra="created: 2026-11-01\n", titre="Préparer la réunion des bénévoles"))
    ecrire(racine, B + "conf-b.md", tache_md(extra="created: 2026-11-10\n", titre="Préparer réunion des bénévoles"))
    ecrire(racine, A + "vieille.md", tache_md(extra="updated: 2026-01-05\n", titre="Relancer le fournisseur"))
    ecrire(racine, A + "vieille-datee.md", tache_md(extra="updated: 2026-01-05\necheance: 2027-01-01\n", titre="Attendre"))
    ecrire(racine, A + "vieille-close.md", tache_md("fait", "updated: 2026-01-05\n", "Close"))
    ecrire(racine, A + "permanente.md", tache_md(extra="updated: 2026-01-05\nnature: permanente\n", titre="Veille"))
    ecrire(racine, A + "pelle.md", tache_md(extra="created: 2026-11-01\n", titre="Chiffrer devis de la pelleteuse du jardin"))
    ecrire(racine, "_meta/taches/arrivee.md", tache_md(extra="created: 2026-11-15\n", titre="Chiffrer la pelleteuse du jardin"))
    return Moteur(config, vault, {"faux": faux})


def preconisations(m):
    return {(p["type"], p["tache"]): p for p in m.propositions.liste if p["de"] == scan.AUTEUR}


def test_scan_trouve_doublon_sommeil_et_sans_place(monde, vault):
    res = scan.scanner(monde, JOUR)
    ps = preconisations(monde)
    assert set(ps) == {("fermer", "conf-b"), ("fermer", "vieille"), ("deplacer", "arrivee")}
    assert res == {"nouvelles": 3, "ignorees": 0, "erreurs": []}
    assert ps[("fermer", "conf-b")]["valeur"] == "abandonne" and "conf-a" in ps[("fermer", "conf-b")]["motif"]
    assert (ps[("fermer", "conf-b")]["gain"], ps[("fermer", "conf-b")]["effort"]) == ("fort", "moyen")
    assert ps[("deplacer", "arrivee")]["valeur"] == vault.tache("pelle").conteneur
    assert all(p["etat"] == "en_attente" for p in ps.values())
    assert vault.tache("vieille").statut == "a-faire"  # rien n'est fermé sans geste


def test_scan_jamais_applique_meme_politique_accepter(monde, vault):
    monde.config.interface.propositions = "accepter"
    scan.scanner(monde, JOUR)
    assert all(p["etat"] == "en_attente" for p in preconisations(monde).values())
    assert vault.tache("conf-b").statut == "a-faire"


def test_scan_ne_repropose_ni_l_attente_ni_le_refus(monde):
    scan.scanner(monde, JOUR)
    monde.trancher(preconisations(monde)[("fermer", "vieille")]["n"], False)
    res = scan.scanner(monde, JOUR)
    assert res["nouvelles"] == 0 and res["ignorees"] == 3
    assert len(preconisations(monde)) == 3


def test_accepter_une_preconisation_ferme_la_tache(monde, vault):
    scan.scanner(monde, JOUR)
    monde.trancher(preconisations(monde)[("fermer", "vieille")]["n"], True)
    assert vault.tache("vieille").statut == "abandonne"


def test_decisions_groupe_et_classe_par_gain_puis_effort(monde):
    scan.scanner(monde, JOUR)
    lignes = [d for d in decisions.rassembler(monde)["decisions"] if d["genre"] == "scan"]
    assert [d["tache"] for d in lignes][0] == "conf-b"  # gain fort d'abord
    assert {d["projet"] for d in lignes} == {"Scan du système"}
    assert lignes[0]["motif"] == "gain fort · effort moyen"
    assert not any(d["genre"] == "revue" for d in decisions.rassembler(monde)["decisions"])


def test_route_scan(monde, config):
    with TestClient(api.creer_app(config, monde), base_url=BASE) as c:
        r = c.post("/api/decisions/scan", headers=H)
        assert r.status_code == 200 and r.json()["nouvelles"] >= 2
        assert any(d["genre"] == "scan" for d in c.get("/api/decisions").json()["decisions"])
