"""Lignes de tâche, nature et plafond (INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1) : ajouter, cocher, promouvoir une ligne ;
nature posée puis déduite ; réglage du plafond persisté ; 409 de rangement à la création au-delà du plafond."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_lignes_ajouter_cocher_promouvoir(page, serveur):
    projet(serveur, "C1-Lignes", {"li-mere": ("Chantier lignes", "")})
    charger(page)
    ligne(page, "Chantier lignes").click()
    expect(page.locator(".d-titre")).to_have_text("Chantier lignes")
    expect(page.locator("[data-id=lignes]")).to_be_visible()
    page.fill("[data-id=ligne-saisie]", "Relire le texte")
    page.press("[data-id=ligne-saisie]", "Enter")
    expect(page.locator(".lignes-liste li")).to_have_count(1)
    page.locator(".lignes-liste li input[type=checkbox]").check()
    expect(page.locator(".lignes-liste li.fait")).to_have_count(1)
    page.click("[data-promouvoir='0']")
    expect(page.locator(".d-titre")).to_have_text("Relire le texte")  # la tâche fille s'ouvre
    assert not page.erreurs, page.erreurs


def test_nature_posee_puis_auto(page, serveur):
    projet(serveur, "C1-Nature", {"na-un": ("Rédiger la stratégie de communication", "")})
    charger(page)
    ligne(page, "Rédiger la stratégie de communication").click()
    sel = page.locator("[data-id=sel-nature]")
    expect(sel).to_be_visible()
    sel.select_option("operation")
    expect(sel).to_have_value("operation")
    expect(page.locator(".ligne .nature[data-nature=operation]")).to_have_count(1)
    sel.select_option("")
    expect(page.locator(".ligne .nature[data-nature=pilotage]")).to_have_count(1)
    assert not page.erreurs, page.erreurs


def test_plafond_regle_et_rangement_propose(page, serveur):
    projet(serveur, "C1-Plafond", {"pl-a": ("Livrer le module a", ""), "pl-b": ("Livrer le module b", "")})
    reponse = page.request.put(page.url_serveur + "/api/rangement", headers=H, data={"plafond": 2, "natures_separees": True})
    assert reponse.ok and reponse.json()["plafond"] == 2
    try:
        cont = next(c["id"] for c in page.request.get(page.url_serveur + "/api/conteneurs").json() if c["titre"] == "Plafond")
        corps = {"titre": "Brancher le connecteur zéta", "description": "Un travail de code distinct.", "conteneur": cont}
        r = page.request.post(page.url_serveur + "/api/taches", headers=H, data=corps)
        assert r.status == 409 and r.json()["rangement"]["raison"] == "plafond"
        assert {p["geste"] for p in r.json()["rangement"]["propositions"]} >= {"nouveau_groupe"}
        assert page.request.post(page.url_serveur + "/api/taches", headers=H, data={**corps, "forcer": True}).ok
    finally:
        page.request.put(page.url_serveur + "/api/rangement", headers=H, data={"plafond": 10, "natures_separees": True})
