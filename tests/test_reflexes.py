"""Réflexes de l'agent (INV-REFLEXES-1) et traçage des documents d'une tâche (INV-TRACE-1) : bloc entre marqueurs,
reste du fichier intact, état (absent, à jour, ancien, retouché), rien d'écrit sans accord, routes du poste."""

import pytest
from fastapi.testclient import TestClient

from conftest import PORT
from orchestrateur import api, cli, reflexes
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}
AUTRUI = "# Mes consignes\n\nNe jamais toucher à ceci.\n"


@pytest.fixture
def maison(tmp_path, monkeypatch):
    m = tmp_path / "maison"
    (m / ".claude").mkdir(parents=True)
    monkeypatch.setenv("ORCH_ACCUEIL_HOME", str(m))
    return m


def test_installer_puis_retirer_rend_le_fichier_a_l_identique():
    pose = reflexes.transformer(AUTRUI, "installer", "fr")
    assert pose.startswith(AUTRUI) and "<!-- goldenbrain:reflexes fin -->" in pose
    assert reflexes.etat_texte(pose, "fr") == ("a_jour", reflexes.VERSION)
    assert reflexes.transformer(pose, "installer", "fr") == pose  # idempotent
    assert reflexes.transformer(pose, "retirer") == AUTRUI


def test_bloc_au_milieu_retire_sans_toucher_au_reste_et_fins_de_ligne_windows():
    texte = "A\r\n\r\n" + reflexes.bloc("en", "\r\n") + "\r\n\r\nB\r\n"
    assert reflexes.transformer(texte, "retirer") == "A\r\n\r\nB\r\n"
    assert "\n" not in reflexes.transformer(texte, "installer", "en").replace("\r\n", "")


def test_etats_ancien_et_retouche_et_marqueur_cite_dans_la_prose():
    pose = reflexes.transformer(AUTRUI, "installer", "fr")
    ancien = pose.replace(f"debut v{reflexes.VERSION} -->", "debut v0 -->")
    assert reflexes.etat_texte(ancien, "fr")[0] == "ancien"
    assert reflexes.etat_texte(pose.replace("L'utilisateur décide", "Je décide"), "fr")[0] == "retouche"
    cite = "On écrit `<!-- goldenbrain:reflexes debut v1 -->` dans la prose.\n"
    assert reflexes.etat_texte(cite, "fr")[0] == "absent"  # un marqueur cité n'est pas une borne
    assert reflexes.transformer(reflexes.transformer(ancien, "installer", "fr"), "retirer") == AUTRUI


def test_bloc_traduit_dans_les_quatre_langues():
    for code, titre in (("fr", "réflexes"), ("en", "reflexes"), ("de", "Arbeitsreflexe"), ("es", "reflejos")):
        assert titre in reflexes.bloc(code) and "orch tracer" in reflexes.bloc(code) and "`integration:`" in reflexes.bloc(code)


def test_cli_n_ecrit_rien_sans_accord(maison, capsys):
    chemin = maison / ".claude" / "CLAUDE.md"
    chemin.write_text(AUTRUI, encoding="utf-8")
    assert cli.main(["reflexes", "installer", "--harnais", "claude"]) == 0
    sortie = capsys.readouterr().out
    assert "--accord" in sortie and "+<!-- goldenbrain:reflexes debut" in sortie
    assert chemin.read_text(encoding="utf-8") == AUTRUI
    assert cli.main(["reflexes", "installer", "--harnais", "claude", "--accord"]) == 0
    assert reflexes.etat_texte(chemin.read_text(encoding="utf-8"), "fr")[0] == "a_jour"
    assert cli.main(["reflexes"]) == 0 and "claude (Claude Code) : à jour" in capsys.readouterr().out
    assert cli.main(["reflexes", "retirer", "--harnais", "claude", "--accord"]) == 0
    assert chemin.read_text(encoding="utf-8") == AUTRUI


def test_cli_consignes_d_un_projet(tmp_path, maison):
    assert cli.main(["reflexes", "installer", "--harnais", "codex", "--dossier", str(tmp_path), "--accord"]) == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").startswith("<!-- goldenbrain:reflexes debut")


def test_lien_symbolique_preserve(maison, tmp_path):
    vrai = tmp_path / "dotfiles" / "CLAUDE.md"
    vrai.parent.mkdir()
    vrai.write_text(AUTRUI, encoding="utf-8")
    lien = maison / ".claude" / "CLAUDE.md"
    lien.symlink_to(vrai)
    assert reflexes.appliquer(lien, "installer", "fr")
    assert lien.is_symlink() and "goldenbrain:reflexes" in vrai.read_text(encoding="utf-8")


@pytest.fixture
def client(config, vault, faux, maison):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_routes_proposent_appliquent_et_reportent(client, maison):
    r = client.get("/api/accueil/reflexes").json()
    claude = next(a for a in r["assistants"] if a["id"] == "claude")
    assert r["propose"] and claude["present"] and claude["etat"] == "absent" and "+<!-- goldenbrain" in claude["apercu"]
    assert not next(a for a in r["assistants"] if a["id"] == "codex")["propose"]  # absent du poste
    assert client.post("/api/accueil/reflexes/appliquer", json={"harnais": "claude"}).status_code == 403  # sans en-tête
    r = client.post("/api/accueil/reflexes/appliquer", json={"harnais": "claude"}, headers=H).json()
    assert next(a for a in r["assistants"] if a["id"] == "claude")["etat"] == "a_jour" and not r["propose"]
    client.post("/api/accueil/reflexes/appliquer", json={"harnais": "claude", "action": "retirer"}, headers=H)
    r = client.post("/api/accueil/reflexes/plus-tard", json={"harnais": "claude"}, headers=H).json()
    assert not r["propose"] and not (maison / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert client.post("/api/accueil/reflexes/appliquer", json={"harnais": "x"}, headers=H).status_code == 400


def test_tracer_ecrit_une_ligne_avec_liens(client, racine, tmp_path):
    note = racine / "Projets" / "C1-Alpha" / "compte-rendu.md"
    note.write_text("# CR\n", encoding="utf-8")
    corps = {"texte": "Résultat : compte rendu rédigé", "documents": [str(note), str(tmp_path / "hors.pdf")]}
    assert client.post("/api/taches/mere/traces", json=corps, headers=H).status_code == 200
    texte = (racine / "Projets" / "C1-Alpha" / "taches" / "mere.md").read_text(encoding="utf-8")
    assert texte.startswith("---\ntype: tache\nstatut: a-faire\n")  # frontmatter intact (INV-VAULT-1)
    assert "## Traces\n- " in texte and "[[Projets/C1-Alpha/compte-rendu]]" in texte and "hors.pdf`" in texte


def test_cli_tracer_envoie_des_chemins_absolus(monkeypatch, capsys):
    vu = []
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: vu.append((m, c, corps)) or {"id": "t1"})
    assert cli.main(["tracer", "t1", "fait", "--document", "rel.md"]) == 0
    assert vu[0][1] == "/taches/t1/traces" and vu[0][2]["documents"][0].replace("\\", "/").endswith("/rel.md") and vu[0][2]["documents"][0] != "rel.md"
