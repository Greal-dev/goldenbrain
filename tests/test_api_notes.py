"""Routes `/api/vault/*` (lot 6) via TestClient : formes, erreurs, écriture, SSE, fichiers."""

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire
from orchestrateur import api, fiches
from orchestrateur.config import ConfigNotes
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, "Notes/Accueil.md",
           "---\ntype: hub\ntags: [a]\n---\n# Accueil\n[[mere]] [[Absente]] ![[img.png]] "
           "[[Notes/Sous/Fille#Haut|la fille]]\n")
    ecrire(racine, "Notes/Sous/Fille.md", "# Fille\nretour vers [[Accueil]]\n")
    ecrire(racine, "Notes/b.md", "# B\n")
    ecrire(racine, "Notes/img.png", "png")
    ecrire(racine, "Notes/dessin.svg", "<svg onload='alert(1)'/>")
    ecrire(racine, "Notes/outil.exe", "MZ")
    ecrire(racine, ".obsidian/workspace.md", "# caché\n")
    ecrire(racine, "Prive/Journal/j.md", "# Journal intime\n")
    config.notes = ConfigNotes(exclure=["Prive"], ttl_s=0.2)
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def test_dossier_un_niveau_compteurs_tri_exclus(client):
    d = client.get("/api/vault/dossier").json()
    assert d["chemin"] == "" and d["parents"] == []
    noms = [x["nom"] for x in d["dossiers"]]
    assert noms == sorted(noms, key=str.casefold) and ".obsidian" not in noms and "Prive" not in noms
    assert {"nom": "Notes", "chemin": "Notes", "notes": 3} in d["dossiers"]
    assert {"nom": "Projets", "chemin": "Projets", "notes": 8} in d["dossiers"]
    n = client.get("/api/vault/dossier?chemin=Notes").json()
    assert [x["nom"] for x in n["notes"]] == ["Accueil", "b"]
    assert set(n["notes"][0]) == {"chemin", "nom", "titre", "type", "maj"}
    assert n["notes"][0]["titre"] == "Accueil" and n["notes"][0]["type"] == "hub"
    assert [f["nom"] for f in n["fichiers"]] == ["dessin.svg", "img.png", "outil.exe"]
    s = client.get("/api/vault/dossier?chemin=Notes/Sous").json()
    assert s["parents"] == [{"nom": "vault", "chemin": ""}, {"nom": "Notes", "chemin": "Notes"}]
    for interdit in (".obsidian", "Prive", "Prive/Journal", "../", "Notes/b.md"):
        assert client.get(f"/api/vault/dossier?chemin={interdit}").status_code == 404


def test_note_frontmatter_liens_entrants_tache(client):
    n = client.get("/api/vault/note?chemin=Notes/Accueil.md").json()
    assert n["frontmatter"] == {"type": "hub", "tags": ["a"]} and n["titre"] == "Accueil"
    assert n["contenu"].startswith("---\ntype: hub") and n["tache"] is None
    assert isinstance(n["mtime_ns"], str)
    liens = {x["cible"]: x for x in n["liens"]}
    assert liens["mere"]["chemin"] == "Projets/C1-Alpha/taches/mere.md"
    assert liens["Absente"]["chemin"] is None
    assert liens["img.png"]["incorpore"] and liens["img.png"]["chemin"] == "Notes/img.png"
    f = liens["Notes/Sous/Fille"]
    assert (f["alias"], f["ancre"], f["chemin"]) == ("la fille", "Haut", "Notes/Sous/Fille.md")
    assert n["entrants"] == [{"chemin": "Notes/Sous/Fille.md", "titre": "Fille",
                              "extrait": "retour vers [[Accueil]]"}]
    t = client.get("/api/vault/note?chemin=Projets/C1-Alpha/taches/mere.md").json()
    assert t["tache"] == "mere"


