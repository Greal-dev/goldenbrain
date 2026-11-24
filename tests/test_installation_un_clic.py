"""Installation « un clic » (INV-PAQUET-1, INV-PAQUET-2) : composants épinglés et vérifiables,
lanceur qui recopie la graine sans jamais écraser la copie de l'utilisateur, lanceur Windows qui
lit le bon port, icônes. Rien n'est téléchargé, aucun vrai serveur : Python et navigateur factices."""

import os
import re
import shutil
import subprocess
import sys
import types
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
INSTALLATION = RACINE / "installation"
sys.path.insert(0, str(RACINE / "scripts"))
sys.path.insert(0, str(INSTALLATION))

import construction  # noqa: E402
import deja_lance  # noqa: E402
import langue  # noqa: E402

CLES = {"python-linux-x86_64", "python-linux-aarch64", "python-macos-arm64", "python-macos-x86_64",
        "python-windows-x86_64", "mingit-windows-x86_64", "innosetup"}


def test_chaque_composant_telecharge_porte_une_empreinte_sha256():
    # INV-PAQUET-2 : une adresse sans empreinte valide serait installée sans contrôle.
    table = construction.composants()
    assert set(table) == CLES
    for url, empreinte in table.values():
        assert url.startswith("https://")
        assert re.fullmatch(r"[0-9a-f]{64}", empreinte)


def test_dependances_toutes_epinglees():
    lignes = [ligne.split(";")[0].strip() for ligne in
              (INSTALLATION / "contraintes.txt").read_text(encoding="utf-8").splitlines()
              if ligne.strip() and not ligne.startswith("#")]
    noms = {ligne.split("==")[0].lower() for ligne in lignes}
    assert all("==" in ligne for ligne in lignes)
    assert {"fastapi", "uvicorn", "pyyaml"} <= noms


def test_telechargement_refuse_si_empreinte_differente(tmp_path, monkeypatch):
    monkeypatch.setenv("GB_CACHE", str(tmp_path))
    url, _ = construction.composants()["innosetup"]
    (tmp_path / url.rsplit("/", 1)[-1]).write_bytes(b"altere")
    monkeypatch.setattr(construction.urllib.request, "urlopen",
                        lambda *a, **k: open(os.devnull, "rb"))  # « téléchargement » vide, donc faux
    with pytest.raises(construction.ErreurConstruction):
        construction.telecharger("innosetup")


@pytest.fixture
def lanceur(tmp_path):
    """Graine factice, Python factice (« le serveur répond » : code 0), navigateur qui note l'adresse."""
    if shutil.which("sh") is None:
        pytest.skip("sh absent")
    graine = tmp_path / "graine"
    graine.mkdir()
    (graine / "lancer.sh").write_text("exit 9\n", encoding="utf-8")
    (graine / "marque").write_text("graine\n", encoding="utf-8")
    faux_py = tmp_path / "python3"
    faux_py.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    faux_py.chmod(0o755)
    nav = tmp_path / "nav"
    nav.write_text(f'#!/bin/sh\necho "$1" >> "{tmp_path}/ouvert"\n', encoding="utf-8")
    nav.chmod(0o755)
    def lancer():
        # Environnement lu à l'appel : un test peut régler la langue du système avant de lancer.
        env = {**os.environ, "GB_DONNEES": str(tmp_path / "donnees"), "GB_GRAINE": str(graine),
               "GB_PYTHON": str(faux_py), "GB_NAVIGATEUR": str(nav)}
        env.pop("ORCH_CONFIG", None)
        return subprocess.run(["sh", str(INSTALLATION / "goldenbrain.sh")], env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
    return lancer, tmp_path


def test_premier_lancement_recopie_la_graine_et_designe_le_python_embarque(lanceur):
    lancer, t = lanceur
    r = lancer()
    assert r.returncode == 0, r.stderr
    app = t / "donnees" / "app"
    assert (app / "marque").read_text(encoding="utf-8") == "graine\n"
    assert (app / "python.local").read_text(encoding="utf-8").strip() == str(t / "python3")
    assert "http://127.0.0.1:8300" in r.stdout


def test_lancement_ne_remplace_jamais_la_copie_existante(lanceur):
    # INV-PAQUET-1 : la copie de l'utilisateur porte ses mises à jour et ses réglages.
    lancer, t = lanceur
    app = t / "donnees" / "app"
    app.mkdir(parents=True)
    (app / "marque").write_text("copie de l'utilisateur\n", encoding="utf-8")
    (app / "config.toml").write_text("[serveur]\nport = 8399\n", encoding="utf-8")
    assert lancer().returncode == 0
    assert (app / "marque").read_text(encoding="utf-8") == "copie de l'utilisateur\n"
    for _ in range(50):  # le navigateur est lancé en arrière-plan
        if (t / "ouvert").exists():
            break
        time.sleep(0.1)
    assert (t / "ouvert").read_text(encoding="utf-8").strip() == "http://127.0.0.1:8399"


def test_lanceur_windows_lit_le_port_de_la_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("ORCH_CONFIG", raising=False)
    assert deja_lance.port(tmp_path) == 8300
    (tmp_path / "config.toml").write_text("[serveur]\nport = 8411\n", encoding="utf-8")
    assert deja_lance.port(tmp_path) == 8411
    autre = tmp_path / "autre.toml"
    autre.write_text("[serveur]\nport = 8412\n", encoding="utf-8")
    monkeypatch.setenv("ORCH_CONFIG", str(autre))
    assert deja_lance.port(tmp_path) == 8412


def test_icones_windows_et_macos_embarquent_le_png(tmp_path):
    png = RACINE / "web" / "icone-512.png"
    construction.ico(png, tmp_path / "a.ico")
    construction.icns(png, tmp_path / "a.icns")
    ico, icns = (tmp_path / "a.ico").read_bytes(), (tmp_path / "a.icns").read_bytes()
    assert ico[:4] == b"\0\0\1\0" and ico[22:] == png.read_bytes()
    assert icns[:4] == b"icns" and int.from_bytes(icns[4:8], "big") == len(icns)
    assert icns[8:12] == b"ic09"


def test_lanceur_windows_copie_aussi_le_dossier_git_cache():
    # Essai sous wine du 2026-11-19 : sans /H, .git (caché) manquerait et la mise à jour serait impossible.
    texte = (INSTALLATION / "GoldenBrain.cmd").read_text(encoding="utf-8")
    assert re.search(r"^xcopy .* /H ", texte, re.M)
    assert texte.isascii()


@pytest.mark.parametrize("valeur, code", [("de_DE.UTF-8", "de"), ("es_ES.UTF-8", "es"), ("fr_CA.UTF-8", "fr"),
                                          ("it_IT.UTF-8", "en"), ("C", "en"), ("", "en")])
def test_langue_du_systeme_quatre_langues_anglais_sinon(monkeypatch, valeur, code):
    for nom in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv("LANG", valeur)
    # Windows lit la langue d'affichage du système, pas LANG : on exerce ici la branche POSIX.
    monkeypatch.setattr(langue, "sys", types.SimpleNamespace(platform="linux"))
    assert langue.code_systeme() == code


def _app_avec_langue(dossier: Path, connue: bool) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "config.depart.toml").write_text("# départ\n[interface]\nmode = \"simple\"\n", encoding="utf-8")
    (dossier / "config.exemple.toml").write_text('# langue = "fr"\n' if connue else "[interface]\n", encoding="utf-8")
    return dossier


