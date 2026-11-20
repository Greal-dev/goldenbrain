"""Scénario des Réglages « Compactage automatique » (INV-COMPACT-1) : seuil général et plafond
persistés et relus, mécanisme par harnais, puis vue de mesure alimentée par un vrai tour."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_reglages_compactage_seuil_persistance_et_mesure(page, serveur):
    projet(serveur, "C1-Compact", {"cp-tache": ("Tâche mesurée", "")})
    try:
        charger(page)
        page.goto(page.url_serveur + "/#reglages/compactage")
        page.wait_for_selector("[data-id=cp-pct]")
        assert page.locator("[data-id=cp-pct]").input_value() == "45"
        assert page.locator("[data-id=cp-plafond]").input_value() == "0"
        page.evaluate("document.querySelector('[data-id=cp-plafond]').dataset.ancien = '1'")
        with page.expect_response(lambda r: r.url.endswith("/api/compactage") and r.request.method == "PUT") as rep:
            page.fill("[data-id=cp-pct]", "50")
            page.locator("[data-id=cp-pct]").dispatch_event("change")
        assert rep.value.json()["pct"] == 50
        # La réponse précède le redessin : saisir avant lui enverrait la valeur du champ recréé.
        page.wait_for_selector("[data-id=cp-plafond]:not([data-ancien])")
        with page.expect_response(lambda r: r.url.endswith("/api/compactage") and r.request.method == "PUT"):
            page.fill("[data-id=cp-plafond]", "300000")
            page.locator("[data-id=cp-plafond]").dispatch_event("change")
        expect(page.locator("[data-id=cp-harnais]")).to_contain_text("claude : seuil propre à l’assistant IA")
        expect(page.locator("[data-id=cp-harnais]")).to_contain_text("opencode : solution de repli")

        page.reload()  # le réglage est relu du serveur (config.toml)
        page.wait_for_selector("[data-id=cp-pct]")
        assert page.locator("[data-id=cp-pct]").input_value() == "50"
        assert page.locator("[data-id=cp-plafond]").input_value() == "300000"

        # Un tour réel (harnais factice, contexte annoncé à 123 456 jetons) alimente la vue de mesure.
        r = page.request.post(serveur.url + "/api/taches/cp-tache/messages", headers=H, data={"texte": "travaille"})
        assert r.status in (200, 202), r.text()
        page.goto(page.url_serveur + "/#reglages/compactage")
        expect(page.locator("[data-id=cp-mesure]")).to_contain_text("100–200 k", timeout=10000)
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(serveur.url + "/api/compactage", headers=H, data={"pct": 45, "plafond": 0})
