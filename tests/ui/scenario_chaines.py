"""Scénario « chaînes de phases » : dialogue « Chaînes » (modèles intégrés), création d'un modèle à deux phases,
lancement sur un projet, phases et état dans le détail de la tâche parente (INV-CHAINE-1, INV-CHAINE-2)."""

import aides_arbre
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger
from playwright.sync_api import expect


def test_chaine_creee_lancee_et_suivie_dans_le_detail(page, serveur):
    aides_arbre.projet(serveur, "C1-Chaines", {})
    charger(page)

    page.locator("#btn-chaines").click()
    liste = page.locator("dialog.chaines-dlg")
    expect(liste.locator(".chaine-modele", has_text="Réponse à un appel d'offres")).to_have_count(1)
    expect(liste.locator(".chaine-modele", has_text="Article ou contenu")).to_have_count(1)

    liste.get_by_role("button", name="Nouvelle chaîne").click()
    dlg = page.locator("dialog.dlg:not(.chaines-dlg)")
    dlg.locator("[name=titre]").fill("Veille Ch")
    dlg.locator("[name=resume]").fill("Deux phases d'essai.")
    dlg.locator("[data-phase='1'] label:has-text('Titre de la phase') input").fill("Lire Ch")
    dlg.locator("[data-phase='1'] textarea").fill("Lis le dossier.")
    dlg.locator("[data-act=ajouter-phase]").click()
    dlg.locator("[data-phase='2'] label:has-text('Titre de la phase') input").fill("Résumer Ch")
    dlg.locator("[data-phase='2'] textarea").fill("Résume ce que tu as lu.")
    dlg.locator("[data-phase='2'] input[type=checkbox]").check()
    dlg.locator("button[type=submit]").click()

    modele = page.locator("dialog.chaines-dlg .chaine-modele", has_text="Veille Ch")
    expect(modele).to_contain_text("2 phase(s)")
    modele.get_by_role("button", name="Lancer").click()
    dlg = page.locator("dialog.dlg")
    dlg.locator("select[name=conteneur]").select_option(label="Chaines")
    dlg.locator("[name=dossier]").fill("Dossiers/Essai")
    dlg.locator("[name=titre]").fill("Essai Ch")
    dlg.locator("button[type=submit]").click()

    bloc = page.locator(".chaine-bloc")
    expect(bloc.locator(".ch-phase")).to_have_count(2)
    expect(bloc.locator(".ch-phase").first).to_contain_text("Lire Ch")
    expect(bloc.locator(".ch-etat")).to_be_visible()
    assert not page.erreurs
