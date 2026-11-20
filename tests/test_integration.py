"""INV-INTEG-1 : pastille « intégration en retard » — branches citées, lecture git (dépôt temporaire), cache, route."""

import os
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, integration
from orchestrateur.moteur import Moteur
from orchestrateur.integration import ConfigIntegration, Suivi, branches_citees

H = {"X-Orchestrateur": "1"}
BASE = "http://127.0.0.1:8399"
MAINTENANT = 1_800_000_000.0


def git(depot, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"@{int(date)} +0000"
    subprocess.run(["git", "-C", str(depot), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def depot(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, "init", "-q", "-b", "gb/integration")
    git(d, "commit", "-q", "--allow-empty", "-m", "base", date=MAINTENANT - 100 * 3600)
    return d


def branche(depot, nom, heures):
    git(depot, "checkout", "-q", "-b", nom)
    git(depot, "commit", "-q", "--allow-empty", "-m", nom, date=MAINTENANT - heures * 3600)
    git(depot, "checkout", "-q", "gb/integration")


def tache(statut="fait", resultat="branche gb/x, commit abc"):
    return SimpleNamespace(fiche={"fait": "", "resultat": resultat}, statut=statut)


def noeud(ident, statut="fait", enfants=()):
    return {"id": ident, "type": "tache", "statut": statut, "enfants": list(enfants)}


def suivi(depot, **cfg):
    return Suivi(ConfigIntegration(**cfg), depot, horloge=lambda: MAINTENANT)


def test_branches_citees_sans_doublon_ni_ponctuation_ni_integration():
    f = {"fait": "branche gb/a-b (voir gb/integration).", "resultat": "gb/a-b ; gb/c/d, puis gb/c/d."}
    assert branches_citees(f, "gb/integration") == ["gb/a-b", "gb/c/d"]
    assert branches_citees({"resultat": "origin/gb/x ou sgb/y"}) == []


def test_config_refuse_branche_et_seuil_invalides():
    for mauvais in ({"branche": "-D x"}, {"branche": "a..b"}, {"retard_h": 0}, {"cache_s": -1}):
        with pytest.raises(ValueError):
            ConfigIntegration(**mauvais)


def test_pastille_si_non_contenue_depuis_plus_de_n_heures(depot):
    branche(depot, "gb/x", heures=5)
    s = suivi(depot)
    taches = {"t": tache()}
    n = [noeud("t")]
    s.annoter(n, taches)
    assert n[0]["integration_retard"] == {"branche": "gb/x", "heures": 5}


def test_pas_de_pastille_sous_le_seuil_ni_si_contenue_ni_si_ouverte_ni_si_inconnue(depot):
    branche(depot, "gb/x", heures=1)
    branche(depot, "gb/fusionnee", heures=9)
    git(depot, "merge", "-q", "--no-ff", "-m", "m", "gb/fusionnee")
    s = suivi(depot)
    taches = {"recent": tache(resultat="gb/x"), "fusion": tache(resultat="gb/fusionnee"),
              "ouverte": tache("en-cours", "gb/x"), "inconnue": tache(resultat="gb/n-existe-pas")}
    n = [noeud(k, taches[k].statut) for k in taches]
    s.annoter(n, taches)
    assert not any("integration_retard" in x for x in n)


def test_pastille_dans_les_enfants_et_la_plus_ancienne_branche(depot):
    branche(depot, "gb/x", heures=3)
    branche(depot, "gb/y", heures=7)
    s = suivi(depot)
    n = [noeud("mere", "en-cours", [noeud("fille")])]
    s.annoter(n, {"mere": tache("en-cours"), "fille": tache(resultat="gb/x puis gb/y")})
    assert n[0]["enfants"][0]["integration_retard"] == {"branche": "gb/y", "heures": 7}


def test_seuil_reglable_sans_relire_git_et_fusion_apres_cache(depot):
    branche(depot, "gb/x", heures=5)
    t = [1.0]
    s = Suivi(ConfigIntegration(cache_s=10), depot, horloge=lambda: MAINTENANT + t[0])
    taches, n = {"t": tache()}, [noeud("t")]
    s.annoter(n, taches)
    assert "integration_retard" in n[0]
    s.config = ConfigIntegration(retard_h=8, cache_s=10)  # seuil relevé : pastille levée aussitôt
    n = [noeud("t")]
    s.annoter(n, taches)
    assert "integration_retard" not in n[0]
    s.config = ConfigIntegration(cache_s=10)
    git(depot, "merge", "-q", "--ff-only", "gb/x")
    n = [noeud("t")]
    s.annoter(n, taches)
    assert "integration_retard" in n[0]  # cache encore valide
    t[0] = 30.0
    s.annoter([noeud("t")], taches)
    s.attendre()
    n = [noeud("t")]
    s.annoter(n, taches)
    assert "integration_retard" not in n[0]


def test_annoter_ne_bloque_pas_si_git_est_lent(depot, monkeypatch):
    branche(depot, "gb/x", heures=5)
    monkeypatch.setattr(integration, "lire", lambda *a: __import__("time").sleep(5))
    monkeypatch.setattr(integration, "ATTENTE_PREMIERE_S", 0.1)
    import time
    debut = time.monotonic()
    n = [noeud("t")]
    suivi(depot).annoter(n, {"t": tache()})
    assert time.monotonic() - debut < 2 and "integration_retard" not in n[0]


def test_depot_absent_ou_integration_absente_aucune_pastille(tmp_path, depot):
    branche(depot, "gb/x", heures=5)
    n = [noeud("t")]
    suivi(tmp_path / "nulle-part").annoter(n, {"t": tache()})
    suivi(depot, branche="gb/inexistante").annoter(n, {"t": tache()})
    assert "integration_retard" not in n[0]


def test_route_lire_regler_et_refuser(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url=BASE) as client:
        _route(client)


def _route(client):
    assert client.get("/api/integration").json() == {"branche": "gb/integration", "retard_h": 2.0, "cache_s": 60.0}
    r = client.put("/api/integration", json={"retard_h": 4}, headers=H)
    assert r.status_code == 200 and r.json()["retard_h"] == 4
    assert client.put("/api/integration", json={"retard_h": -1}, headers=H).status_code == 400
    assert client.get("/api/integration").json()["retard_h"] == 4