@pytest.mark.parametrize("chemin", ["../x.md", "C:/Windows/win.ini", "\\\\srv\\x.md",
                                    ".obsidian/workspace.md", "Prive/Journal/j.md",
                                    "Notes/Accueil.md::$DATA", "CON", "Notes/Accueil.md."])
def test_note_evasion_refusee(client, chemin):
    assert client.get("/api/vault/note", params={"chemin": chemin}).status_code in (400, 404)
    r = client.put("/api/vault/note", json={"chemin": chemin, "contenu": "x", "mtime_ns": "0"},
                   headers=H)
    assert r.status_code in (400, 404)


def test_note_404_et_pas_une_note(client):
    assert client.get("/api/vault/note?chemin=Notes/rien.md").status_code == 404
    assert client.get("/api/vault/note?chemin=Notes/img.png").status_code == 400
    assert client.get("/api/vault/note").status_code == 400


def test_ecriture_succes_sse_et_conflit(client, racine):
    q = client.app.state.moteur.abonner()
    n = client.get("/api/vault/note?chemin=Notes/b.md").json()
    r = client.put("/api/vault/note", headers=H,
                   json={"chemin": "Notes/b.md", "contenu": "# B\nzèbre\n", "mtime_ns": n["mtime_ns"]})
    assert r.status_code == 200 and r.json()["contenu"] == "# B\nzèbre\n"
    assert q.get_nowait() == {"type": "note", "chemin": "Notes/b.md"}
    assert client.get("/api/vault/recherche?q=zebre").json()[0]["chemin"] == "Notes/b.md"
    r = client.put("/api/vault/note", headers=H,
                   json={"chemin": "Notes/b.md", "contenu": "perdu", "mtime_ns": n["mtime_ns"]})
    assert r.status_code == 409 and r.json()["courante"]["contenu"] == "# B\nzèbre\n"
    assert "detail" in r.json() and (racine / "Notes/b.md").read_text("utf-8") == "# B\nzèbre\n"
    assert client.put("/api/vault/note", json={"chemin": "Notes/b.md", "contenu": "x",
                                               "mtime_ns": "1"}).status_code == 403


def test_creation(client, racine):
    r = client.post("/api/vault/note", headers=H,
                    json={"dossier": "Notes", "nom": "Nouvelle", "contenu": "# N\n"})
    assert r.status_code == 201 and r.json()["chemin"] == "Notes/Nouvelle.md"
    assert (racine / "Notes/Nouvelle.md").read_bytes() == b"# N\n"
    assert client.post("/api/vault/note", headers=H,
                       json={"dossier": "Notes", "nom": "nouvelle"}).status_code == 409
    assert (racine / "Notes/Nouvelle.md").read_bytes() == b"# N\n"
    for nom in ("a:b", "CON", "x?", "a/b"):
        assert client.post("/api/vault/note", headers=H,
                           json={"dossier": "Notes", "nom": nom}).status_code == 400
    assert client.post("/api/vault/note", headers=H,
                       json={"dossier": "Notes/Neuf", "nom": "x"}).status_code == 404
    r = client.post("/api/vault/note", headers=H,
                    json={"dossier": "Notes/Neuf", "nom": "x", "creer_dossier": True})
    assert r.status_code == 201 and (racine / "Notes/Neuf/x.md").is_file()
    assert client.post("/api/vault/note", headers=H,
                       json={"dossier": "../dehors", "nom": "x", "creer_dossier": True}
                       ).status_code == 404


