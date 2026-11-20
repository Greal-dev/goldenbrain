"""Portabilité Windows : aucune lecture/écriture texte ne dépend de l'encodage du poste (cp1252 sous Windows)."""

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).parents[1]
_spec = importlib.util.spec_from_file_location("check", RACINE / "scripts" / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


@pytest.mark.parametrize("code", [
    "p.read_text()", "p.write_text(x)", "open(f)", "open(f, 'w')", "p.open()",
    "subprocess.run(a, text=True)", "subprocess.run(a, universal_newlines=True)",
])
def test_le_controle_refuse_l_encodage_implicite(code):
    assert check.encodages_implicites(ast.parse(code))


@pytest.mark.parametrize("code", [
    "p.read_text('utf-8')", "p.read_text(encoding='utf-8')", "p.write_text(x, 'utf-8')",
    "p.write_text(x, encoding='utf-8')", "open(f, 'rb')", "p.open('wb')", "open(f, encoding='utf-8')",
    "subprocess.run(a, text=True, encoding='utf-8')", "subprocess.run(a, capture_output=True)",
    "subprocess.run(a, text=False)",
])
def test_le_controle_admet_l_encodage_explicite(code):
    assert not check.encodages_implicites(ast.parse(code))


def test_le_depot_est_conforme():
    assert check.encodages() == []


def test_les_tests_d_encodage_passent_sans_utf8_du_poste():
    """Poste non UTF-8 (cp1252 sous Windows) : les deux tests qui échangent du non-ASCII passent, et tout
    accès texte sans `encoding` est une erreur (EncodingWarning : détecte l'écart aussi sous Linux)."""
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252", "PYTHONWARNDEFAULTENCODING": "1"}
    cibles = ["tests/test_geste.py::test_point_de_restauration_git_puis_retour_arriere",
              "tests/test_mise_a_jour.py::test_modifications_locales_refusent_sans_rien_changer"]
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-W", "error::EncodingWarning", *cibles],
                       cwd=RACINE, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-2000:]
