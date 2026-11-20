"""INV-RESULTAT-1 : « Voir le résultat » relève fichiers, site local et dossier, et les ouvre sur le poste."""

import json

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, resultat
from orchestrateur.api_appareils import POSTE_SEUL_RE
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, NonTrouve
from conftest import ecrire, tache_md

H = {"X-Orchestrateur": "1"}


@pytest.fixture
def ouvertures(monkeypatch):
    vus = []
    monkeypatch.setattr(resultat, "ouvrir_systeme", lambda cible, url=False: vus.append((cible, url)))
    return vus


@pytest.fixture
def depot_code(racine, tmp_path):
    d = tmp_path / "projet"
    d.mkdir()
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           f"---\ntype: contexte\ncasquette: C1-Pro\nparent: \"[[Operation-X]]\"\nnom: Alpha\ndepot: \"{d}\"\n---\n")
    return d


def fiche(racine, resultat_txt="", essai="", extra=""):
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md", tache_md(extra=extra, titre="Mère") +
           f"\n<!-- orchestrateur:debut -->\n## Fiche\n- **Résultat** : {resultat_txt}\n- **Essai** : {essai}\n"
           "<!-- orchestrateur:fin -->\n")


def moteur(config, vault, faux, transcript=""):
    if transcript:
        faux.chemin_transcript = lambda self, session: transcript
    return Moteur(config, vault, {"faux": faux})


def cibles(m):
    return [e["cible"] for e in resultat.chercher(m, "mere")["elements"]]


def test_rien_a_montrer_message_clair(config, vault, faux):
    r = resultat.chercher(moteur(config, vault, faux), "mere")
    assert r["elements"] == [] and "Rien à montrer" in r["message"]


def test_dossier_de_travail_et_index_html(config, vault, faux, depot_code):
    (depot_code / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    r = resultat.chercher(moteur(config, vault, faux), "mere")
    assert [(e["genre"], e["origine"]) for e in r["elements"]] == [("site", "dossier"), ("dossier", "dossier")]


def test_fiche_fichiers_cites_et_adresse_locale(racine, config, vault, faux, depot_code):
    (depot_code / "rapport.pdf").write_text("x", encoding="utf-8")
    (depot_code / "docs").mkdir()
    (depot_code / "docs" / "note.md").write_text("x", encoding="utf-8")
    fiche(racine, f"`{depot_code}/rapport.pdf` et docs/note.md ; absent.txt",
          "ouvrir http://localhost:5173/ puis https://example.com/x")
    c = cibles(moteur(config, vault, faux))
    assert c[0] == "http://localhost:5173/"  # adresse du poste, jamais une adresse externe
    assert str((depot_code / "rapport.pdf").resolve()) in c and str((depot_code / "docs" / "note.md").resolve()) in c
    assert not any("example.com" in x or "absent" in x for x in c)


def test_chemin_hors_racines_ignore(racine, config, vault, faux, depot_code, monkeypatch):
    monkeypatch.setattr(resultat, "_racines", lambda v, d: [depot_code.resolve()])
    fiche(racine, "/etc/passwd")
    assert "/etc/passwd" not in cibles(moteur(config, vault, faux))


def test_fichiers_du_dernier_tour_seulement(racine, config, vault, faux, depot_code, tmp_path):
    ancien, neuf = depot_code / "ancien.txt", depot_code / "neuf.html"
    ancien.write_text("a", encoding="utf-8")
    neuf.write_text("n", encoding="utf-8")
    journal = tmp_path / "s.jsonl"

    def ecriture(f):
        return {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": str(f)}}]}}

    def parole(t):
        return {"type": "user", "message": {"content": [{"type": "text", "text": t}]}}

    lignes = [parole("un"), ecriture(ancien), parole("deux"), ecriture(neuf)]
    journal.write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    fiche(racine, extra="session: s-1\nharnais: faux\n")
    c = cibles(moteur(config, vault, faux, str(journal)))
    assert str(neuf.resolve()) in c and str(ancien.resolve()) not in c


def test_ouvrir_site_et_dossier(racine, config, vault, faux, depot_code, ouvertures):
    fiche(racine, "", "http://127.0.0.1:3000")
    m = moteur(config, vault, faux)
    r = resultat.ouvrir(m, "mere", "http://127.0.0.1:3000")
    assert ouvertures == [("http://127.0.0.1:3000", True)] and "Ouvert" in r["message"]
    resultat.ouvrir(m, "mere", str(depot_code.resolve()))
    assert ouvertures[-1] == (str(depot_code.resolve()), False)


def test_fichier_executable_jamais_lance_son_dossier_s_ouvre(racine, config, vault, faux, depot_code, ouvertures):
    (depot_code / "scripts").mkdir()
    (depot_code / "scripts" / "go.sh").write_text("echo salut", encoding="utf-8")
    fiche(racine, "scripts/go.sh")
    r = resultat.ouvrir(moteur(config, vault, faux), "mere", str((depot_code / "scripts" / "go.sh").resolve()))
    assert ouvertures == [(str((depot_code / "scripts").resolve()), False)] and "pourrait s'exécuter" in r["message"]


def test_cible_inconnue_refusee_jamais_ouverte(config, vault, faux, ouvertures):
    with pytest.raises(NonTrouve):
        resultat.ouvrir(moteur(config, vault, faux), "mere", "/etc/passwd")
    assert ouvertures == []


def test_aucune_application_message_clair(config, vault, faux, depot_code, monkeypatch):
    def absent(cible, url=False):
        raise FileNotFoundError("xdg-open")
    monkeypatch.setattr(resultat, "ouvrir_systeme", absent)
    with pytest.raises(Conflit, match="Aucune application"):
        resultat.ouvrir(moteur(config, vault, faux), "mere", str(depot_code.resolve()))


def test_routes_et_garde_poste_seul(config, vault, faux, depot_code, ouvertures):
    app = api.creer_app(config, moteur(config, vault, faux))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        liste = c.get("/api/taches/mere/resultat").json()
        assert liste["elements"][0]["genre"] == "dossier"
        r = c.post("/api/taches/mere/resultat/ouvrir", json={"cible": liste["elements"][0]["cible"]}, headers=H)
        assert r.status_code == 200 and ouvertures
    assert POSTE_SEUL_RE.fullmatch("/api/taches/x/resultat") and POSTE_SEUL_RE.fullmatch("/api/taches/x/resultat/ouvrir")
