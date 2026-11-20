"""Notes du vault (lot 6) : chemins sûrs, extraction et résolution des liens, index incrémental."""

import os
from pathlib import Path

import pytest

from orchestrateur import notes
from orchestrateur.index_notes import IndexNotes, normaliser
from orchestrateur.vault import ErreurOrch, Invalide, NonTrouve

from conftest import ecrire


@pytest.fixture
def vn(tmp_path: Path) -> Path:
    r = tmp_path / "vn"
    ecrire(r, "Accueil.md", "# Accueil\n[[Projets/Alpha/Plan]] et [[Plan]]\n")
    ecrire(r, "Projets/Alpha/Plan.md", "---\ntype: plan\n---\n# Plan Alpha\n![[schema.png]]\n")
    ecrire(r, "Projets/Alpha/schema.png", "png")
    ecrire(r, "Projets/Alpha/Notes/Idee.md", "[[Plan]] [[../Plan#But|le plan]]\n")
    ecrire(r, "Projets/Beta/Plan.md", "# Plan Beta\n")
    ecrire(r, "Archives/Vieux/Plan.md", "# Vieux\n")
    ecrire(r, "Plan-long/x/y/Plan.md", "# Profond\n")
    ecrire(r, ".obsidian/app.json", "{}")
    ecrire(r, "Prive/Secret/s.md", "# Secret\n")
    return r


@pytest.fixture
def idx(vn: Path) -> IndexNotes:
    i = IndexNotes(vn, ["Prive"], ttl_s=0)
    i.rafraichir()
    return i


EVASIONS = ["../x.md", "a/../../x.md", "a\\..\\..\\x.md", "a/..\\b.md", "/etc/passwd",
            "C:/Windows/win.ini", "c:x.md", "\\\\serveur\\partage\\x.md", "//serveur/x.md",
            "Accueil.md:flux", "Accueil.md::$DATA", "CON", "nul.md", "dossier/COM1.txt",
            "LPT1", "aux .md", "Accueil.md.", "Accueil.md ", ".obsidian/app.json",
            "Projets/.git/config", "a/b/.trash/x.md", ".Claude/x.md", "Prive/Secret/s.md",
            "prive/secret/s.md", "x\x00.md"]


@pytest.mark.parametrize("chemin", EVASIONS)
def test_evasion_de_chemin_refusee(vn, chemin):
    with pytest.raises((Invalide, NonTrouve)):
        notes.chemin_sur(vn.resolve(), chemin, ["Prive"])


def test_chemin_valide_et_separateurs_mixtes(vn):
    rel, p = notes.chemin_sur(vn.resolve(), "Projets\\Alpha/./Plan.md", [])
    assert rel == "Projets/Alpha/Plan.md" and p.is_file()
    assert notes.chemin_sur(vn.resolve(), "", [], vide_ok=True)[0] == ""
    with pytest.raises(Invalide):
        notes.chemin_sur(vn.resolve(), "", [])


def test_jonction_sortante_refusee_et_invisible(vn, tmp_path):
    _winapi = pytest.importorskip("_winapi")
    dehors = tmp_path / "dehors"
    ecrire(dehors, "fuite.md", "# Fuite\n")
    _winapi.CreateJunction(str(dehors), str(vn / "lien"))
    with pytest.raises(NonTrouve):
        notes.chemin_sur(vn.resolve(), "lien/fuite.md", [])
    i = IndexNotes(vn, [], 0)
    i.rafraichir()
    assert not any(r.startswith("lien/") for r in i.notes)


def test_lien_symbolique_sortant_refuse(vn, tmp_path):
    dehors = ecrire(tmp_path, "dehors.md", "x")
    try:
        os.symlink(dehors, vn / "sym.md")
    except OSError:
        pytest.skip("liens symboliques non autorisés sur ce poste")
    with pytest.raises(NonTrouve):
        notes.chemin_sur(vn.resolve(), "sym.md", [])


@pytest.mark.parametrize("nom", ["", "a/b", "a\\b", "a:b", "x?", "CON", "fin.", ".cache", "a|b"])
def test_nom_de_note_invalide(nom):
    with pytest.raises(Invalide):
        notes.nom_valide(nom)


def test_extraction_des_liens():
    texte = ("[[A|alias]] ![[img.png]] [[B#Titre]] [[C\\|t]] [t](sous/D.md) [w](https://x.fr) "
             "[s](#ancre)\n```\n[[Code]]\n```\n`[[Inline]]` [e](mon%20fichier.md)\n")
    liens = notes.extraire(texte)
    vus = [(x["cible"], x["alias"], x["ancre"], x["incorpore"]) for x in liens]
    assert vus == [("A", "alias", "", False), ("img.png", "", "", True), ("B", "", "Titre", False),
                   ("C", "t", "", False), ("sous/D.md", "t", "", False),
                   ("mon fichier.md", "e", "", False)]


