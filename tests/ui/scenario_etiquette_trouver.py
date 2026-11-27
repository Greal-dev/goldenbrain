"""Créer une étiquette et y ranger l'existant (INV-ETIQUETTE-5) : Ctrl+K → « Nouvelle étiquette… » → la vue s'ouvre avec
« Trouver les tâches » lancé (classement local par synonymes) → cocher → « Étiqueter » → la vue liste la tâche ;
regroupement « Par étiquette » : un clic sur le groupe ouvre la vue de l'étiquette (INV-ETIQUETTE-4)."""

import univers
from aides_arbre import _ECRITS, nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

MOT = "finances-perso"


def _monde(serveur):
    _ECRITS.append(serveur.vault / "Projets" / "C1-TrouverEtiq")
    univers.ecrire(serveur.vault, "Projets/C1-TrouverEtiq/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: TrouverEtiq\n---\n")
    for nom, titre in (("te-a", "Relevé CAF Zeta9"), ("te-b", "Haie Zeta9")):
        univers.ecrire(serveur.vault, f"Projets/C1-TrouverEtiq/taches/{nom}.md", univers.tache(titre))


def test_nouvelle_etiquette_trouver_cocher_etiqueter(page, serveur):
    _monde(serveur)
    page.goto(page.url_serveur + "/")
    page.wait_for_selector("#arbre .ligne")
    page.keyboard.press("Control+k")
    page.fill(".pal-champ", "Nouvelle étiquette")
    page.locator('[data-id="palette-commande"]', has_text="Nouvelle étiquette…").click()
    dlg = page.locator("dialog.dlg:not(.palette)")
    dlg.locator('input[name="nom"]').fill(MOT)
    dlg.locator('textarea[name="consigne"]').fill("Argent du foyer")
    dlg.locator(".dlg-actions .primaire").click()
    expect(page).to_have_url(page.url_serveur + f"/#etiquette={MOT}")
    expect(page.locator('[data-id="vue-etiquette"]')).to_contain_text("Argent du foyer")
    panneau = page.locator('[data-id="etiq-trouver-panneau"]')
    cible = panneau.locator('[data-id="etiq-cand"]', has_text="Relevé CAF Zeta9")
    expect(cible).to_be_visible()  # « finances » appelle CAF et relevé
    expect(cible.locator("input")).to_be_checked()
    expect(cible.locator('[data-id="etiq-motif"]')).to_contain_text("caf")
    expect(panneau.locator('[data-id="etiq-cand"]', has_text="Haie Zeta9")).to_have_count(0)
    for case in panneau.locator('[data-id="etiq-cand"] input:checked').all():  # serveur partagé : seule notre tâche
        if not case.locator("xpath=ancestor::li").get_attribute("data-tache") == "te-a":
            case.uncheck()
    panneau.locator('[data-id="etiq-poser"]').click()
    expect(page.locator('[data-id="etiq-ligne"]')).to_have_count(1)
    expect(page.locator('[data-id="etiq-ligne"]')).to_contain_text("Relevé CAF Zeta9")
    expect(panneau.locator('[data-id="etiq-annuler-pose"]')).to_be_visible()

    # Regroupement « Par étiquette » : le groupe porte son compte et ouvre la vue.
    page.goto(page.url_serveur + "/")
    page.wait_for_selector("#arbre .ligne")
    page.click("#btn-filtres")
    page.select_option("#f-groupe", "etiquette")
    groupe = page.locator("#arbre .ligne.t-groupe", has_text=f"#{MOT}")
    expect(groupe.locator(".compte")).to_have_text("1")
    page.keyboard.press("Escape")  # le panneau des filtres flotte au-dessus de l'arbre
    expect(page.locator("#panneau-filtres")).to_be_hidden()
    groupe.locator(".titre").click()
    expect(page).to_have_url(page.url_serveur + f"/#etiquette={MOT}")
    assert not page.erreurs, page.erreurs
