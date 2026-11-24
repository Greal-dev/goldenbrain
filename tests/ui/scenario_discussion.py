"""Mode discussion (INV-DISCUSSION-1) : tâche ouverte en 1366×768, la conversation occupe l'essentiel de l'écran.

Mesure : surface du volet de conversation (fil + saisie) rapportée à celle de la fenêtre, objectif ≥ 70 %. Chaque volet reste à un geste.
Vault temporaire, harnais factice, contextes neufs (aucune disposition mémorisée).
"""
import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer


@pytest.fixture(scope="module", params=["fr", "de", "es"])
def srv(request, tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("discussion"), f'\n[interface]\nmode = "avance"\nlangue = "{request.param}"\n'):
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/causerie.md", univers.tache("Causer avec l'agent", "en-cours"))
        yield s


def ouvrir(navigateur, srv, w=1366, h=768, avant=""):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    if avant:
        ctx.add_init_script(avant)
    p = ctx.new_page()
    p.goto(srv.url + "/#t=causerie")
    p.wait_for_selector(".composer textarea", timeout=90000)
    p.ctx = ctx
    return p


def test_la_conversation_couvre_70_pour_cent_de_l_ecran(navigateur, srv):
    p = ouvrir(navigateur, srv)
    try:
        expect(p.locator("body")).to_have_class(__import__("re").compile("discussion"))
        p.wait_for_timeout(600)
        part = p.evaluate("""() => { const r = document.querySelector('.volet-t-conv').getBoundingClientRect();
            return r.width * r.height / (innerWidth * innerHeight) }""")
        assert part >= 0.70, f"conversation = {part:.0%} de l'écran"
        barre = p.evaluate("() => document.querySelector('.b-haut').getBoundingClientRect().height")
        assert barre <= 56, f"barre haute = {barre}px"
    finally:
        p.ctx.close()


def test_menu_rail_et_tout_afficher(navigateur, srv):
    p = ouvrir(navigateur, srv)
    try:
        # menu : jamais invisible, le clic le déroule et donne accès aux écrans
        p.click("#btn-menu")
        expect(p.locator("#btn-reglages")).to_be_visible()
        p.keyboard.press("Escape")
        expect(p.locator("#btn-reglages")).to_be_hidden()
        # rail : le clic épingle l'arbre
        expect(p.locator("#rail-arbre")).to_be_visible()
        p.click("#rail-arbre")
        expect(p.locator("body")).to_have_class(__import__("re").compile("arbre-epingle"))
        # tout afficher : disposition complète, mémorisée après rechargement
        p.keyboard.press("Alt+d")
        expect(p.locator("body")).not_to_have_class(__import__("re").compile(r"\bdiscussion\b"))
        p.reload()
        p.wait_for_selector(".composer textarea", timeout=90000)
        expect(p.locator("body")).not_to_have_class(__import__("re").compile(r"\bdiscussion\b"))
    finally:
        p.ctx.close()


def test_telephone_inchange(navigateur, srv):
    p = ouvrir(navigateur, srv, 390, 844)
    try:
        expect(p.locator("body")).not_to_have_class(__import__("re").compile(r"\bdiscussion\b"))
    finally:
        p.ctx.close()
