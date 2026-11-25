"""Directions visuelles d'essai (INV-DIRECTION-1) : ?theme=a|b|c charge sa feuille, la page par défaut n'en charge aucune,
et chaque direction tient les budgets d'écran (en-tête ≤ 15 %, conversation ≥ 70 %, barre haute ≤ 56 px), sans erreur.
Vault temporaire, harnais factice.
"""
import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer

DIRECTIONS = ("a", "b", "c")
FEUILLES = "() => [...document.styleSheets].map(s => s.href || '').filter(h => h.includes('directions/'))"


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("directions"), '\n[interface]\nmode = "avance"\nlangue = "fr"\n'):
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/essai.md", univers.tache("Préparer la réponse au dossier de consultation", "en-cours"))
        yield s


def ouvrir(navigateur, srv, requete, w=1366, h=768, ancre="#t=essai"):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    p = ctx.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.goto(srv.url + "/" + requete + ancre)
    p.wait_for_selector(".composer textarea", timeout=90000)
    p.ctx = ctx
    return p


def test_sans_parametre_aucune_direction(navigateur, srv):
    p = ouvrir(navigateur, srv, "")
    try:
        assert p.evaluate("document.documentElement.dataset.direction") is None
        assert p.evaluate(FEUILLES) == []
        p.goto(srv.url + "/?theme=z#t=essai")  # valeur inconnue : ignorée
        p.wait_for_selector(".composer textarea")
        assert p.evaluate(FEUILLES) == []
    finally:
        p.ctx.close()


@pytest.mark.parametrize("d", DIRECTIONS)
@pytest.mark.parametrize("taille", [(1366, 768), (390, 844)])
def test_direction_chargee_et_budgets_tenus(navigateur, srv, d, taille):
    w, h = taille
    p = ouvrir(navigateur, srv, f"?theme={d}", w, h)
    try:
        assert p.evaluate("document.documentElement.dataset.direction") == d
        assert len(p.evaluate(FEUILLES)) == 1
        # L'ancre change, le paramètre d'essai demeure : la direction suit la navigation.
        p.evaluate("location.hash = '#decisions'")
        assert f"theme={d}" in p.url
        p.evaluate("location.hash = '#t=essai'")
        p.wait_for_selector(".composer textarea")
        p.fill(".composer textarea", "Bonjour")
        p.press(".composer textarea", "Control+Enter")
        expect(p.locator(".msg.agent.final")).to_be_visible(timeout=20000)
        p.wait_for_timeout(600)
        haut = p.evaluate("""() => document.querySelector('.conv-tete').getBoundingClientRect().bottom
            - document.querySelector('#volet-droit').getBoundingClientRect().top""")
        assert haut <= 0.15 * h, f"{d} {w}x{h} : {haut:.0f} px au-dessus du fil"
        if w > 900:
            part = p.evaluate("""() => { const r = document.querySelector('.volet-t-conv').getBoundingClientRect();
                return r.width * r.height / (innerWidth * innerHeight) }""")
            assert part >= 0.70, f"{d} : conversation = {part:.0%} de l'écran"
            assert p.evaluate("() => document.querySelector('.b-haut').getBoundingClientRect().height") <= 56
        # Focus visible : un contour non nul au clavier.
        p.focus(".composer textarea")
        p.keyboard.press("Shift+Tab")
        p.keyboard.press("Tab")
        assert p.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
        assert not p.erreurs, p.erreurs
    finally:
        p.ctx.close()