def test_premier_lancement_ecrit_la_langue_seulement_si_la_version_la_connait(tmp_path, monkeypatch):
    # Une clé inconnue empêcherait GoldenBrain de démarrer : rien n'est écrit tant qu'elle n'existe pas.
    monkeypatch.delenv("ORCH_CONFIG", raising=False)
    ancienne = _app_avec_langue(tmp_path / "ancienne", connue=False)
    langue.ecrire_config(ancienne, "de")
    assert not (ancienne / "config.toml").exists()
    neuve = _app_avec_langue(tmp_path / "neuve", connue=True)
    langue.ecrire_config(neuve, "de")
    assert (neuve / "config.toml").read_text(encoding="utf-8") == \
        '# départ\n[interface]\nlangue = "de"\nmode = "simple"\n'
    (neuve / "config.toml").write_text("[serveur]\nport = 8399\n", encoding="utf-8")
    langue.ecrire_config(neuve, "es")  # INV-PAQUET-1 : les réglages de l'utilisateur ne sont jamais réécrits
    assert (neuve / "config.toml").read_text(encoding="utf-8") == "[serveur]\nport = 8399\n"


def test_lanceur_parle_la_langue_du_systeme_et_la_reporte_dans_la_configuration(lanceur, monkeypatch):
    lancer, t = lanceur
    _app_avec_langue(t / "graine", connue=True)
    for nom in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    r = lancer()
    assert r.returncode == 0, r.stderr
    assert "GoldenBrain: primera instalación en" in r.stdout
    assert 'langue = "es"' in (t / "donnees" / "app" / "config.toml").read_text(encoding="utf-8")


def test_controle_refuse_le_chemin_du_poste_dans_un_shebang_un_pyc_ou_un_nom(tmp_path):
    for nom, donnees in (("bin/outil", b"#!" + str(construction.RACINE).encode() + b"/python\n"),
                         ("lib/__pycache__/x.cpython-312.pyc", b"\0" + str(construction.RACINE).encode() + b"/lib/x.py"),
                         ("lib/autre.txt", b"dans " + str(Path.home()).encode())):
        fichier = tmp_path / nom
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_bytes(donnees)
    with pytest.raises(construction.ErreurConstruction) as e:
        construction.controler_propre(tmp_path)
    message = str(e.value)
    assert "shebang" in message and "bytecode" in message and "bin/outil" in message
    assert str(construction.RACINE) not in message and str(Path.home()) not in message  # jamais la valeur


def test_controle_accepte_un_arbre_propre_et_scanne_aussi_un_zip(tmp_path, monkeypatch):
    import zipfile
    (tmp_path / "ok.pyc").write_bytes(b"/opt/goldenbrain/python/lib/x.py")
    construction.controler_propre(tmp_path)
    monkeypatch.setattr(construction, "CONSTRUCTION", tmp_path)
    sale = tmp_path / "sale.zip"
    with zipfile.ZipFile(sale, "w") as z:
        z.writestr("App/bin/uvicorn", "#!" + str(construction.RACINE) + "/python\n")
    with pytest.raises(construction.ErreurConstruction):
        construction.controler_artefact(sale)
    propre = tmp_path / "propre.zip"
    with zipfile.ZipFile(propre, "w") as z:
        z.writestr("App/bin/uvicorn", "#!/usr/bin/env python3\n")
    construction.controler_artefact(propre)
