"""Affichage par défaut « sobre éditorial » (INV-AFFICHAGE-1) : sans paramètre, barre haute sombre en clair comme en sombre,
ses menus au thème de la page, page claire ou sombre selon le thème ; budgets d'écran tenus au bureau et au téléphone
(en-tête ≤ 15 %, conversation ≥ 70 %, barre haute ≤ 56 px), focus visible, sans erreur.
Vault temporaire, harnais factice.
"""
import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer

BARRE = "rgb(28, 27, 25)"
FOND = {"clair": "rgb(255, 255, 255)", "sombre": "rgb(18, 18, 18)"}


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("affichage"), '\n[interface]\nmode = "avance"\nlangue = "fr"\n'):
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/essai.md", univers.tache("Préparer la réponse au dossier de consultation", "en-cours"))
        yield s


def ouvrir(navigateur, srv, theme, w=1366, h=768):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    ctx.add_init_script(f"localStorage.setItem('orch.theme', '{theme}')")
    p = ctx.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.goto(srv.url + "/#t=essai")
    p.wait_for_selector(".composer textarea", timeout=90000)
    p.ctx = ctx
    return p


def fond(p, sel):
    return p.evaluate(f"getComputedStyle(document.querySelector({sel!r})).backgroundColor")


@pytest.mark.parametrize("theme", ["clair", "sombre"])
@pytest.mark.parametrize("taille", [(1366, 768), (390, 844)])
def test_affichage_par_defaut_et_budgets(navigateur, srv, theme, taille):
    w, h = taille
    p = ouvrir(navigateur, srv, theme, w, h)
    try:
        assert fond(p, "#bandeau") == BARRE
        assert fond(p, "body") == FOND[theme]
        p.fill(".composer textarea", "Bonjour")
        p.press(".composer textarea", "Control+Enter")
        expect(p.locator(".msg.agent.final")).to_be_visible(timeout=20000)
        p.wait_for_timeout(600)
        haut = p.evaluate("""() => document.querySelector('.conv-tete').getBoundingClientRect().bottom
            - document.querySelector('#volet-droit').getBoundingClientRect().top""")
        assert haut <= 0.15 * h, f"{theme} {w}x{h} : {haut:.0f} px au-dessus du fil"
        if w > 900:
            part = p.evaluate("""() => { const r = document.querySelector('.volet-t-conv').getBoundingClientRect();
                return r.width * r.height / (innerWidth * innerHeight) }""")
            assert part >= 0.70, f"{theme} : conversation = {part:.0%} de l'écran"
            assert p.evaluate("() => document.querySelector('.b-haut').getBoundingClientRect().height") <= 56
        # Le menu déroulant de la barre retrouve le thème de la page.
        p.fill("#recherche", "Préparer")
        expect(p.locator("#rech-liste")).to_be_visible(timeout=10000)
        assert p.evaluate("getComputedStyle(document.querySelector('#rech-liste')).colorScheme") == ("light" if theme == "clair" else "dark")
        p.keyboard.press("Escape")
        # Focus visible : un contour non nul au clavier.
        p.focus(".composer textarea")
        p.keyboard.press("Shift+Tab")
        p.keyboard.press("Tab")
        assert p.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
        assert not p.erreurs, p.erreurs
    finally:
        p.ctx.close()
