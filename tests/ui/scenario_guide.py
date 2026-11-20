"""Scénario « guide » (INV-GUIDE-1) : « ? » de l'en-tête, sommaire cliquable, recherche dans la page,
« ? » contextuel de Réglages qui mène à sa section, lien direct `#guide=<ancre>`."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger
from playwright.sync_api import expect


# Le titre de la section visée est dans la fenêtre (la fin du guide ne remonte pas jusqu'en haut).
VU = """(id) => { const e = document.getElementById(id); if (!e) return false;
    const r = e.getBoundingClientRect(); return r.top >= -2 && r.bottom <= innerHeight; }"""


def test_guide_ouvert_sommaire_recherche_et_aide_contextuelle(page, serveur):
    charger(page)
    page.locator("#btn-guide").click()
    expect(page.locator(".guide h2")).to_have_text("Guide")
    expect(page.locator("#guide-installer")).to_be_visible()
    assert page.url.endswith("#guide")

    page.locator(".guide-sommaire a", has_text="Dépannage").click()
    expect(page.locator("#guide-depannage")).to_be_visible()
    page.wait_for_function("() => location.hash === '#guide=depannage'")
    page.wait_for_function(VU, arg="guide-depannage")

    page.locator(".guide-recherche").fill("loginctl")
    expect(page.locator(".guide-section:visible")).to_have_count(1)
    expect(page.locator("#guide-service-au-demarrage-linux")).to_be_visible()

    page.locator("#btn-reglages").click()
    page.locator(".eq-tete .btn.aide").click()
    expect(page.locator("#guide-reglages")).to_be_visible()
    page.wait_for_function("() => location.hash === '#guide=reglages'")
    page.wait_for_function(VU, arg="guide-reglages")

    page.goto(page.url_serveur + "/#guide=telegram")
    expect(page.locator("#guide-telegram")).to_be_visible()
    page.wait_for_function(VU, arg="guide-telegram")