def test_recherche_dossier_limite_et_modification_externe(client, racine):
    r = client.get("/api/vault/recherche?q=accueil").json()
    assert r[0]["chemin"] == "Notes/Accueil.md" and set(r[0]) == {"chemin", "titre", "extraits",
                                                                  "score"}
    assert all(x["chemin"].startswith("Notes/Sous/")
               for x in client.get("/api/vault/recherche?q=accueil&dossier=Notes/Sous").json())
    assert client.get("/api/vault/recherche?q=journal").json() == []
    assert client.get("/api/vault/recherche?q=dehors&dossier=../").status_code == 404
    for i in range(110):
        ecrire(racine, f"Masse/n{i}.md", "commun\n")
    time.sleep(0.25)
    assert len(client.get("/api/vault/recherche?q=commun&limite=500").json()) == 100
    ecrire(racine, "Notes/b.md", "# B\nobsidian a écrit ici\n")
    time.sleep(0.25)
    assert client.get("/api/vault/recherche?q=obsidian ecrit").json()[0]["chemin"] == "Notes/b.md"


def test_resoudre(client):
    def res(**p):
        return client.get("/api/vault/resoudre", params=p).json()["chemin"]
    assert res(lien="[[Fille|x]]") == "Notes/Sous/Fille.md"
    assert res(lien="Sous/Fille#Haut", depuis="Notes/Accueil.md") == "Notes/Sous/Fille.md"
    assert res(lien="img.png") == "Notes/img.png"
    assert res(lien="Absente") is None
    assert client.get("/api/vault/resoudre?lien=x&depuis=../y.md").status_code == 404


def test_fichier(client):
    r = client.get("/api/vault/fichier?chemin=Notes/img.png")
    assert r.status_code == 200 and r.content == b"png"
    assert r.headers["content-type"] == "image/png" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("inline")
    svg = client.get("/api/vault/fichier?chemin=Notes/dessin.svg")
    assert svg.headers["content-disposition"].startswith("attachment")
    assert client.get("/api/vault/fichier?chemin=Notes/Accueil.md").status_code == 400
    assert client.get("/api/vault/fichier?chemin=Notes/outil.exe").status_code == 400
    assert client.get("/api/vault/fichier?chemin=../vault/Notes/img.png").status_code == 404
    assert client.get("/api/vault/fichier?chemin=Notes/img.png:flux").status_code == 400
    assert client.get("/api/vault/fichier?chemin=Notes/absent.png").status_code == 404



# --- dossiers cachés et listage sans attente (correctif du 13/11) -------------------------
def test_dossier_cache_playwright_invisible_partout(client, racine):
    ecrire(racine, ".playwright-mcp/trace.md", "# trace [[Accueil]]\n")
    ecrire(racine, ".playwright-mcp/capture.png", "png")
    ecrire(racine, "Notes/.cache/x.md", "# x\n")
    ecrire(racine, "Notes/.brouillon.md", "# brouillon\n")
    client.app.state.index_notes.rafraichir()
    d = client.get("/api/vault/dossier").json()
    assert ".playwright-mcp" not in [x["nom"] for x in d["dossiers"]]
    n = client.get("/api/vault/dossier?chemin=Notes").json()
    assert ".cache" not in [x["nom"] for x in n["dossiers"]]
    assert ".brouillon" not in [x["nom"] for x in n["notes"]]
    assert {"nom": "Notes", "chemin": "Notes", "notes": 3} in d["dossiers"]
    for url in ("/api/vault/dossier?chemin=.playwright-mcp",
                "/api/vault/note?chemin=.playwright-mcp/trace.md",
                "/api/vault/note?chemin=Notes/.brouillon.md",
                "/api/vault/fichier?chemin=.playwright-mcp/capture.png"):
        assert client.get(url).status_code == 404
    assert client.get("/api/vault/resoudre?lien=trace").json()["chemin"] is None
    assert client.get("/api/vault/recherche?q=brouillon").json() == []
    entrants = client.get("/api/vault/note?chemin=Notes/Accueil.md").json()["entrants"]
    assert [e["chemin"] for e in entrants] == ["Notes/Sous/Fille.md"]
    assert client.post("/api/vault/note", headers=H,
                       json={"dossier": ".playwright-mcp", "nom": "x"}).status_code == 404


