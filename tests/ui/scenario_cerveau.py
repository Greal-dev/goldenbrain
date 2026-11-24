"""Premier lancement sur un poste neuf (INV-CERVEAU-1, INV-CERVEAU-2) : « Configurer votre second cerveau » ouvre l'interface en plein
écran avant tout autre écran, que le vault soit absent, vide ou déjà garni ; un vault situé ailleurs se choisit sans toucher
config.toml (sélecteur de dossier) et le serveur repart dessus ; « Plus tard » laisse un rappel ; Réglages rouvre le parcours."""

import shutil
import tomllib

import pytest
from playwright.sync_api import expect

from conftest import demarrer


def poste_neuf(tmp_path_factory, vault):
    gen = demarrer(tmp_path_factory.mktemp("neuf"), cerveau_fait=False)
    s = next(gen)
    if vault == "absent":
        shutil.rmtree(s.vault)
    elif vault == "vide":
        shutil.rmtree(s.vault)
        s.vault.mkdir()
    return gen, s


@pytest.fixture(params=["absent", "vide", "garni"])
def neuf(request, tmp_path_factory):
    gen, s = poste_neuf(tmp_path_factory, request.param)
    s.mode = request.param
    yield s
    gen.close()


@pytest.fixture
def garni(tmp_path_factory):
    gen, s = poste_neuf(tmp_path_factory, "garni")
    yield s
    gen.close()


def ouvrir(navigateur, s):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    p = ctx.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.url_serveur = s.url
    p.ctx = ctx
    return p


def test_premier_lancement_ouvre_le_second_cerveau_en_plein_ecran_avant_tout(navigateur, neuf):
    page = ouvrir(navigateur, neuf)
    page.goto(page.url_serveur)
    boite = page.locator('[data-id="cerveau"]')
    expect(boite).to_be_visible()
    assert boite.bounding_box() == {"x": 0, "y": 0, "width": 1366, "height": 768}  # plein écran
    expect(page.locator('[data-id="premiers-pas"]')).to_have_count(0)  # rien d'autre avant
    expect(page.locator('[data-id="accueil"]')).to_have_count(0)
    attendu = {"absent": "neuf", "vide": "vide", "garni": "existant"}[neuf.mode]
    expect(page.locator('[data-id="cerveau-verdict"]')).to_have_attribute("data-etat", attendu)
    page.click('[data-id="cerveau-continuer"]')  # même dossier : pas de redémarrage, la suite s'enchaîne
    expect(page.locator('[data-id="premiers-pas"]')).to_be_visible()
    if neuf.mode == "absent":
        assert neuf.vault.is_dir()  # créé à la validation, jamais avant
    assert not page.erreurs
    page.ctx.close()


def test_rien_n_est_cree_avant_la_validation(navigateur, tmp_path_factory):
    gen, s = poste_neuf(tmp_path_factory, "absent")
    page = ouvrir(navigateur, s)
    page.goto(page.url_serveur)
    page.wait_for_selector('[data-id="cerveau"]')
    assert not s.vault.exists()
    page.ctx.close()
    gen.close()


def test_vault_ailleurs_choisi_au_selecteur_serveur_redemarre_dessus(navigateur, garni, tmp_path_factory):
    ailleurs = tmp_path_factory.mktemp("Mon coffre Obsidian é") / "Notes perso"
    (ailleurs / ".obsidian").mkdir(parents=True)
    (ailleurs / "Idées.md").write_text("# Idées\n", encoding="utf-8")
    page = ouvrir(navigateur, garni)
    page.goto(page.url_serveur)
    page.wait_for_selector('[data-id="cerveau"]')
    page.click('[data-id="cerveau-parcourir"]')
    page.wait_for_selector('[data-id="cerveau-nav"]')
    page.fill('[data-id="cerveau-chemin"]', str(ailleurs))  # saisie directe, avec espaces et accents
    expect(page.locator('[data-id="cerveau-verdict"]')).to_contain_text("Obsidian")  # le verdict suit la saisie (le vault actuel n'en est pas un)
    page.click('[data-id="cerveau-continuer"]')
    expect(page.locator('[data-id="cerveau-redemarrage"]')).to_be_visible()
    assert garni.proc.wait(20) == 3  # code de redémarrage : le lanceur relance sur le nouveau vault
    assert tomllib.loads((garni.dossier / "config.toml").read_text(encoding="utf-8"))["vault"]["racine"] == str(ailleurs)
    assert (ailleurs / "Idées.md").read_text(encoding="utf-8") == "# Idées\n"  # repris en place, intact
    page.ctx.close()


def test_selecteur_navigue_dans_les_dossiers(navigateur, garni, tmp_path_factory):
    base = tmp_path_factory.mktemp("sel")
    (base / "Sous dossier é").mkdir()
    page = ouvrir(navigateur, garni)
    page.goto(page.url_serveur)
    page.fill('[data-id="cerveau-chemin"]', str(base))
    expect(page.locator('[data-id="cerveau-verdict"]')).to_have_attribute("data-etat", "vide")  # l'examen a eu lieu : « Parcourir » part de ce dossier
    page.click('[data-id="cerveau-parcourir"]')
    page.wait_for_selector('[data-dossier="Sous dossier é"]')
    page.click('[data-dossier="Sous dossier é"]')
    expect(page.locator('[data-id="cerveau-nav-chemin"]')).to_have_text(str(base / "Sous dossier é"))
    page.click('[data-id="cerveau-ici"]')
    expect(page.locator('[data-id="cerveau-chemin"]')).to_have_value(str(base / "Sous dossier é"))
    page.ctx.close()


def test_dossier_refuse_bloque_le_bouton_et_le_dit(navigateur, garni, tmp_path_factory):
    fichier = tmp_path_factory.mktemp("f") / "note.md"
    fichier.write_text("x", encoding="utf-8")
    page = ouvrir(navigateur, garni)
    page.goto(page.url_serveur)
    page.fill('[data-id="cerveau-chemin"]', str(fichier))
    expect(page.locator('[data-id="cerveau-verdict"]')).to_have_attribute("data-etat", "refus")
    expect(page.locator('[data-id="cerveau-continuer"]')).to_be_disabled()
    page.fill('[data-id="cerveau-chemin"]', "relatif/dossier")
    expect(page.locator('[data-id="cerveau-verdict"]')).to_contain_text("relatif/dossier")  # message propre au chemin relatif
    expect(page.locator('[data-id="cerveau-continuer"]')).to_be_disabled()
    page.ctx.close()


def test_plus_tard_laisse_un_rappel_visible_puis_reglages_rouvre(navigateur, garni):
    page = ouvrir(navigateur, garni)
    page.goto(page.url_serveur)
    page.click('[data-id="cerveau-plus-tard"]')
    expect(page.locator('[data-id="cerveau-rappel"]')).to_be_visible()
    page.reload()
    expect(page.locator('[data-id="cerveau"]')).to_have_count(0)  # plus d'écran : un rappel
    expect(page.locator('[data-id="cerveau-rappel"]')).to_be_visible()
    expect(page.locator('[data-id="premiers-pas"]')).to_have_count(0)
    page.click('[data-id="cerveau-configurer"]')
    expect(page.locator('[data-id="cerveau"]')).to_be_visible()
    page.ctx.close()


def test_reglages_propose_de_reconfigurer(page, serveur):
    page.goto(page.url_serveur + "/#reglages/cerveau")
    page.click('[data-id="reconfigurer-cerveau"]')
    expect(page.locator('[data-id="cerveau"]')).to_be_visible()
