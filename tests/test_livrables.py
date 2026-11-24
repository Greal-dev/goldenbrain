"""Livrables : relevé d'office (traces, lignes), déclaration, attendus, agrégation chez un parent, fichier disparu, appareil distant, CLI."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, api_appareils, cli, fiches, livrables
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from conftest import ecrire, tache_md

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
AGENT = {**H, "X-Orch-Tache": "chantier"}
ALPHA = "Projets/C1-Alpha"
NOTE = "[[Projets/C1-Alpha/notes/rapport]]"


@pytest.fixture
def moteur(config, vault, faux, racine):
    ecrire(racine, f"{ALPHA}/taches/chantier.md", tache_md(titre="Chantier"))
    ecrire(racine, f"{ALPHA}/taches/fille.md", tache_md(extra='parent: "[[chantier]]"\n', titre="Fille"))
    ecrire(racine, f"{ALPHA}/notes/rapport.md", "---\ntype: note\n---\n\n# Rapport\n")
    return Moteur(config, vault, {"faux": faux})


@pytest.fixture
def client(config, moteur):
    with TestClient(api.creer_app(config, moteur), base_url=BASE) as c:
        yield c


def liste(client, de="chantier", **params):
    r = client.get("/api/livrables", params={"de": de, **params})
    assert r.status_code == 200, r.text
    return r.json()


def cibles(r, ident="chantier"):
    return [x["cible"] for g in r["groupes"] if g["id"] == ident for x in g["livrables"]]


# --- normalisation et sécurité -------------------------------------------------------------------
@pytest.mark.parametrize("brut", ["", "   ", "../secret", "/tmp/a/../../etc/passwd", "javascript:alert(1)", "ftp://x/y",
                                  "a · b", "<!-- x -->", "x\x00y"])
def test_cibles_refusees(vault, brut):
    with pytest.raises(Invalide):
        livrables.normaliser(vault, brut)


def test_types_et_cles(vault, racine):
    assert livrables.typer(livrables.normaliser(vault, "https://exemple.org/p"))[0] == "url"
    assert livrables.typer(livrables.normaliser(vault, "branche:gb/livrables"))[0] == "branche"
    assert livrables.typer(livrables.normaliser(vault, "commit:abc1234"))[0] == "commit"
    assert livrables.typer(livrables.normaliser(vault, "publie:https://exemple.org/x"))[0] == "publie"
    assert livrables.typer(livrables.normaliser(vault, "/tmp/un/fichier.txt"))[0] == "fichier"


# --- API : déclarer, attendre, cocher, retirer ----------------------------------------------------
def test_declarer_retirer_et_auteur(client):
    r = client.post("/api/taches/chantier/livrables", json={"cible": "https://exemple.org/p", "titre": "Page"}, headers=H)
    assert r.status_code == 201 and r.json()["total"] == 1
    r = client.post("/api/taches/chantier/livrables", json={"cible": "branche:gb/x"}, headers=AGENT).json()
    items = {x["type"]: x for x in r["groupes"][0]["livrables"]}
    assert items["url"]["auteur"] == "moi" and items["url"]["titre"] == "Page"
    assert items["branche"]["auteur"] == "ia"
    client.post("/api/taches/chantier/livrables/retirer", json={"index": items["url"]["index"]}, headers=H)
    assert cibles(liste(client)) == ["gb/x"]


def test_cible_invalide_refusee_par_l_api(client):
    assert client.post("/api/taches/chantier/livrables", json={"cible": "../x"}, headers=H).status_code == 400
    assert client.post("/api/taches/chantier/livrables", json={"cible": "javascript:1"}, headers=H).status_code == 400


def test_attendu_puis_produit(client):
    client.post("/api/taches/chantier/livrables/attendre", json={"titre": "Rapport final"}, headers=H)
    r = liste(client)
    assert r["manquants"] == 1 and r["groupes"][0]["attendus"][0]["produit"] is False
    client.post("/api/taches/chantier/livrables/basculer", json={"index": 0}, headers=H)
    r = liste(client)
    assert r["manquants"] == 0 and r["groupes"][0]["attendus"][0]["produit"] is True
    assert client.post("/api/taches/chantier/livrables/basculer", json={"index": 9}, headers=H).status_code == 400


# --- relevé d'office : traces et lignes, sans migration ------------------------------------------
def test_traces_et_lignes_figurent_d_office(client, racine, moteur):
    p = racine / ALPHA / "taches" / "chantier.md"
    moteur.vault.consigner("chantier", "Traces", f"- 2026-11-20 10:00 — Rapport écrit — {NOTE}, `/tmp/livre.txt`")
    texte = p.read_text(encoding="utf-8")
    p.write_text(fiches.ecrire_lignes(texte, [{"fait": True, "texte": "Exporté", "date": "2026-11-21", "auteur": "ia",
                                                  "lien": "https://exemple.org/export"}]), encoding="utf-8")
    r = liste(client)
    assert set(x["type"] for x in r["groupes"][0]["livrables"]) == {"note", "fichier", "url"}


def test_dedoublonnage_trace_ligne_et_declare(client, racine, moteur):
    p = racine / ALPHA / "taches" / "chantier.md"
    moteur.vault.consigner("chantier", "Traces", f"- 2026-11-20 10:00 — Écrit — {NOTE}")
    texte = p.read_text(encoding="utf-8")
    p.write_text(fiches.ecrire_lignes(texte, [{"fait": True, "texte": "Rapport", "date": "2026-11-22", "auteur": "ia",
                                                  "lien": NOTE}]), encoding="utf-8")
    absolu = str(racine / ALPHA / "notes" / "rapport.md")
    client.post("/api/taches/chantier/livrables", json={"cible": absolu, "titre": "Le rapport"}, headers=H)
    items = liste(client)["groupes"][0]["livrables"]
    assert len(items) == 1 and items[0]["type"] == "note" and items[0]["titre"] == "Le rapport"
    assert items[0]["date"] == "2026-11-20" and set(items[0]["sources"]) >= {"trace", "ligne", "declare"}


def test_ligne_vers_une_tache_n_est_pas_un_livrable(client, racine):
    p = racine / ALPHA / "taches" / "chantier.md"
    p.write_text(fiches.ecrire_lignes(p.read_text(encoding="utf-8"), [
        {"fait": False, "texte": "Devenue tâche", "date": "2026-11-22", "auteur": "moi", "lien": "[[fille]]"}]), encoding="utf-8")
    assert liste(client)["total"] == 0


# --- fichier disparu ---------------------------------------------------------------------------
def test_fichier_disparu_signale_pas_masque(client, tmp_path):
    f = tmp_path / "sortie.txt"
    f.write_text("x", encoding="utf-8")
    client.post("/api/taches/chantier/livrables", json={"cible": str(f), "titre": "Sortie"}, headers=H)
    assert liste(client)["groupes"][0]["livrables"][0]["existe"] is True
    f.unlink()
    x = liste(client)["groupes"][0]["livrables"][0]
    assert x["existe"] is False and x["titre"] == "Sortie"
    assert client.post("/api/taches/chantier/livrables/ouvrir", json={"cible": x["cible"]}, headers=H).status_code == 409


def test_note_disparue_signalee(client, racine):
    client.post("/api/taches/chantier/livrables", json={"cible": NOTE}, headers=H)
    assert liste(client)["groupes"][0]["livrables"][0]["existe"] is True
    (racine / ALPHA / "notes" / "rapport.md").unlink()
    assert liste(client)["groupes"][0]["livrables"][0]["existe"] is False


# --- parent : agrégation par tâche d'origine, filtre, recherche ------------------------------------
def test_agregation_chez_le_parent(client):
    client.post("/api/taches/chantier/livrables", json={"cible": "https://exemple.org/a", "titre": "Alpha"}, headers=H)
    client.post("/api/taches/fille/livrables", json={"cible": "commit:abc1234", "titre": "Correctif"}, headers=H)
    r = liste(client)
    assert r["agrege"] and {g["id"] for g in r["groupes"]} == {"chantier", "fille"} and r["total"] == 2
    assert r["groupes"][0]["id"] == "chantier"  # la tâche elle-même d'abord
    assert not liste(client, "fille")["agrege"]
    assert [x["type"] for g in liste(client, type="commit")["groupes"] for x in g["livrables"]] == ["commit"]
    assert [g["id"] for g in liste(client, q="correctif")["groupes"]] == ["fille"]
    assert client.get("/api/livrables", params={"de": "chantier", "type": "inconnu"}).status_code == 400


def test_agregation_chez_un_conteneur_et_inconnu(client):
    client.post("/api/taches/fille/livrables", json={"cible": "branche:gb/f"}, headers=H)
    r = liste(client, "Projets/C1-Alpha")
    assert r["total"] == 1 and r["groupes"][0]["id"] == "fille"
    assert client.get("/api/livrables", params={"de": "n-existe-pas"}).status_code == 404


# --- appareil distant : jamais de lecture hors vault ----------------------------------------------
def test_distant_ne_lit_pas_le_poste(moteur, tmp_path):
    f = tmp_path / "secret.txt"
    f.write_text("x", encoding="utf-8")
    livrables.declarer(moteur.vault, "chantier", str(f), "Secret")
    assert livrables.releve(moteur, "chantier", distant=False)["groupes"][0]["livrables"][0]["existe"] is True
    x = livrables.releve(moteur, "chantier", distant=True)["groupes"][0]["livrables"][0]
    assert x["existe"] is None and x["ouvrable"] is False


def test_ouverture_reservee_au_poste():
    assert api_appareils.POSTE_SEUL_RE.search("/api/taches/chantier/livrables/ouvrir")


def test_ouverture_refuse_un_chemin_hors_liste(client, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert client.post("/api/taches/chantier/livrables/ouvrir", json={"cible": str(f)}, headers=H).status_code == 404


# --- CLI ------------------------------------------------------------------------------------------
def test_cli_livrable(client, capsys, monkeypatch):
    monkeypatch.setattr(cli, "http", lambda *a, **k: None, raising=False)
    r = client.post("/api/taches/chantier/livrables", json={"cible": "commit:abc1234"}, headers=AGENT)
    assert r.status_code == 201
    assert "livrable" in cli.cli_lignes.COMMANDES
