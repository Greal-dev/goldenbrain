"""Lecteur de fichiers : registre des formats, validation des chemins, isolement du HTML, refus distant et d'agent."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, lecteur, resultat
from orchestrateur.config import Config
from orchestrateur.config_distant import ConfigDistant, ConfigExecuteurs
from orchestrateur.config_lecteur import ConfigLecteur
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from conftest import ecrire, tache_md

H = {"X-Orchestrateur": "1"}
LOCAL = "http://127.0.0.1:8399"


@pytest.fixture
def moteur(config, vault, faux, racine):
    ecrire(racine, "Projets/C1-Alpha/taches/chantier.md", tache_md(titre="Chantier"))
    ecrire(racine, "Projets/C1-Alpha/notes/rapport.md", "---\ntype: note\n---\n\n# Rapport\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    ecrire(racine, "Projets/C1-Alpha/notes/page.html", "<h1>Bonjour</h1><script>document.title='x'</script>")
    ecrire(racine, "Projets/C1-Alpha/notes/budget.docx", "PK\x03\x04binaire")
    ecrire(racine, "Projets/C1-Alpha/notes/script.sh", "#!/bin/sh\necho hop\n")
    lecteur.vider_cache()
    return Moteur(config, vault, {"faux": faux})


@pytest.fixture
def client(config, moteur):
    with TestClient(api.creer_app(config, moteur), base_url=LOCAL) as c:
        yield c


@pytest.fixture
def ouvertures(monkeypatch):
    vus = []
    monkeypatch.setattr(resultat, "ouvrir_systeme", lambda cible, url=False: vus.append(cible))
    monkeypatch.setattr(lecteur, "_application", lambda p: "Éditeur")
    return vus


def test_registre_formats(racine):
    r = ConfigLecteur()
    assert lecteur.mode_de(r, "md") == ("lecteur", "md")
    assert lecteur.mode_de(r, "html") == ("lecteur", "html")
    assert lecteur.mode_de(r, "png") == ("lecteur", "image")
    assert lecteur.mode_de(r, "docx")[0] == "application"
    assert lecteur.mode_de(r, "zip")[0] == "application"
    assert lecteur.mode_de(r, "")[0] == "lecteur"
    assert lecteur.mode_de(ConfigLecteur(application=["md"]), "md")[0] == "application"
    assert lecteur.mode_de(ConfigLecteur(lecteur=["docx"]), "docx") == ("lecteur", "texte")
    with pytest.raises(ValueError):
        ConfigLecteur(lecteur=["md"], application=["md"])


def test_md_html_docx_modes(client):
    base = "/api/lecteur/info"
    assert client.get(base, params={"chemin": "Projets/C1-Alpha/notes/rapport.md"}).json()["genre"] == "md"
    assert client.get(base, params={"chemin": "Projets/C1-Alpha/notes/page.html"}).json()["genre"] == "html"
    docx = client.get(base, params={"chemin": "Projets/C1-Alpha/notes/budget.docx"}).json()
    assert docx["mode"] == "application" and docx["application"] is True


def test_traversee_refusee(client):
    r = client.get("/api/lecteur/info", params={"chemin": "../../etc/passwd"})
    assert r.status_code == 400


def test_hors_racines_refuse_et_jamais_servi(client, tmp_path):
    dehors = tmp_path / "dehors.txt"
    dehors.write_text("secret", encoding="utf-8")
    for route in ("info", "page", "brut"):
        r = client.get(f"/api/lecteur/{route}", params={"chemin": str(dehors)})
        assert r.status_code == 403, route
        assert "secret" not in r.text


@pytest.mark.skipif(sys.platform == "win32", reason="lien symbolique : droits Windows")
def test_lien_symbolique_vers_l_exterieur_refuse(client, racine, tmp_path):
    dehors = tmp_path / "dehors.txt"
    dehors.write_text("secret", encoding="utf-8")
    os.symlink(dehors, racine / "Projets/C1-Alpha/notes/lien.txt")
    assert client.get("/api/lecteur/page", params={"chemin": "Projets/C1-Alpha/notes/lien.txt"}).status_code == 403


def test_dossier_ajoute_dans_reglages_devient_lisible(client, config, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "a.txt").write_text("bonjour", encoding="utf-8")
    assert client.get("/api/lecteur/page", params={"chemin": str(d / "a.txt")}).status_code == 403
    config.lecteur = ConfigLecteur(dossiers=[str(d)])
    lecteur.vider_cache()
    assert client.get("/api/lecteur/page", params={"chemin": str(d / "a.txt")}).json()["texte"] == "bonjour"


def test_livrable_declare_hors_racines_est_lisible(client, tmp_path):
    f = tmp_path / "livre.txt"
    f.write_text("fait", encoding="utf-8")
    assert client.get("/api/lecteur/page", params={"chemin": str(f)}).status_code == 403
    client.post("/api/taches/chantier/livrables", json={"cible": str(f), "type": "fichier"}, headers=H)
    lecteur.vider_cache()
    assert client.get("/api/lecteur/page", params={"chemin": str(f)}).json()["texte"] == "fait"


def test_page_partielle_et_suite(client, racine):
    lignes = "".join(f"ligne {i}\n" for i in range(60000))
    ecrire(racine, "Projets/C1-Alpha/notes/gros.log", lignes)
    p = "Projets/C1-Alpha/notes/gros.log"
    a = client.get("/api/lecteur/page", params={"chemin": p}).json()
    assert a["suite"] and a["texte"].endswith("\n") and a["fin"] < a["taille"]
    b = client.get("/api/lecteur/page", params={"chemin": p, "debut": a["fin"]}).json()
    assert b["texte"].startswith("ligne ") and b["debut"] == a["fin"]
    assert (a["texte"] + b["texte"]).startswith(lignes[:len(a["texte"])])


def test_html_isole_sans_script_ni_origine(client):
    r = client.get("/api/lecteur/brut", params={"chemin": "Projets/C1-Alpha/notes/page.html"})
    csp = r.headers["content-security-policy"]
    assert r.status_code == 200 and "sandbox" in csp and "allow-scripts" not in csp and "allow-same-origin" not in csp
    assert "default-src 'none'" in csp and "script-src" not in csp and "img-src  data:" in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["content-type"].startswith("text/html")
    externe = client.get("/api/lecteur/brut", params={"chemin": "Projets/C1-Alpha/notes/page.html", "externe": True})
    assert "img-src * data:" in externe.headers["content-security-policy"] and "script" not in externe.headers["content-security-policy"]


def test_brut_refuse_un_md(client):
    assert client.get("/api/lecteur/brut", params={"chemin": "Projets/C1-Alpha/notes/rapport.md"}).status_code == 400


def test_ouvrir_docx_au_poste(client, ouvertures):
    r = client.post("/api/lecteur/ouvrir", json={"chemin": "Projets/C1-Alpha/notes/budget.docx"}, headers=H)
    assert r.status_code == 200 and "Éditeur" in r.json()["message"]
    assert ouvertures[-1].endswith("budget.docx")


def test_un_script_ne_se_lance_jamais(client, ouvertures):
    r = client.post("/api/lecteur/ouvrir", json={"chemin": "Projets/C1-Alpha/notes/script.sh"}, headers=H)
    assert r.status_code == 200 and not ouvertures[-1].endswith("script.sh")
    assert ouvertures[-1].endswith("notes")


def test_agent_ne_peut_pas_ouvrir_une_application(client, ouvertures):
    for tete in ({"X-Orch-Tache": "chantier"}, {"X-Orch-Jeton": "x"}):
        r = client.post("/api/lecteur/ouvrir", json={"chemin": "Projets/C1-Alpha/notes/budget.docx"}, headers={**H, **tete})
        assert r.status_code == 403
        r = client.post("/api/lecteur/dossier", json={"chemin": "Projets/C1-Alpha/notes/budget.docx"}, headers={**H, **tete})
        assert r.status_code == 403
    assert not ouvertures


def test_reglages_ecrits_et_valides(client, config, tmp_path):
    config.chemin = tmp_path / "config.toml"
    r = client.put("/api/lecteur/reglages", json={"dossiers": ["C:\\Docs"], "lecteur": [], "application": ["md"]}, headers=H)
    assert r.status_code == 200 and r.json()["registre"]["md"] == "application"
    import tomllib
    assert tomllib.loads(config.chemin.read_text(encoding="utf-8"))["lecteur"]["dossiers"] == ["C:\\Docs"]
    assert client.put("/api/lecteur/reglages", json={"lecteur": ["x y"]}, headers=H).status_code == 400


# --- appareil distant ------------------------------------------------------------------------------
def test_distant_lit_le_vault_jamais_l_application(config, vault, faux, racine, tmp_path):
    from test_appareils import ECOUTE, appairer
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    config.distant = ConfigDistant(appareils=True)
    ecrire(racine, "Projets/C1-Alpha/taches/chantier.md", tache_md(titre="Chantier"))
    ecrire(racine, "Projets/C1-Alpha/notes/n.md", "# N\n")
    dehors = tmp_path / "hors.txt"
    dehors.write_text("x", encoding="utf-8")
    lecteur.vider_cache()
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    tel = appairer(app)
    assert tel.get("/api/lecteur/page", params={"chemin": "Projets/C1-Alpha/notes/n.md"}).json()["texte"].startswith("# N")
    assert tel.get("/api/lecteur/page", params={"chemin": str(dehors)}).status_code == 403
    for chemin in ("ouvrir", "dossier"):
        assert tel.post(f"/api/lecteur/{chemin}", json={"chemin": "Projets/C1-Alpha/notes/n.md"}, headers=H).status_code == 403
    assert tel.put("/api/lecteur/reglages", json={"dossiers": [str(tmp_path)]}, headers=H).status_code == 403