def test_resolution_ordre_obsidian(idx):
    r = idx.resoudre
    assert r("Projets/Alpha/Plan", "Accueil.md") == "Projets/Alpha/Plan.md"        # exact
    assert r("projets/alpha/plan.md", None) == "Projets/Alpha/Plan.md"             # casse
    assert r("../Plan", "Projets/Alpha/Notes/Idee.md") == "Projets/Alpha/Plan.md"  # relatif
    assert r("Plan", "Projets/Beta/x.md") == "Projets/Beta/Plan.md"                # plus proche
    assert r("Plan", "Projets/Alpha/Notes/Idee.md") == "Projets/Alpha/Plan.md"
    assert r("PLAN", "Accueil.md") == "Projets/Beta/Plan.md"                       # puis plus court
    assert r("Beta/Plan", "Accueil.md") == "Projets/Beta/Plan.md"                  # suffixe
    assert r("schema.png", "Accueil.md") == "Projets/Alpha/schema.png"             # non md
    assert r("Inconnue", "Accueil.md") is None                                     # à créer
    assert r("Secret/s", None) is None and r("s", None) is None                    # exclu
    assert r("", "Accueil.md") == "Accueil.md"                                     # [[#ancre]]


def test_entrants(idx):
    entrants = idx.entrants("Projets/Alpha/Plan.md")
    assert [e["chemin"] for e in entrants] == ["Accueil.md", "Projets/Alpha/Notes/Idee.md"]
    assert entrants[0]["titre"] == "Accueil" and "[[Projets/Alpha/Plan]]" in entrants[0]["extrait"]
    assert [e["chemin"] for e in idx.entrants("Projets/Beta/Plan.md")] == ["Accueil.md"]
    assert idx.entrants("Archives/Vieux/Plan.md") == []


def test_index_incremental_un_seul_fichier_relu(vn, idx):
    avant = idx.relus
    idx.rafraichir()
    assert idx.relus == avant
    ecrire(vn, "Projets/Beta/Plan.md", "# Plan Beta modifié\n")
    idx.rafraichir()
    assert idx.relus == avant + 1
    (vn / "Accueil.md").unlink()
    idx.rafraichir()
    assert "Accueil.md" not in idx.notes and idx.entrants("Projets/Alpha/Plan.md")[0]["chemin"] \
        == "Projets/Alpha/Notes/Idee.md"


def test_ttl_evite_le_balayage(vn):
    i = IndexNotes(vn, [], ttl_s=60)
    i.assurer()
    ecrire(vn, "Nouvelle.md", "# Nouvelle\n")
    i.assurer()
    assert "Nouvelle.md" not in i.notes
    i.maj("Nouvelle.md")
    assert "Nouvelle.md" in i.notes


def test_recherche_accents_mots_expression_ponderation(vn):
    ecrire(vn, "Echeance.md", "# Échéance\nrien\n")
    ecrire(vn, "Corps.md", "# Autre\nl'échéance du bail approche\n\nune ECHEANCE encore\n")
    i = IndexNotes(vn, [], 0)
    i.rafraichir()
    res = i.chercher("echeance")
    assert [r["chemin"] for r in res] == ["Echeance.md", "Corps.md"]  # titre > corps
    assert res[1]["extraits"] == [{"ligne": 2, "texte": "l'échéance du bail approche"},
                                  {"ligne": 4, "texte": "une ECHEANCE encore"}]
    assert [r["chemin"] for r in i.chercher("échéance bail")] == ["Corps.md"]
    assert i.chercher('"bail approche"')[0]["chemin"] == "Corps.md"
    assert i.chercher('"approche bail"') == []
    assert [r["chemin"] for r in i.chercher("plan", dossier="Projets/Alpha")] == \
        ["Projets/Alpha/Plan.md", "Projets/Alpha/Notes/Idee.md"]
    exclusif = IndexNotes(vn, ["Prive"], 0)
    exclusif.rafraichir()
    assert exclusif.chercher("secret") == [] and i.chercher("secret")
    assert normaliser("Éé") == "ee"


def test_ecriture_conflit_crlf_bom(vn, idx):
    class V:  # vault minimal : pas de tâche
        racine = vn.resolve()

        def index(self):
            return {}, {}

    p = vn / "Crlf.md"
    p.write_bytes(b"\xef\xbb\xbf---\r\ntype: x\r\n---\r\nligne\r\n")
    n = notes.note(idx, V(), "Crlf.md", p)
    assert n["contenu"] == "---\ntype: x\n---\nligne\n" and n["frontmatter"] == {"type": "x"}
    n2 = notes.ecrire(idx, V(), "Crlf.md", p, n["contenu"] + "ajout\n", n["mtime_ns"])
    assert p.read_bytes() == b"\xef\xbb\xbf---\r\ntype: x\r\n---\r\nligne\r\najout\r\n"
    with pytest.raises(notes.ConflitNote) as e:  # date périmée : rien n'est écrasé
        notes.ecrire(idx, V(), "Crlf.md", p, "écrasé", n["mtime_ns"])
    assert e.value.code == 409 and e.value.courante["mtime_ns"] == n2["mtime_ns"]
    assert b"ajout" in p.read_bytes()
    brut = "a\nb\r\nc  \n\tfin sans saut"
    lf = vn / "Lf.md"
    lf.write_bytes(b"x\n")
    n = notes.note(idx, V(), "Lf.md", lf)
    notes.ecrire(idx, V(), "Lf.md", lf, brut, n["mtime_ns"])
    assert lf.read_bytes() == brut.encode()
    with pytest.raises(ErreurOrch):
        notes.ecrire(idx, V(), "Projets/Alpha/schema.png", vn / "Projets/Alpha/schema.png", "", "0")
