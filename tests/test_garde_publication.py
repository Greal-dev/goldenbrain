"""INV-PUB-1 : la garde de publication de la porte reconnaît les données sensibles usuelles."""

import importlib.util
import re
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("check", Path(__file__).parents[1] / "scripts" / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def touche(ligne: str) -> set[str]:
    return {nom for nom, m in check.MOTIFS_PUBLICS.items() if re.search(m, ligne, re.I)}


# Échantillons coupés par « ¦ », retiré à l'exécution : ce fichier ne doit pas déclencher la garde elle-même.
@pytest.mark.parametrize("ligne, attendu", [
    ("écrire à jean.dupont@¦exemple.fr", "adresse électronique"),
    (r"C:\Us¦ers\jdupont\Documents", "chemin personnel"),
    ("/c/Us¦ers/jdupont/vault", "chemin personnel"),
    ("/ho¦me/jdupont/vault", "chemin personnel"),
    ("--resume 4cf7aeef¦-e862-421f-8bac-03d4a4939a3b", "identifiant de session"),
    ("cle = sk¦-ant-api03-abcdefghijklmnopqrstuv", "jeton"),
    ("ghp¦_abcdefghijklmnopqrstuvwxyz0123", "jeton"),
])
def test_donnee_sensible_reconnue(ligne, attendu):
    assert attendu in touche(ligne.replace("¦", ""))


@pytest.mark.parametrize("ligne", [
    "user.email t@example.org", "C:/Users/utilisateur/Documents/Vault", "~/Documents/Vault",
    "00000000-0000-4000-8000-000000000001", "@pytest.fixture", "statut retour-humain",
])
def test_exemple_fictif_admis(ligne):
    assert not touche(ligne)


def test_motifs_personnels_lus_hors_depot(tmp_path, monkeypatch):
    (tmp_path / ".sensible").write_text("# commentaire\n\nmon-projet\n", "utf-8")
    monkeypatch.setattr(check, "RACINE", tmp_path)
    assert check.motifs_personnels() == ["mon-projet"]


def _garde(tmp_path, monkeypatch, notice: str, motif: str) -> list[str]:
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "NOTICE").write_text(notice, "utf-8")
    (tmp_path / ".sensible").write_text(motif + "\n", "utf-8")
    (tmp_path / ".gitignore").write_text(".sensible\n", "utf-8")
    monkeypatch.setattr(check, "RACINE", tmp_path)
    return check.sensibles()


def test_notice_admet_le_nom_de_l_auteur(tmp_path, monkeypatch):
    assert _garde(tmp_path, monkeypatch, "GoldenBrain — Copyright 2026 Jean Dupont\n", "dupont") == []


def test_notice_refuse_tout_autre_contenu_personnel(tmp_path, monkeypatch):
    erreurs = _garde(tmp_path, monkeypatch, "GoldenBrain — Copyright 2026 Jean Dupont\nContact : Dupont\n", "dupont")
    assert erreurs == ["NOTICE:2 : motif personnel n°1 (INV-PUB-1)"]


def test_notice_refuse_une_adresse_sur_la_ligne_d_auteur(tmp_path, monkeypatch):
    erreurs = _garde(tmp_path, monkeypatch, "GoldenBrain — Copyright 2026 Jean Dupont <jean@¦exemple.fr>\n".replace("¦", ""), "dupont")
    assert "NOTICE:1 : motif personnel n°1 (INV-PUB-1)" in erreurs and "NOTICE:1 : adresse électronique (INV-PUB-1)" in erreurs


def test_garde_avertit_quand_sensible_est_absent(tmp_path, monkeypatch, capsys):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(check, "RACINE", tmp_path)
    monkeypatch.setattr(check, "motifs_personnels", lambda: [])
    assert check.sensibles() == []
    assert "AVERTISSEMENT : `.sensible` absent" in capsys.readouterr().out


def test_element_recense_avertit_sans_bloquer_mais_le_nouveau_bloque(tmp_path, monkeypatch, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "publication-connue.txt").write_text(
        f"# commentaire\nNOTICE\t{check.empreinte('Contact : Dupont')}\n", "utf-8")
    erreurs = _garde(tmp_path, monkeypatch, "Contact : Dupont\nAutre : Dupont\n", "dupont")
    assert erreurs == ["NOTICE:2 : motif personnel n°1 (INV-PUB-1)"]
    assert "NOTICE:1 : motif personnel n°1 (INV-PUB-1) déjà recensé" in capsys.readouterr().out


def test_adresse_du_depot_public_admise_mais_pas_le_motif_ailleurs(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text(
        f"git clone https://{check.DEPOT_PUBLIC.pattern.replace(chr(92), '')}.git\nProjet : goldenbrain\n", "utf-8")
    erreurs = _garde(tmp_path, monkeypatch, "", "goldenbrain")
    assert erreurs == ["README.md:2 : motif personnel n°1 (INV-PUB-1)"]
