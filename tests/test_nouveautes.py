"""Journal des nouveautés (INV-NOUV-1) : entrées, CHANGELOG.md, « Quoi de neuf », script de publication.

Dépôts git temporaires ; jamais le vrai dépôt, jamais `gh` réellement lancé.
"""

import datetime as dt
import subprocess
import sys
from pathlib import Path

from orchestrateur import nouveautes

ID = ["-c", "user.name=Test", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false"]
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nouveautes.py"


def git(cwd, *args):
    r = subprocess.run(["git", *ID, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def enregistrer(depot, chemin, message):
    f = depot / chemin
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f.read_text(encoding="utf-8") + "x\n" if f.exists() else "x\n", encoding="utf-8")
    git(depot, "add", chemin)
    git(depot, "commit", "-q", "-m", message)
    return git(depot, "rev-parse", "HEAD")


def depot_neuf(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, "init", "-q", "-b", "main")
    return d, enregistrer(d, "a.py", "Départ")


def test_entrees_prend_les_lignes_nouveaute_puis_le_guide_jamais_le_reste(tmp_path):
    d, depart = depot_neuf(tmp_path)
    enregistrer(d, "a.py", "Refonte interne du moteur")  # ni ligne Nouveauté ni guide : muet
    enregistrer(d, "a.py", "Accélérer l'accueil\n\nNouveauté: l'accueil s'ouvre deux fois plus vite.\n"
                           "Nouveauté: Le tri des tâches est mémorisé")
    enregistrer(d, "docs/GUIDE.md", "Réglages : groupes repliables (INV-REG-2)")
    enregistrer(d, "docs/GUIDE.md", "Guide\n\nNouveauté: un guide pas à pas pour débuter")
    assert nouveautes.entrees(d, depart, "HEAD") == [
        "L'accueil s'ouvre deux fois plus vite", "Le tri des tâches est mémorisé",
        "Réglages : groupes repliables", "Un guide pas à pas pour débuter"]


def test_entree_portant_un_motif_sensible_n_est_jamais_publiee(tmp_path):
    d, depart = depot_neuf(tmp_path)
    (d / ".sensible").write_text("# commentaire\nclient-secret\n", encoding="utf-8")
    enregistrer(d, "a.py", "x\n\nNouveauté: tableau pour Client-Secret\nNouveauté: export en PDF")
    assert nouveautes.entrees(d, depart, "HEAD") == ["Export en PDF"]


def test_versions_datees_et_suffixe_le_meme_jour():
    jour = dt.date(2026, 11, 20)
    texte = nouveautes.ajouter("", nouveautes.section(nouveautes.prochaine_version("", jour), ["A"]))
    assert nouveautes.prochaine_version(texte, jour) == "2026.11.20.2"
    texte = nouveautes.ajouter(texte, nouveautes.section("2026.11.20.2", ["B"]))
    assert texte.startswith(nouveautes.ENTETE)
    assert [s["version"] for s in nouveautes.sections(texte)] == ["2026.11.20.2", "2026.11.20"]
    assert nouveautes.sections(texte)[1]["entrees"] == ["A"]


def test_version_sans_nouveaute_visible_le_dit_simplement():
    assert "Corrections et améliorations internes" in nouveautes.section("2026.11.20", [])


def test_quoi_de_neuf_lit_le_journal_distant_absent_du_local(tmp_path):
    d, _ = depot_neuf(tmp_path)
    local = nouveautes.ajouter("", nouveautes.section("2026.11.19", ["Ancien"]))
    (d / "CHANGELOG.md").write_text(local, encoding="utf-8")
    git(d, "add", "CHANGELOG.md")
    git(d, "commit", "-q", "-m", "v1")
    git(d, "checkout", "-q", "-b", "distant")
    (d / "CHANGELOG.md").write_text(nouveautes.ajouter(local, nouveautes.section("2026.11.20", ["Neuf"])),
                                    encoding="utf-8")
    git(d, "commit", "-q", "-am", "v2")
    git(d, "checkout", "-q", "main")
    assert nouveautes.quoi_de_neuf(d, "distant") == [{"version": "2026.11.20", "entrees": ["Neuf"]}]


def test_quoi_de_neuf_sans_journal_lit_l_historique_et_ne_tombe_jamais(tmp_path):
    d, _ = depot_neuf(tmp_path)
    git(d, "checkout", "-q", "-b", "distant")
    enregistrer(d, "a.py", "x\n\nNouveauté: thème sombre")
    git(d, "checkout", "-q", "main")
    assert nouveautes.quoi_de_neuf(d, "distant") == [{"version": None, "entrees": ["Thème sombre"]}]
    assert nouveautes.quoi_de_neuf(d, "inexistante") == []


def test_script_journal_puis_release_sans_envoi(tmp_path):
    d, depart = depot_neuf(tmp_path)
    fin = enregistrer(d, "a.py", "x\n\nNouveauté: export en PDF")
    precedent = tmp_path / "ancien.md"
    precedent.write_text(nouveautes.ajouter("", nouveautes.section("2026.11.19", ["Ancien"])), encoding="utf-8")
    sortie, notes = tmp_path / "CHANGELOG.md", tmp_path / "notes.md"
    r = subprocess.run([sys.executable, str(SCRIPT), "journal", "--depot", str(d), "--depuis", depart,
                        "--jusqua", fin, "--precedent", str(precedent), "--sortie", str(sortie),
                        "--notes", str(notes), "--jour", "2026-11-20"],
                       capture_output=True, text=True, encoding="utf-8", check=True)
    assert r.stdout.strip() == "2026.11.20"
    assert [s["version"] for s in nouveautes.sections(sortie.read_text(encoding="utf-8"))] == ["2026.11.20", "2026.11.19"]
    assert notes.read_text(encoding="utf-8").startswith("- Export en PDF")
    r = subprocess.run([sys.executable, str(SCRIPT), "release", "--version", "2026.11.20", "--depot-distant",
                        "proprietaire/depot", "--cible", "abc1234", "--notes", str(notes)],
                       capture_output=True, text=True, encoding="utf-8", check=True)
    assert r.stdout.startswith("gh release create v2026.11.20 --repo proprietaire/depot --target abc1234")
