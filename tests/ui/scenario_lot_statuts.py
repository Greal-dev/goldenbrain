"""Scénario « filtre de statut partagé et changement en bloc » : mêmes pastilles dans le volet et la vue principale,
adresse partageable, « n sur N », cases à cocher, Maj+clic, confirmation avec récapitulatif, annulation."""

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

TACHES = {"lo-a": ("Une Lot", ""), "lo-b": ("Deux Lot", ""), "lo-c": ("Trois Lot", ""), "lo-d": ("Quatre Lot", "")}


def _poser(serveur):
    projet(serveur, "C1-LotStatuts", TACHES)
    univers.ecrire(serveur.vault, "Projets/C1-LotStatuts/taches/lo-e.md", univers.tache("Cinq Lot", statut="bloque"))


def _vue(page):
    ligne(page, "LotStatuts").click()
    expect(page.locator(".casc-titre")).to_have_text("LotStatuts")


def test_filtre_statut_partage_et_adresse(page, serveur):
    _poser(serveur)
    charger(page)
    _vue(page)
    page.click("#btn-statuts")  # INV-DEROULANT-1
    page.locator(".chip-st", has_text="bloquée").click()
    expect(page.locator(".casc-nsurn")).to_contain_text("1 sur")
    page.click("#btn-filtres")  # le volet reflète le même choix
    expect(page.locator('.f-st[data-statut="bloque"]')).to_have_attribute("aria-pressed", "true")
    assert "st=bloque" in page.url
    page.reload()  # mémorisé et lisible dans l'adresse
    page.wait_for_selector("#arbre .ligne")
    assert "st=bloque" in page.url
    page.click("#btn-filtres")
    page.locator("#f-st-raz").click()
    assert "st=" not in page.url


def test_changement_en_bloc_confirme_puis_annule(page, serveur):
    _poser(serveur)
    charger(page)
    _vue(page)
    cases = page.locator(".casc-corps .cl:not(.ctx) .c-sel")
    cases.nth(0).click()
    cases.nth(2).click(modifiers=["Shift"])  # étendue : trois tâches cochées
    expect(page.locator(".lot-n")).to_have_text("3 tâches sélectionnées")
    page.select_option("#lot-statut", "bloque")
    page.locator("#lot-appliquer").click()
    expect(page.locator("#lot-recap")).to_contain_text("3 tâches")
    page.locator("#lot-confirmer").click()
    expect(page.locator(".lot-etat")).to_have_text("3 tâches modifiées")
    expect(page.locator(".casc-corps .cl:not(.ctx) .c-st", has_text="Bloqu")).to_have_count(4)
    page.locator("#lot-annuler").click()
    expect(page.locator(".lot-etat")).to_have_text("Changement annulé.")
    expect(page.locator(".casc-corps .cl:not(.ctx) .c-st", has_text="Bloqu")).to_have_count(1)
    assert not page.erreurs, page.erreurs
