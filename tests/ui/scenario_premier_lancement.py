"""Premier lancement sur un vault vide (audit L3) : état vide guidé, un seul parcours d'accueil, confirmation
avant la revue de cohérence, avertissement sur les agents sans confirmation. Serveur et vault à part (vide)."""

import shutil

import pytest
from playwright.sync_api import expect

from conftest import demarrer


@pytest.fixture
def vide(tmp_path_factory):
    gen = demarrer(tmp_path_factory.mktemp("vide"))
    s = next(gen)
    shutil.rmtree(s.vault)
    s.vault.mkdir()
    yield s
    gen.close()


@pytest.fixture
def page_vide(navigateur, vide):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    p = ctx.new_page()
    p.erreurs = []
    p.on("console", lambda m: p.erreurs.append(m.text) if m.type in ("error", "warning") else None)
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.url_serveur = vide.url
    yield p
    ctx.close()


def passer_plus_tard(page):
    page.goto(page.url_serveur)
    page.wait_for_selector('[data-id="premiers-pas"]')
    page.click('[data-id="pp-plus-tard"]')


def test_vault_vide_apres_plus_tard_propose_un_etat_vide_guide_et_non_un_chargement_permanent(page_vide):
    passer_plus_tard(page_vide)
    guide = page_vide.locator('[data-id="vide-guide"]')
    expect(guide).to_be_visible()
    assert "Chargement" not in page_vide.inner_text(".casc-defile")
    expect(page_vide.locator('[data-id="vide-creer"]')).to_be_visible()
    expect(page_vide.locator('[data-id="vide-importer"]')).to_be_visible()
    page_vide.click('[data-id="vide-importer"]')
    expect(page_vide.locator('[data-id="accueil"]')).to_be_visible()


def test_plus_tard_aux_premiers_pas_ne_chaine_pas_un_second_dialogue_de_bienvenue(page_vide):
    passer_plus_tard(page_vide)
    page_vide.wait_for_timeout(600)
    expect(page_vide.locator('[data-id="accueil"]')).to_have_count(0)
    expect(page_vide.locator('[data-id="premiers-pas"]')).to_have_count(0)


def test_revue_de_coherence_demande_confirmation_et_n_agit_pas_si_on_refuse(page_vide):
    passer_plus_tard(page_vide)
    messages = []
    page_vide.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
    appels = []
    page_vide.on("request", lambda r: appels.append(r.url) if r.method == "POST" and "jardinage" in r.url else None)
    page_vide.click("#btn-menu")  # barre d'une rangée sur tous les écrans : le geste est dans « Menu »
    page_vide.click("#btn-revue")
    page_vide.wait_for_timeout(400)
    assert messages and "quota" in messages[0]
    assert not appels


def test_premiere_tache_avertit_que_les_assistants_agissent_sans_confirmation(page_vide):
    passer_plus_tard(page_vide)
    page_vide.click('[data-id="vide-creer"]')
    expect(page_vide.locator("dialog .dlg-texte")).to_contain_text("sans vous demander confirmation")