def test_listage_n_attend_pas_un_rafraichissement_de_l_index(client):
    index = client.app.state.index_notes
    client.get("/api/vault/dossier")  # construction initiale faite (ou attendue)
    bloque, sorti = threading.Event(), threading.Event()
    balayer = index._balayer

    def lent():
        bloque.wait(5)
        sorti.set()
        return balayer()

    index._balayer = lent
    index.balaye = time.monotonic() - 3600  # périmé
    debut = time.perf_counter()
    d = client.get("/api/vault/dossier").json()
    assert time.perf_counter() - debut < 1 and not sorti.is_set()
    assert {"nom": "Notes", "chemin": "Notes", "notes": 3} in d["dossiers"]
    bloque.set()
    assert sorti.wait(5)


# --- déplacer / renommer une note (INV-NOTE-3) --------------------------------------------
def deplacer(client, chemin, vers, **autres):
    return client.post("/api/vault/note/deplacer", headers=H,
                       json={"chemin": chemin, "vers": vers, **autres})


def photo(racine: Path) -> dict:
    return {f.relative_to(racine).as_posix(): f.read_bytes()
            for f in sorted(racine.rglob("*")) if f.is_file()}


def test_deplacement_simple_liens_entrants_sse_et_index(client, racine):
    q = client.app.state.moteur.abonner()
    assert deplacer(client, "Notes/Sous/Fille.md", "Notes/Autre/Fille.md").status_code == 404
    r = deplacer(client, "Notes/Sous/Fille.md", "Notes/Autre/Fille.md", creer_dossier=True)
    assert r.status_code == 200, r.text
    assert r.json()["note"]["chemin"] == "Notes/Autre/Fille.md"
    assert r.json()["fichiers_reecrits"] == 1
    assert not (racine / "Notes/Sous/Fille.md").exists()
    assert (racine / "Notes/Autre/Fille.md").read_text("utf-8") == "# Fille\nretour vers [[Accueil]]\n"
    assert "[[Notes/Autre/Fille#Haut|la fille]]" in (racine / "Notes/Accueil.md").read_text("utf-8")
    assert q.get_nowait() == {"type": "note", "chemin": "Notes/Autre/Fille.md",
                              "ancien": "Notes/Sous/Fille.md"}
    assert client.get("/api/vault/resoudre?lien=Fille").json()["chemin"] == "Notes/Autre/Fille.md"
    a = client.get("/api/vault/note?chemin=Notes/Accueil.md").json()
    assert {x["cible"]: x["chemin"] for x in a["liens"]}["Notes/Autre/Fille"] == \
        "Notes/Autre/Fille.md"


def test_renommage_wikilinks_par_nom_homonyme_intact(client, racine):
    ecrire(racine, "Ailleurs/b.md", "# autre b\n")
    ecrire(racine, "Ailleurs/c.md", "[[b]] vise l'homonyme voisin\n")
    ecrire(racine, "Notes/x.md", "[[b]] [[b|alias]] [[b#ancre]] ![[b]] [[B.md]] [[Notes/b]]\n"
                                 "`[[b]]` [[bis]]\n")
    client.app.state.index_notes.rafraichir()
    r = deplacer(client, "Notes/b.md", "Notes/beta.md")
    assert r.status_code == 200, r.text
    assert (racine / "Notes/x.md").read_text("utf-8") == (
        "[[beta]] [[beta|alias]] [[beta#ancre]] ![[beta]] [[beta.md]] [[Notes/beta]]\n"
        "`[[b]]` [[bis]]\n")
    assert (racine / "Ailleurs/c.md").read_text("utf-8") == "[[b]] vise l'homonyme voisin\n"
    assert r.json()["fichiers_reecrits"] == 1


