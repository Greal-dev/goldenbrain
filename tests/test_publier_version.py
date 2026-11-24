"""Publication d'une version (scripts/publier_version.py) : note en quatre langues dans l'ordre, repli
sur le français, traduction écartée si elle sort de son rôle ou porte un motif personnel (INV-PUB-1),
étiquette datée, version précédente retrouvée par son arbre. Rien n'est envoyé ni construit."""

import datetime as dt
import shlex
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))

import publier_version as pv  # noqa: E402


def test_note_dans_l_ordre_anglais_francais_espagnol_allemand():
    texte = pv.note(["Bouton Valider"], "goldenbrain_1_amd64.deb", lambda langue, t: f"- [{langue}]")
    titres = [l for l in texte.splitlines() if l.startswith("## ")]
    assert titres == ["## English", "## Français", "## Español", "## Deutsch"]
    assert "- [English]" in texte and "- [Spanish]" in texte and "- [German]" in texte
    assert "- Bouton Valider" in texte.split("## Español")[0].split("## Français")[1]
    assert texte.count("goldenbrain_1_amd64.deb") == 4


def test_note_sans_traducteur_reprend_le_francais_et_sans_nouveaute_une_phrase():
    assert pv.note(["Bouton Valider"], "x.deb").count("- Bouton Valider") == 4
    vide = pv.note([], "x.deb")
    assert "- Internal fixes and improvements." in vide and "- Interne Korrekturen und Verbesserungen." in vide


def test_note_sans_traduction_ne_presente_pas_du_francais_sous_un_titre_etranger():
    texte = pv.note(["Bouton Valider"], "x.deb")  # aucun traducteur : le français est repris
    for titre, avertissement in (("English", "in French"), ("Español", "en francés"), ("Deutsch", "auf Französisch")):
        section = texte.split(f"## {titre}")[1].split("\n## ")[0]
        assert avertissement in section and "- Bouton Valider" in section
    assert "traduit" not in texte.split("## Français")[1].split("## Español")[0]  # le français n'a rien à signaler
    traduit = pv.note(["Bouton Valider"], "x.deb", lambda langue, t: f"- [{langue}]")
    assert "in French" not in traduit  # traduit : pas d'avertissement


def test_traduction_hors_liste_ou_personnelle_ecartee(tmp_path):
    (tmp_path / ".sensible").write_text("secretperso\n", encoding="utf-8")
    py = shlex.quote(sys.executable)  # shlex.split (POSIX) mange les « \\ » d'un chemin Windows
    bonne = pv.traducteur(f'{py} -c "print(\'- Hello {{langue}}\')"', tmp_path)
    assert bonne("English", "- Bonjour") == "- Hello English"
    bavarde = pv.traducteur(f'{py} -c "print(\'Voici la traduction :\')"', tmp_path)
    assert bavarde("English", "- Bonjour") is None
    fuite = pv.traducteur(f'{py} -c "print(\'- secretperso\')"', tmp_path)
    assert fuite("English", "- Bonjour") is None
    assert pv.traducteur("commande-inexistante-gb", tmp_path)("English", "- x") is None


def test_etiquette_datee_avec_suffixe_le_meme_jour():
    jour = dt.date(2026, 11, 20)
    assert pv.prochaine_etiquette([], jour) == "v2026.11.20"
    assert pv.prochaine_etiquette(["v2026.11.20", "v2026.11.19"], jour) == "v2026.11.20.2"


def test_version_precedente_retrouvee_par_son_arbre(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True,
                              text=True, encoding="utf-8").stdout.strip()
    git("init", "-q")
    for n in ("un", "deux"):
        (tmp_path / "f.txt").write_text(n, encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", n)
    premier = git("rev-parse", "HEAD~1")
    assert pv.commit_par_arbre(tmp_path, git("rev-parse", "HEAD~1^{tree}"), "HEAD") == premier
    assert pv.commit_par_arbre(tmp_path, "0" * 40, "HEAD") is None
