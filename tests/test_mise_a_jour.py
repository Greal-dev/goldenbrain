"""Mise à jour en un geste : INV-MAJ-1 (avance rapide seule, refus clairs), INV-MAJ-2 (git sans shell).

Dépôts temporaires : un « distant » nu, un clone de l'utilisateur ; jamais le vrai dépôt.
"""

import subprocess

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from orchestrateur import api_maj, mise_a_jour
from orchestrateur.config import ConfigMiseAJour
from orchestrateur.moteur import Moteur
from orchestrateur.vault import ErreurOrch
from orchestrateur.version import Version

C = ConfigMiseAJour()
ID = ["-c", "user.name=Test", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false"]


def git(cwd, *args):
    r = subprocess.run(["git", *ID, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def commit(cwd, nom, texte):
    (cwd / nom).write_text(texte, encoding="utf-8")
    git(cwd, "add", nom)
    git(cwd, "commit", "-q", "-m", f"ajoute {nom}")


@pytest.fixture
def depots(tmp_path):
    """(distant nu, clone de l'utilisateur, second clone qui publie sur le distant)."""
    distant = tmp_path / "distant.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(distant))
    ailleurs = tmp_path / "ailleurs"
    git(tmp_path, "clone", "-q", str(distant), str(ailleurs))
    git(ailleurs, "checkout", "-q", "-b", "main")
    commit(ailleurs, "a.txt", "1\n")
    (ailleurs / ".gitignore").write_text("config.toml\netat/\n", encoding="utf-8")
    git(ailleurs, "add", ".gitignore")
    git(ailleurs, "commit", "-q", "-m", "ignore")
    git(ailleurs, "push", "-q", "origin", "main")
    local = tmp_path / "local"
    git(tmp_path, "clone", "-q", str(distant), str(local))
    return distant, local, ailleurs


def publier(ailleurs, nom="b.txt"):
    commit(ailleurs, nom, "2\n")
    git(ailleurs, "push", "-q", "origin", "main")


def test_a_jour_ne_change_rien(depots):
    _, local, _ = depots
    avant = git(local, "rev-parse", "HEAD")
    r = mise_a_jour.appliquer(local, C)
    assert r["appliquee"] is False and r["retard"] == 0 and git(local, "rev-parse", "HEAD") == avant


def test_en_retard_avance_en_avance_rapide(depots):
    _, local, ailleurs = depots
    publier(ailleurs)
    assert mise_a_jour.etat(local, C)["retard"] == 1
    r = mise_a_jour.appliquer(local, C)
    assert r["appliquee"] is True and r["retard"] == 0 and (local / "b.txt").is_file()
    assert git(local, "rev-parse", "HEAD") == git(ailleurs, "rev-parse", "HEAD")


def test_fichiers_d_alea_ume_ignores_jamais_touches(depots):
    _, local, ailleurs = depots
    git(local, "pull", "-q")  # .gitignore présent
    for rel, t in (("config.toml", "port = 1\n"), ("etat/tours.json", "{}")):
        (local / rel).parent.mkdir(exist_ok=True)
        (local / rel).write_text(t, encoding="utf-8")
    publier(ailleurs)
    mise_a_jour.appliquer(local, C)
    assert (local / "config.toml").read_text(encoding="utf-8") == "port = 1\n"
    assert (local / "etat/tours.json").read_text(encoding="utf-8") == "{}"


def test_modifications_locales_refusent_sans_rien_changer(depots):
    _, local, ailleurs = depots
    publier(ailleurs)
    (local / "a.txt").write_text("modifié\n", encoding="utf-8")
    avant = git(local, "rev-parse", "HEAD")
    with pytest.raises(mise_a_jour.Refus, match="modifications locales dans a.txt"):
        mise_a_jour.appliquer(local, C)
    assert git(local, "rev-parse", "HEAD") == avant
    assert (local / "a.txt").read_text(encoding="utf-8") == "modifié\n"


def test_historique_divergent_refuse_sans_fusion(depots):
    _, local, ailleurs = depots
    commit(local, "local.txt", "x\n")
    publier(ailleurs)
    avant = git(local, "rev-parse", "HEAD")
    with pytest.raises(mise_a_jour.Refus, match="a divergé"):
        mise_a_jour.appliquer(local, C)
    assert git(local, "rev-parse", "HEAD") == avant and not (local / "b.txt").exists()


def test_en_avance_seulement_rien_a_faire(depots):
    _, local, _ = depots
    commit(local, "local.txt", "x\n")
    r = mise_a_jour.appliquer(local, C)
    assert r["appliquee"] is False and r["avance"] == 1


def test_autre_branche_courante_refusee(depots):
    _, local, ailleurs = depots
    publier(ailleurs)
    git(local, "checkout", "-q", "-b", "travail")
    with pytest.raises(mise_a_jour.Refus, match="version « travail »"):
        mise_a_jour.appliquer(local, C)


def test_pas_un_depot_aucune_action(tmp_path):
    assert mise_a_jour.etat(tmp_path, C) == {"depot": False, "branche": "main"}
    with pytest.raises(mise_a_jour.Refus, match="pas un dossier de code"):
        mise_a_jour.appliquer(tmp_path, C)


@pytest.mark.parametrize("nom", ["--upload-pack=x", "a b", "", "-f"])
def test_nom_de_branche_suspect_refuse_avant_git(depots, nom):
    _, local, _ = depots
    with pytest.raises(ErreurOrch, match="invalide"):
        mise_a_jour.etat(local, ConfigMiseAJour(branche=nom))


def test_distant_injoignable_est_une_erreur_lisible(depots):
    _, local, _ = depots
    with pytest.raises(ErreurOrch):
        mise_a_jour.etat(local, ConfigMiseAJour(distant="inconnu"))


# --- API -----------------------------------------------------------------------------------------

@pytest.fixture
def api(config, vault, faux, depots):
    _, local, ailleurs = depots
    moteur = Moteur(config, vault, {"faux": faux})
    version = Version()
    app = FastAPI()

    @app.exception_handler(ErreurOrch)
    async def erreur(_: Request, e: ErreurOrch):
        return JSONResponse({"detail": str(e)}, status_code=e.code)

    app.include_router(api_maj.routes(config, moteur, version, local))
    with TestClient(app) as c:
        c.moteur, c.version, c.local, c.ailleurs = moteur, version, local, ailleurs
        yield c


def test_api_lit_le_retard_et_le_memorise_une_heure(api):
    assert api.get("/api/mise-a-jour").json()["retard"] == 0
    publier(api.ailleurs)
    memo = api.get("/api/mise-a-jour").json()
    assert memo["retard"] == 0 and memo["dernier_controle"]  # pas de nouveau contrôle avant une heure
    frais = api.get("/api/mise-a-jour?actualiser=true").json()
    assert frais["retard"] == 1 and frais["locale"] != frais["distante"]


def test_api_montre_quoi_de_neuf_quand_une_version_attend(api):
    (api.ailleurs / "c.txt").write_text("3\n", encoding="utf-8")
    git(api.ailleurs, "add", "c.txt")
    git(api.ailleurs, "commit", "-q", "-m", "Export\n\nNouveauté: export en PDF")
    git(api.ailleurs, "push", "-q", "origin", "main")
    e = api.get("/api/mise-a-jour?actualiser=true").json()
    assert e["nouveautes"] == [{"version": None, "entrees": ["Export en PDF"]}]  # INV-NOUV-1


def test_api_post_applique_puis_demande_le_redemarrage(api):
    publier(api.ailleurs)
    r = api.post("/api/mise-a-jour")
    assert r.status_code == 200 and r.json()["appliquee"] and r.json()["redemarre"]
    assert api.version.code_sortie == 3 and (api.local / "b.txt").is_file()


def test_api_post_deja_a_jour_ne_redemarre_pas(api):
    r = api.post("/api/mise-a-jour")
    assert r.json()["redemarre"] is False and api.version.code_sortie == 0


def test_api_post_409_si_un_tour_tourne(api):
    publier(api.ailleurs)
    api.moteur.occupe = lambda: True
    r = api.post("/api/mise-a-jour")
    assert r.status_code == 409 and "tour" in r.json()["detail"]
    assert not (api.local / "b.txt").exists() and api.version.code_sortie == 0


def test_api_post_409_lisible_si_modifications_locales(api):
    publier(api.ailleurs)
    (api.local / "a.txt").write_text("modifié\n", encoding="utf-8")
    r = api.post("/api/mise-a-jour")
    assert r.status_code == 409 and "modifications locales" in r.json()["detail"]
    assert api.version.code_sortie == 0


def test_api_hors_ligne_garde_la_derniere_valeur_et_signale(api):
    assert api.get("/api/mise-a-jour").json()["retard"] == 0
    git(api.local, "remote", "set-url", "origin", str(api.local / "inexistant"))
    r = api.get("/api/mise-a-jour?actualiser=true").json()
    assert r["erreur"] and r["retard"] == 0
