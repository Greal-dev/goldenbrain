"""Compagnon mobile (INV-COMPAGNON-1, INV-PWA-2) : instantané en liste blanche, ETag et 304,
refus sans appareil appairé, indicateur `hors_ligne` posé par la configuration."""

import json

from fastapi.testclient import TestClient

from conftest import PORT, ecrire, tache_md
from test_appareils import ECOUTE, DISTANT, H, appairer, poste  # noqa: F401  (fixture)
from orchestrateur import api, compagnon
from orchestrateur.config import ConfigDistant, ConfigExecuteurs
from orchestrateur.moteur import Moteur

URL = "/api/compagnon/instantane"
VAULT_RETOUR = "retour-humain"
SECRET = "SECRET-CORPS-DE-FICHE"


def _monde(racine):
    ecrire(racine, "Projets/C1-Alpha/taches/question.md",
           tache_md(statut=VAULT_RETOUR, extra=f"commentaire: Faut-il publier ?\n", titre="À trancher")
           .replace("Corps.", f"{SECRET} chemin /srv/prive/x"))


def _local(config, vault, faux, **distant):
    config.distant = ConfigDistant(**distant)
    return api.creer_app(config, Moteur(config, vault, {"faux": faux}))


def test_instantane_liste_blanche_sans_corps_ni_chemin(config, vault, faux, racine):
    _monde(racine)
    with TestClient(_local(config, vault, faux), base_url=f"http://127.0.0.1:{PORT}") as c:
        r = c.get(URL)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    j = r.json()
    assert {"arbre", "decisions", "travaux", "empreinte", "genere", "ttl_s", "hors_ligne", "tronque"} <= set(j)
    texte = json.dumps(j, ensure_ascii=False)
    assert SECRET not in texte and "/srv/prive" not in texte and str(racine) not in texte
    assert any(n["titre"] == "Mère" and n["parent"] for n in j["arbre"])
    assert all(set(n) <= {"parent", *compagnon.CHAMPS_NOEUD} for n in j["arbre"])
    d = [x for x in j["decisions"] if x["titre"] == "À trancher"]
    assert d and d[0]["question"] == "Faut-il publier ?" and d[0]["genre"] == "reponse"
    assert j["hors_ligne"] is False and j["ttl_s"] == 7 * 86400


def test_etag_304_puis_changement(config, vault, faux, racine):
    with TestClient(_local(config, vault, faux), base_url=f"http://127.0.0.1:{PORT}") as c:
        etag = c.get(URL).headers["etag"]
        r = c.get(URL, headers={"If-None-Match": etag})
        assert r.status_code == 304 and r.content == b"" and r.headers["etag"] == etag
        _monde(racine)
        vault._index = None  # l'index en mémoire ne doit pas masquer la tâche neuve
        r = c.get(URL, headers={"If-None-Match": etag})
        assert r.status_code == 200 and r.headers["etag"] != etag


def test_arbre_tronque_et_decisions_bornees(config, vault, faux, monkeypatch):
    monkeypatch.setattr(compagnon, "NOEUDS_MAX", 3)
    with TestClient(_local(config, vault, faux), base_url=f"http://127.0.0.1:{PORT}") as c:
        j = c.get(URL).json()
    assert len(j["arbre"]) == 3 and j["tronque"] is True


def test_hors_ligne_suit_la_configuration(config, vault, faux):
    with TestClient(_local(config, vault, faux, hors_ligne=True), base_url=f"http://127.0.0.1:{PORT}") as c:
        assert c.get(URL).json()["hors_ligne"] is True


def test_appareil_non_appaire_refuse_appaire_admis_revoque_refuse(poste):
    with TestClient(poste, base_url=DISTANT) as anonyme:
        assert anonyme.get(URL).status_code == 401
    tel = appairer(poste)
    r = tel.get(URL)
    assert r.status_code == 200 and r.json()["arbre"]
    with TestClient(poste, base_url=f"http://127.0.0.1:{PORT}") as local:
        ident = local.get("/api/appareils").json()["appareils"][0]["id"]
        assert local.delete(f"/api/appareils/{ident}", headers=H).status_code == 200
    assert tel.get(URL).status_code == 401
