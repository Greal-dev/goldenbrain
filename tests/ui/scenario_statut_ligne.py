"""Scénario « changer le statut depuis les listes » : menu sur la pastille de l'arbre et de la cascade, sans ouvrir
la tâche, statut verrouillé inerte, refus en clair sur la ligne, annulation, usage au clavier."""

import re

import aides_arbre
import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, rang
from playwright.sync_api import expect


def poser(serveur):
    aides_arbre._ECRITS.append(serveur.vault / "Projets" / "C1-StatutLigne")
    univers.ecrire(serveur.vault, "Projets/C1-StatutLigne/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: StatutLigne\n---\n")
    for f, titre, extra in [("sl-a", "Alpha Statut", ""), ("sl-b", "Beta Statut", ""),
                            ("sl-c", "Gamma Statut", "paperclip: x\n")]:
        univers.ecrire(serveur.vault, f"Projets/C1-StatutLigne/taches/{f}.md", univers.tache(titre, extra=extra))


def test_changer_le_statut_depuis_l_arbre_annuler_et_clavier(page, serveur):
    poser(serveur)
    charger(page)
    pastille = ligne(page, "Alpha Statut").locator(".st-chg")
    expect(pastille).to_have_attribute("aria-label", "Statut : Non commencée. Changer le statut de « Alpha Statut »")
    # Clic : menu ; choix « En cours » ; la tâche n'est pas ouverte ; la ligne suit sans rechargement.
    pastille.click()
    menu = page.locator(".menu-statut")
    expect(menu).to_be_visible()
    assert menu.locator(".ms-item").all_inner_texts()[0:3] == ["Non commencée", "En cours", "Abandonnée"]  # même ordre que le détail
    menu.get_by_role("menuitemradio", name="En cours").click()
    expect(ligne(page, "Alpha Statut").locator(".badge-st")).to_have_text("en cours")
    expect(page.locator("#arbre .ligne.sel")).to_have_count(0)
    # Bandeau d'annulation : retour à l'état précédent.
    expect(page.locator(".annul-statut")).to_contain_text("Statut changé")
    page.locator(".annul-statut").get_by_role("button", name="Annuler").click()
    expect(ligne(page, "Alpha Statut").locator(".badge-st")).to_have_text("à faire")
    page.wait_for_timeout(1200)  # laisse passer les relectures différées de l arbre (sous charge, elles volent le focus)
    # Clavier : Entrée ouvre, flèche bas descend, Entrée choisit ; Échap ferme sans changer.
    beta = ligne(page, "Beta Statut").locator(".st-chg")
    beta.focus()
    expect(beta).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator(".menu-statut")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(".menu-statut")).to_have_count(0)
    expect(beta).to_be_focused()  # Échap rend le focus à la pastille
    page.keyboard.press("Space")
    expect(page.locator(".menu-statut .ms-item").first).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(page.locator(".menu-statut .ms-item").nth(1)).to_be_focused()
    page.keyboard.press("Enter")
    expect(ligne(page, "Beta Statut").locator(".badge-st")).to_have_text("en cours")


def test_statut_verrouille_inerte_et_refus_affiche_sur_la_ligne(page, serveur):
    poser(serveur)
    charger(page)
    verrouille = ligne(page, "Gamma Statut").locator(".st-chg")
    expect(verrouille).to_have_attribute("aria-disabled", "true")
    verrouille.click(force=True)  # aria-disabled : Playwright le tient pour inactif
    expect(page.locator(".menu-statut")).to_have_count(0)
    # Refus du serveur : message en clair sur la ligne, statut inchangé.
    page.route(re.compile(r"/api/taches/.+/statut$"), lambda r: r.fulfill(status=409, content_type="application/json",
                                                             body='{"detail": "refus de test"}'))
    ligne(page, "Alpha Statut").locator(".st-chg").click()
    page.locator(".menu-statut").get_by_role("menuitemradio", name="En cours").click()
    expect(ligne(page, "Alpha Statut").locator(".st-refus")).to_have_text("refus de test")
    expect(ligne(page, "Alpha Statut").locator(".badge-st")).to_have_text("à faire")


def test_changer_le_statut_depuis_la_cascade(page, serveur):
    poser(serveur)
    charger(page)
    page.locator("#arbre .ligne.t-conteneur .titre", has_text="StatutLigne").click()
    cible = rang(page, "Beta Statut")
    cible.locator(".st-chg").click()
    page.locator(".menu-statut").get_by_role("menuitemradio", name="Bloquée").click()
    expect(rang(page, "Beta Statut").locator(".c-st")).to_contain_text("Bloquée")
    expect(page.locator(".d-titre")).to_have_count(0)  # la tâche n'a pas été ouverte