def test_liens_relatifs_sortants_et_entrants_recalcules(client, racine):
    ecrire(racine, "Notes/Sous/r.md", "[[../b]] [l](../Accueil.md) [[./Fille#H|f]]\n")
    ecrire(racine, "Notes/in.md", "[[./Sous/r]] et [v](Sous/r.md)\n")
    client.app.state.index_notes.rafraichir()
    r = deplacer(client, "Notes/Sous/r.md", "Notes/r.md")
    assert r.status_code == 200, r.text
    assert (racine / "Notes/r.md").read_text("utf-8") == \
        "[[./b]] [l](./Accueil.md) [[./Sous/Fille#H|f]]\n"
    assert (racine / "Notes/in.md").read_text("utf-8") == "[[./r]] et [v](Sous/r.md)\n"


def test_echec_en_cours_de_deplacement_restaure_l_etat_initial(client, racine, monkeypatch):
    ecrire(racine, "Notes/Sous/r.md", "[[../b]]\n")
    ecrire(racine, "Notes/in.md", "[[Notes/Sous/r]] [[Notes/Sous/r|x]]\n")
    ecrire(racine, "Notes/in2.md", "[[Notes/Sous/r]]\n")
    client.app.state.index_notes.rafraichir()
    avant = photo(racine)
    vrai, n = fiches.ecrire_atomique, []

    def panne(p, texte):
        n.append(p)
        if len(n) == 2:
            raise OSError("disque plein")
        vrai(p, texte)

    monkeypatch.setattr(fiches, "ecrire_atomique", panne)
    r = deplacer(client, "Notes/Sous/r.md", "Notes/Neuf/r2.md", creer_dossier=True)
    assert r.status_code == 409 and "rien n'a changé" in r.json()["detail"]
    assert photo(racine) == avant and not (racine / "Notes/Neuf").exists()


def test_deplacer_une_tache_permis_renommer_ou_tour_actif_409(client, racine):
    q = client.app.state.moteur.abonner()
    r = deplacer(client, "Projets/C1-Alpha/taches/petit.md", "Projets/C2-Beta/taches/renomme.md")
    assert r.status_code == 409 and "par son titre" in r.json()["detail"]
    moteur = client.app.state.moteur
    moteur.etats["petit"] = "en_cours"
    r = deplacer(client, "Projets/C1-Alpha/taches/petit.md", "Projets/C2-Beta/taches/petit.md")
    assert r.status_code == 409 and r.json()["occupee"]["tache"] == "petit"  # INV-VERROU-1
    # INV-ALIGN-2 : `forcer` n'outrepasse pas le verrou dur de la note d'une tâche au travail.
    r = deplacer(client, "Projets/C1-Alpha/taches/petit.md", "Projets/C2-Beta/taches/petit.md",
                 forcer=True)
    assert r.status_code == 409 and "séance de travail" in r.json()["detail"] and "occupee" not in r.json()
    moteur.etats["petit"] = "inactif"
    r = deplacer(client, "Projets/C1-Alpha/taches/petit.md", "Projets/C2-Beta/taches/petit.md")
    assert r.status_code == 200 and r.json()["note"]["tache"] == "petit"
    assert moteur.vault.tache("petit").conteneur == "Projets/C2-Beta"
    assert [q.get_nowait()["type"] for _ in range(2)] == ["note", "arbre"]


@pytest.mark.parametrize("vers", ["Notes/Accueil.md", "../dehors.md", ".obsidian/b.md",
                                  "Prive/b.md", "Notes/.b.md"])
def test_deplacement_refuse_409(client, racine, vers):
    avant = photo(racine)
    r = deplacer(client, "Notes/b.md", vers, creer_dossier=True)
    assert r.status_code == 409, r.text
    assert photo(racine) == avant


def test_fichier_pdf_incorporable_par_l_interface_seulement(client):
    ecrire(client.app.state.moteur.vault.racine, "Notes/doc.pdf", "%PDF")
    r = client.get("/api/vault/fichier?chemin=Notes/doc.pdf")
    assert r.status_code == 200 and r.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
    autre = client.get("/api/vault/dossier")
    assert autre.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in autre.headers["content-security-policy"]
