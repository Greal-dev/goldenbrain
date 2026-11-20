"""Scénarios du système visuel : thème choisi dans Réglages (persistant, retour au système), écran étroit utilisable
(un écran à la fois, voir aussi `scenario_telephone.py`)."""
from playwright.sync_api import expect


FOND = "getComputedStyle(document.body).backgroundColor"


def test_theme_sombre_choisi_persiste_puis_retour_au_systeme(navigateur, serveur):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, color_scheme="light")
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        page.goto(serveur.url + "/")
        page.wait_for_selector(".ligne")
        clair = page.evaluate(FOND)
        page.click("#btn-reglages")
        page.click("[data-id=theme-sombre]")
        assert page.get_attribute("html", "data-theme") == "sombre"
        sombre = page.evaluate(FOND)
        assert sombre != clair, sombre
        # Le choix survit au rechargement, appliqué avant le rendu (theme.js).
        page.reload()
        page.wait_for_selector(".ligne")
        assert page.evaluate(FOND) == sombre
        page.click("#btn-reglages")
        assert page.get_attribute("[data-id=theme-sombre]", "aria-pressed") == "true"
        page.click("[data-id=theme-systeme]")
        assert page.get_attribute("html", "data-theme") is None
        assert page.evaluate(FOND) == clair
        assert not erreurs, erreurs
    finally:
        ctx.close()


def test_ecran_etroit_une_colonne_sans_debordement(navigateur, serveur):
    ctx = navigateur.new_context(viewport={"width": 390, "height": 800})
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        page.goto(serveur.url + "/")
        page.wait_for_selector(".ligne")
        # Pas de largeur minimale de bureau : la page ne déborde pas de l'écran.
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        for sel in ("#btn-nouvelle", "#recherche", "#barre-basse [data-tel=reglages]"):
            boite = page.locator(sel).bounding_box()
            assert boite and boite["x"] >= 0 and boite["x"] + boite["width"] <= 391, (sel, boite)
        # Une colonne, un écran à la fois : l'arbre pleine largeur, puis les Réglages à sa place (barre basse).
        assert page.locator("#volet-gauche").bounding_box()["width"] > 380
        expect(page.locator("#volet-droit")).to_be_hidden()
        page.click("#barre-basse [data-tel=reglages]")
        page.wait_for_selector("[data-id=theme-sombre]")
        expect(page.locator("#volet-gauche")).to_be_hidden()
        assert not erreurs, erreurs
    finally:
        ctx.close()
