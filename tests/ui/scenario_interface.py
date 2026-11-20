"""Scénario du mode simple / avancé : bascule depuis Réglages, notions masquées, rebranchement d'une famille."""

import univers

H = {"X-Orchestrateur": "1"}


def deplier_tout(page):
    fermes = page.locator(".ligne .chev:not(.ouvert):not(.vide)")
    for _ in range(12):  # l'arbre se redessine à chaque dépliage : relire le premier chevron fermé
        if not fermes.count():
            break
        fermes.first.click()


def test_bascule_simple_masque_les_notions_et_rebranche_une_famille(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Interface/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Interface\nparent: Op Interface\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Interface/taches/reglee.md", univers.tache("Réglée"))
    try:
        page.goto(page.url_serveur + "/")
        page.wait_for_selector(".ligne")
        # Avancé : tout est là.
        for sel in ("#btn-equipe", "#btn-revue", "#onglet-notes"):
            assert page.locator(sel).is_visible(), sel
        deplier_tout(page)
        assert page.locator(".ligne.t-operation").count() >= 1

        page.click("#btn-reglages")
        page.click("[data-id=mode-simple]")
        page.wait_for_selector("body.mode-simple")
        for sel in ("#btn-equipe", "#btn-revue", "#onglet-notes", "#btn-props", "#btn-align"):
            assert not page.locator(sel).is_visible(), sel
        assert page.locator("#btn-reglages").is_visible()
        deplier_tout(page)
        assert page.locator(".ligne.t-operation").count() == 0
        assert page.locator(".ligne.t-tache >> text=Réglée").count() == 1

        # Une tâche : plus de personas, de liens, de choix de harnais ; conversation et statut restent.
        page.click(".ligne.t-tache >> text=Mère")
        page.wait_for_selector(".d-titre")
        assert page.locator(".composer textarea").is_visible()
        assert not page.locator("text=Solliciter…").is_visible()
        assert not page.locator("text=Promouvoir en projet").is_visible()
        assert not page.locator(".moteur select[aria-label='Assistant IA']").is_visible()
        assert page.locator(".moteur select[aria-label=Modèle]").is_visible()

        # Un interrupteur rebranche UNE famille sans toucher aux autres.
        page.click("#btn-reglages")
        page.click("[data-groupe=fonctions] > summary")
        page.check("[data-id=equipe]")
        page.wait_for_selector("body:not(.sans-equipe)")
        assert page.locator("#btn-equipe").is_visible()
        assert not page.locator("#btn-revue").is_visible()

        # Le mode mémorisé survit au rechargement.
        page.reload()
        page.wait_for_selector("body.mode-simple")
        assert not page.locator("#onglet-notes").is_visible()
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(page.url_serveur + "/api/interface", headers=H, data={"mode": "avance"})
