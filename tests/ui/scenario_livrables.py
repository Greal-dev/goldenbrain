"""Livrables (INV-LIVRABLES-1, INV-DETAIL-1) : pastille unique de l'en-tête, volet, déclaration, attendu, agrégation chez un parent, filtre."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_livrables_declarer_attendre_et_agreger(page, serveur):
    projet(serveur, "C1-Livrables", {"lv-mere": ("Mère livrables", ""), "lv-fille": ("Fille livrables", "parent: lv-mere\n")})
    charger(page)
    ligne(page, "Mère livrables").click()
    expect(page.locator(".d-titre")).to_have_text("Mère livrables")
    expect(page.locator("[data-id=livrables-pastille]")).to_have_count(1)  # une seule pastille dans l'en-tête
    r = page.request.post(page.url_serveur + "/api/taches/lv-fille/livrables", headers=H,
                          data={"cible": "commit:abc1234", "titre": "Correctif fille"})
    assert r.status == 201, r.text()
    page.click("[data-id=livrables-pastille]")
    zone = page.locator("[data-id=livrables]")
    expect(zone).to_contain_text("Correctif fille")  # agrégé depuis la fille, groupé par tâche d'origine
    page.fill("[data-id=liv-cible]", "https://exemple.org/page")
    page.fill("[data-id=liv-titre]", "Page publiée")
    page.click("[data-id=liv-ajouter]")
    expect(zone).to_contain_text("Page publiée")
    page.fill("[data-id=liv-attendu]", "Rapport final")
    page.click("[data-id=liv-annoncer]")
    expect(zone.locator(".liv-att")).to_have_count(1)
    page.select_option("[data-id=liv-filtre-type]", "commit")
    expect(zone).to_contain_text("Correctif fille")
    expect(zone).not_to_contain_text("Page publiée")
    assert not page.erreurs, page.erreurs
