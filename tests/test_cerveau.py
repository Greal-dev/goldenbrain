"""Second cerveau d'un poste (INV-CERVEAU-1, INV-CERVEAU-2) : état propre au poste, examen d'un dossier, écriture de la seule
clé `[vault] racine`, routes sous la garde de l'accueil, redémarrage demandé au changement de dossier."""

import dataclasses
import os
import sys
import tomllib

import pytest
from fastapi.testclient import TestClient

from conftest import PORT
from orchestrateur import api, cerveau, installation
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from test_installation import Faux

H = {"X-Orchestrateur": "1"}
BASE = "/api/accueil/cerveau"


def test_etat_neuf_puis_herite_puis_pose(config):
    assert cerveau.etat(config)["etat"] == ""  # poste neuf : le parcours se propose, quel que soit le contenu du vault
    (config.donnees / "etat").mkdir(parents=True)
    (config.donnees / "etat" / "premiers-pas.json").write_text("{}", encoding="utf-8")
    assert cerveau.etat(config)["etat"] == "fait"  # installation déjà vécue : une mise à jour n'impose rien
    cerveau.poser(config, "differe")
    assert cerveau.etat(config)["etat"] == "differe"


def test_parcours_ouvert_selon_etat_et_vault(config):
    assert not cerveau.parcours_ouvert(config, True)  # poste neuf : le second cerveau passe avant tout
    cerveau.poser(config, "differe")
    assert not cerveau.parcours_ouvert(config, True)  # « plus tard » : un rappel, pas un écran
    cerveau.poser(config, "fait")
    assert cerveau.parcours_ouvert(config, True) and not cerveau.parcours_ouvert(config, False)
    cerveau.poser(config, "fait", parcours=True)
    assert cerveau.parcours_ouvert(config, False)  # vault existant choisi : accueil et premiers pas suivent


@pytest.mark.parametrize("avant", ["", "[serveur]\nport = 1\n", "[vault]\nracine = \"/a\"\ntaches = [\"x\"]\n[moteur]\nm = 1\n",
                                   "[vault]\ntaches = [\"x\"]\n"])
@pytest.mark.parametrize("racine", ["/srv/élodie/Mes notes", "D:\\Élodie Dupont\\Documents\\Mon \"vault\""])
def test_poser_racine_ne_touche_que_cette_cle(tmp_path, avant, racine):
    f = tmp_path / "config.toml"
    f.write_text(avant, encoding="utf-8")
    cerveau.poser_racine(f, racine)
    lu = tomllib.loads(f.read_text(encoding="utf-8"))
    assert lu["vault"]["racine"] == racine
    assert tomllib.loads(avant).get("serveur") == lu.get("serveur") and tomllib.loads(avant).get("vault", {}).get("taches") == lu["vault"].get("taches")
    assert tomllib.loads(avant).get("moteur") == lu.get("moteur")


def test_poser_racine_garde_les_fins_de_ligne_windows(tmp_path):
    f = tmp_path / "config.toml"
    f.write_bytes(b'[vault]\r\nracine = "/a"\r\n')
    cerveau.poser_racine(f, "/b")
    assert f.read_bytes() == b'[vault]\r\nracine = "/b"\r\n'


def test_examiner_dossier_absent_existant_fichier_et_relatif(config, tmp_path):
    neuf = cerveau.examiner(config, str(tmp_path / "Mes notes é" / "neuf"))
    assert neuf["ok"] and not neuf["existe"] and neuf["ecrivable"]
    garni = cerveau.examiner(config, str(config.vault.racine))
    assert garni["ok"] and garni["actuel"] and not garni["vide"] and garni["notes"] > 0
    (tmp_path / "vide").mkdir()
    assert cerveau.examiner(config, str(tmp_path / "vide"))["vide"] is True
    f = tmp_path / "fichier.md"
    f.write_text("x", encoding="utf-8")
    assert not cerveau.examiner(config, str(f))["ok"]
    with pytest.raises(Invalide):
        cerveau.examiner(config, "relatif/dossier")
    with pytest.raises(Invalide):
        cerveau.examiner(config, "  ")


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="droits POSIX, hors root")
def test_examiner_dossier_non_inscriptible(config, tmp_path):
    ferme = tmp_path / "ferme"
    ferme.mkdir()
    ferme.chmod(0o500)
    try:
        r = cerveau.examiner(config, str(ferme / "sous"))
        assert not r["ok"] and "ferme" in r["erreur"]
    finally:
        ferme.chmod(0o700)


def test_examiner_dossier_deja_servi_par_une_autre_instance(config, tmp_path, monkeypatch):
    from orchestrateur.__main__ import fichier_verrou, prendre_verrou
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    autre = tmp_path / "autre vault"
    autre.mkdir()
    tenu = prendre_verrou(fichier_verrou(autre), autre, 8300)
    try:
        r = cerveau.examiner(config, str(autre))
        assert not r["ok"] and r["occupe"] and "autre vault" in r["erreur"]
    finally:
        tenu.close()
    assert cerveau.examiner(config, str(autre))["ok"]


def test_lister_sous_dossiers_visibles_avec_espaces_et_accents(tmp_path):
    for n in ("Éléphant rose", "b", ".cache"):
        (tmp_path / n).mkdir()
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    r = cerveau.lister(str(tmp_path))
    assert [d["nom"] for d in r["dossiers"]] == ["b", "Éléphant rose"] and r["parent"] == str(tmp_path.parent)
    assert cerveau.lister("")["chemin"] == r["maison"]  # sans chemin : dossier personnel


