"""Scénario de l'écran « En cours » (INV-TRAVAUX-1, INV-TRAVAUX-2) : un tour lance des sous-agents et une liste
d'étapes ; l'écran, ouvert depuis la barre du haut, montre la tâche, la dernière action, l'avancement et les aides ;
pause, reprise, puis arrêt avec confirmation. Capture dans `GB_CAPTURES` si posé, sinon dans le dossier du test."""

import os
from pathlib import Path

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def test_en_cours_montre_aides_avancement_et_permet_pause_et_arret(page, serveur, tmp_path):
    projet(serveur, "C1-Travaux", {"tr-agent": ("Agent avec aides", "")})
    charger(page)
    ligne(page, "Agent avec aides").click()
    page.fill(".composer textarea", "[aides] [lent 60] travaille")
    page.press(".composer textarea", "Control+Enter")
    expect(page.locator("#n-tours")).not_to_have_text("0", timeout=10000)

    try:
        page.click("#btn-travaux")
        ecran = page.locator("[data-id=travaux]")
        carte = ecran.locator("[data-id=tr-tour][data-tache=tr-agent]")
        expect(carte).to_be_visible(timeout=10000)
        expect(carte).to_contain_text("Agent avec aides")
        expect(carte).to_contain_text("Travaux")  # le projet
        expect(carte.locator("[data-id=tr-action]")).to_contain_text("lance les tests")
        expect(carte.locator("[data-id=tr-action]")).to_contain_text("a modifié 1 fichier")
        expect(carte.locator("[data-id=tr-avancement]")).to_contain_text("2 étapes sur 5")
        expect(carte.locator("[data-id=tr-sous-agent]")).to_have_count(2)
        expect(carte).to_contain_text("Relire le module des factures")
        page.screenshot(path=str(Path(os.environ.get("GB_CAPTURES") or tmp_path) / "en-cours.png"), full_page=False)

        carte.locator("[data-id=tr-pause]").click()
        expect(carte.locator("[data-id=tr-action]")).to_contain_text("En pause")
        expect(page.locator("[data-id=tr-reprendre]")).to_be_visible()
        page.locator("[data-id=tr-reprendre]").click()
        expect(carte.locator("[data-id=tr-pause]")).to_be_visible()

        carte.locator("[data-id=tr-arreter]").click()
        dlg = page.locator("dialog.dlg")
        expect(dlg).to_contain_text("Arrêter cet assistant ?")
        dlg.locator("button", has_text="Arrêter").click()
        expect(ecran.locator("[data-id=tr-tour][data-tache=tr-agent]")).to_have_count(0, timeout=10000)
    finally:  # un tour laissé vivant fausserait les alertes des scénarios suivants
        page.request.post(serveur.url + "/api/taches/tr-agent/arret", headers={"X-Orchestrateur": "1"})
    assert not page.erreurs, page.erreurs
