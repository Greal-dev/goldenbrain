"""Palette de commandes Ctrl+K : ouverture partout (même depuis un champ), recherche d'une tâche, geste de statut, fermeture."""

from aides_arbre import nettoyer_vault, projet  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def _charger(page, serveur):
    projet(serveur, "C1-Palette", {"pal-a": ("Quasimodo Cloche", ""), "pal-b": ("Gargouille Pierre", "")})
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")


def test_palette_ouvre_cherche_ouvre_la_fiche_et_change_le_statut(page, serveur):
    _charger(page, serveur)
    palette = page.locator("dialog#palette")
    page.keyboard.press("Control+k")
    expect(palette).to_be_visible()
    expect(palette.locator("[data-id=palette-commande]").first).to_be_visible()  # sans texte : les commandes

    page.keyboard.type("quasimodo")
    expect(palette.locator("[data-id=palette-tache]").first).to_contain_text("Quasimodo Cloche")
    expect(palette.locator("[data-id=palette-tache]")).to_have_count(1)
    page.keyboard.press("Enter")
    expect(palette).not_to_be_visible()
    expect(page.locator(".d-titre")).to_contain_text("Quasimodo Cloche")

    page.keyboard.press("Control+k")
    page.keyboard.type("statut")
    expect(palette.locator("[data-id=palette-commande]").first).to_contain_text("Statut")  # la liste suit la frappe
    palette.locator("[data-id=palette-commande]").first.click()  # première transition proposée depuis « à faire »
    for _ in range(50):
        if page.request.get(serveur.url + "/api/taches/pal-a", headers=H).json()["statut"] != "a-faire":
            break
        page.wait_for_timeout(100)
    assert page.request.get(serveur.url + "/api/taches/pal-a", headers=H).json()["statut"] == "en-cours"
    assert not page.erreurs, page.erreurs


def test_palette_s_ouvre_depuis_un_champ_texte_et_echap_ferme(page, serveur):
    _charger(page, serveur)
    page.focus("#recherche")
    page.keyboard.press("Control+k")
    palette = page.locator("dialog#palette")
    expect(palette).to_be_visible()
    page.keyboard.type("gargouille")
    expect(palette.locator("[data-id=palette-tache]")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(palette).not_to_be_visible()
    assert not page.erreurs, page.erreurs