@pytest.fixture
def client(config, vault, faux, monkeypatch, tmp_path):
    monkeypatch.setattr(installation, "Systeme", lambda: Faux())
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    toml = tmp_path / "config.toml"
    toml.write_text(f'[vault]\nracine = "{config.vault.racine.as_posix()}"\n', encoding="utf-8")
    config = dataclasses.replace(config, chemin=toml)
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    app.state.version.arreter = lambda: None
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        c.toml, c.cfg, c.app = toml, config, app
        yield c


def test_premier_lancement_se_propose_meme_sur_vault_garni_et_bloque_l_ancien_parcours(client):
    lu = client.get(BASE).json()
    assert lu["propose"] is True and lu["vide"] is False  # le vault de l'utilisateur est déjà là : on propose quand même
    assert client.get("/api/accueil").json()["propose"] is False
    assert client.get("/api/accueil/premiers-pas").json()["propose"] is False


def test_plus_tard_laisse_un_rappel_et_aucun_ecran(client):
    assert client.post(BASE + "/plus-tard", headers=H).json()["etat"] == "differe"
    lu = client.get(BASE).json()
    assert lu["propose"] is False and lu["rappel"] is True


def test_appliquer_meme_dossier_pas_de_redemarrage_et_rejoue_le_parcours(client):
    (client.cfg.donnees / "etat").mkdir(parents=True, exist_ok=True)
    (client.cfg.donnees / "etat" / "accueil.json").write_text('{"etat": "fait"}', encoding="utf-8")
    r = client.post(BASE + "/appliquer", json={"chemin": str(client.cfg.vault.racine)}, headers=H).json()
    assert r["redemarrage"] is False
    assert not (client.cfg.donnees / "etat" / "accueil.json").exists()  # le parcours se rejoue sur ce vault
    assert client.get(BASE).json() == {**client.get(BASE).json(), "propose": False, "rappel": False}
    assert client.get("/api/accueil").json()["propose"] is True  # vault existant, parcours ouvert


def test_appliquer_autre_dossier_cree_ecrit_la_cle_et_demande_le_redemarrage(client, tmp_path):
    appels = []
    client.app.state.version.arreter = lambda: appels.append(1)
    neuf = tmp_path / "Second cerveau é" / "notes"
    r = client.post(BASE + "/appliquer", json={"chemin": str(neuf), "creer": True}, headers=H)
    assert r.status_code == 200 and r.json()["redemarrage"] and neuf.is_dir()
    assert tomllib.loads(client.toml.read_text(encoding="utf-8"))["vault"]["racine"] == str(neuf)
    assert client.app.state.version.code_sortie == 3  # le lanceur relance le serveur sur le nouveau vault
    assert cerveau.etat(client.cfg)["etat"] == "fait" and cerveau.etat(client.cfg)["parcours"] is True


def test_appliquer_refuse_sans_rien_ecrire_dossier_absent_non_demande_ou_fichier(client, tmp_path):
    avant = client.toml.read_text(encoding="utf-8")
    absent = client.post(BASE + "/appliquer", json={"chemin": str(tmp_path / "absent")}, headers=H)
    assert absent.status_code == 400 and not (tmp_path / "absent").exists()
    f = tmp_path / "f"
    f.write_text("x", encoding="utf-8")
    assert client.post(BASE + "/appliquer", json={"chemin": str(f)}, headers=H).status_code == 400
    assert client.toml.read_text(encoding="utf-8") == avant and cerveau.etat(client.cfg)["etat"] == ""


def test_appliquer_refuse_un_dossier_servi_par_une_autre_instance(client, tmp_path):
    from orchestrateur.__main__ import fichier_verrou, prendre_verrou
    autre = tmp_path / "pris"
    autre.mkdir()
    tenu = prendre_verrou(fichier_verrou(autre), autre, 8300)
    try:
        r = client.post(BASE + "/appliquer", json={"chemin": str(autre)}, headers=H)
        assert r.status_code == 400 and "autre instance" in r.json()["detail"]
    finally:
        tenu.close()


def test_routes_du_selecteur(client, tmp_path):
    (tmp_path / "Mes notes").mkdir()
    r = client.post(BASE + "/dossiers", json={"chemin": str(tmp_path)}, headers=H).json()
    assert "Mes notes" in [d["nom"] for d in r["dossiers"]]
    assert client.post(BASE + "/dossiers", json={"chemin": str(tmp_path / "nul")}, headers=H).status_code == 400


def test_dossier_refuse_a_l_ecriture_meme_si_le_systeme_dit_oui(config, tmp_path, monkeypatch):
    # Sous Windows `os.access` ignore les droits réels : seul un essai d'écriture le dit (poste Windows, 24/11).
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root écrit partout")
    ferme = tmp_path / "Lecture seule"
    ferme.mkdir()
    ferme.chmod(0o555)
    monkeypatch.setattr(os, "access", lambda *a, **k: True)
    try:
        r = cerveau.examiner(config, str(ferme))
    finally:
        ferme.chmod(0o755)
    assert r["ecrivable"] is False and r["ok"] is False
    assert not any(ferme.iterdir())  # l'essai ne laisse aucun fichier
