"""Scénario du signe de vie (INV-VIGIE-1) : phrase d'activité sous la tâche, puis le tour muet devient
« Silencieux » (tâche et bandeau), « Attendre » tait l'alerte, « Arrêter le tour » l'interrompt.
L'univers règle `[vigie] silence_s = 3` ; le harnais factice n'a pas de processus : diagnostic neutre."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_tour_muet_signale_puis_attendre_puis_arreter(page, serveur):
    projet(serveur, "C1-Vigie", {"vi-muette": ("Tâche muette", "")})
    charger(page)
    try:
        ligne(page, "Tâche muette").click()
        expect(page.locator(".d-titre")).to_have_text("Tâche muette")
        page.fill(".composer textarea", "[lent 60] travaille")
        page.press(".composer textarea", "Control+Enter")
        phrase = page.locator(".d-vie [data-id=vie-phrase]")
        expect(phrase).to_contain_text("je lis le dossier", timeout=5000)
        expect(phrase).to_contain_text("il y a")

        silence = page.locator(".d-vie [data-id=vie-silence]")
        expect(silence).to_contain_text("Silencieux depuis", timeout=10000)
        expect(silence).to_contain_text("diagnostic")
        alerte = page.locator("#vigie-alertes")
        expect(alerte).to_be_visible()
        expect(alerte).to_contain_text("Tâche muette")

        silence.locator("button", has_text="Attendre").click()
        expect(phrase).to_be_visible(timeout=5000)
        expect(alerte).to_be_hidden(timeout=5000)

        expect(silence).to_be_visible(timeout=10000)  # nouveau délai écoulé : l'alerte revient
        silence.locator("button", has_text="Arrêter la séance").click()
        expect(page.locator(".d-meta .etat")).to_have_text("Séance de travail interrompue", timeout=8000)
        expect(alerte).to_be_hidden(timeout=5000)
    finally:
        page.request.post(serveur.url + "/api/taches/vi-muette/arret", headers=H)
    assert not page.erreurs, page.erreurs
