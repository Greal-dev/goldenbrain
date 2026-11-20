"""Scénario de la page Réglages regroupée (INV-REGLAGES-1) : sections repliables mémorisées, résumé d'état dans chaque
titre, ancre #reglages/<section> qui l'ouvre, recherche qui ouvre la section concernée, saisie conservée au redessin."""
import re

from playwright.sync_api import expect

GROUPES = "details.rg-groupe"
# Mêmes modules que l'application (même adresse) : émettre ici, c'est émettre dans l'application.
EMETTRE = "(nom) => import('./store.js').then((m) => m.emit(nom))"


def ouverts(page):
    return page.eval_on_selector_all(f"{GROUPES}[open]", "l => l.map(d => d.dataset.groupe)")


def test_sections_repliables_memorisees_et_resumes(page, serveur):
    page.goto(page.url_serveur + "/#reglages")
    page.wait_for_selector(GROUPES)
    assert ouverts(page) == ["affichage"]  # la première seule, par défaut
    expect(page.locator("[data-id=sim-nombre], [data-id=sim-marge], [data-id=sim-plafond-valeur]").first).to_be_hidden()
    # Résumé d'une ligne, sans ouvrir le groupe.
    expect(page.locator("[data-resume=fonctions]")).to_have_text(re.compile(r"^\d+ sur 8 affichées$"))
    expect(page.locator("[data-resume=validation]")).to_have_text("Montrer : je valide chacune")
    expect(page.locator("[data-resume=agents]")).to_have_text(re.compile(r"agents? au plus|ajusté|plafond"))
    expect(page.locator("[data-resume=connexions]")).to_contain_text("Telegram")
    page.click("[data-groupe=agents] > summary")
    expect(page.locator("[data-ancre=simultanes]")).to_be_visible()
    page.reload()
    page.wait_for_selector(GROUPES)
    assert ouverts(page) == ["affichage", "agents"]  # choix du visiteur gardé d'une visite à l'autre


def test_ancre_ouvre_la_section_et_la_recherche_aussi(page, serveur):
    page.goto(page.url_serveur + "/#reglages/telegram")
    expect(page.locator("[data-id=telegram]")).to_be_visible()
    assert "connexions" in ouverts(page)
    assert page.evaluate("location.hash") == "#reglages/telegram"
    # Depuis un autre écran, l'ancre ouvre aussi la section.
    page.evaluate("location.hash = '#decisions'")
    page.evaluate("location.hash = '#reglages/compactage'")
    expect(page.locator("[data-id=cp-pct]")).to_be_visible()
    page.fill("[data-id=rg-chercher]", "mémoire")
    expect(page.locator("[data-groupe=agents]")).to_have_attribute("open", "")
    expect(page.locator("[data-groupe=validation]")).to_be_hidden()
    page.fill("[data-id=rg-chercher]", "zzzz introuvable")
    expect(page.locator("[data-id=rg-aucun]")).to_be_visible()
    page.fill("[data-id=rg-chercher]", "")
    expect(page.locator("[data-groupe=validation]")).to_be_visible()


def test_saisie_et_sections_conservees_au_redessin(page, serveur):
    page.goto(page.url_serveur + "/#reglages/executeurs")
    page.wait_for_selector("[data-id=executeurs] [data-id=exe-liste]")
    page.fill("[data-id=exe-nom]", "pc-en-cours")
    for _ in range(5):  # un agent qui parle émet 'etat' à chaque ligne
        page.evaluate(EMETTRE, "etat")
    assert page.input_value("[data-id=exe-nom]") == "pc-en-cours"
    assert page.evaluate("document.activeElement.dataset.id") == "exe-nom"
    # Redessin complet (changement de mode ou de fonction) : recherche, focus et sections ouvertes gardés.
    page.fill("[data-id=rg-chercher]", "tele")
    page.evaluate(EMETTRE, "interface")
    expect(page.locator("[data-id=rg-chercher]")).to_have_value("tele")
    assert page.evaluate("document.activeElement.dataset.id") == "rg-chercher"
    expect(page.locator("[data-groupe=connexions]")).to_have_attribute("open", "")
    assert not page.erreurs, page.erreurs
