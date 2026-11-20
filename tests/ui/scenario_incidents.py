"""Scénario des incidents (INV-INCIDENT-1) : un tour échoue sur quota épuisé ; la conversation de la tâche montre la
cause, ce que GoldenBrain a fait et le geste proposé ; le panneau « Incidents » liste l'incident et la jauge du compte."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def test_quota_epuise_cause_visible_dans_la_tache_et_le_panneau(page, serveur):
    projet(serveur, "C1-Incidents", {"inc-agent": ("Agent sans quota", "")})
    charger(page)
    ligne(page, "Agent sans quota").click()
    page.fill(".composer textarea", "[echec] travaille")
    page.press(".composer textarea", "Control+Enter")
    bandeau = page.locator("[data-id=incident]")
    expect(bandeau).to_be_visible(timeout=10000)
    expect(bandeau).to_contain_text("Quota épuisé")
    expect(bandeau).to_contain_text("attente de la reprise")
    expect(bandeau).to_contain_text("Geste proposé")

    expect(page.locator("#n-incidents")).not_to_have_text("0")
    page.click("#btn-incidents")
    panneau = page.locator("#panneau-incidents")
    expect(panneau.locator("[data-id=inc-liste]")).to_contain_text("Agent sans quota")
    expect(panneau.locator("[data-id=inc-jauge]")).to_contain_text("crédit d’utilisation épuisé, reprise")
    page.request.post(serveur.url + "/api/taches/inc-agent/arret", headers={"X-Orchestrateur": "1"})
    assert not page.erreurs, page.erreurs
