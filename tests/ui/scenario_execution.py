"""Scénario de l'exécution par tâche ou regroupée (INV-REGROUPE-1) : motif affiché sur une sous-tâche,
réglage posé sur la tâche mère puis sur le conteneur, décision recalculée."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def test_motif_affiche_et_reglage_de_la_mere_puis_du_conteneur(page, serveur):
    projet(serveur, "C1-Exec", {
        "ex-m": ("Mère Exec", ""),
        "ex-a": ("Sous A Exec", "parent: ex-m\n"),
        "ex-b": ("Sous B Exec", "parent: ex-m\nprerequis: [ex-a]\n"),
        "ex-c": ("Sous C Exec", "parent: ex-m\nprerequis: [ex-b]\n"),
    })
    charger(page)
    motif = page.locator(".d-meta [data-motif-execution]")
    ligne(page, "Sous B Exec").click()
    expect(page.locator(".d-titre")).to_have_text("Sous B Exec")
    expect(motif).to_have_text("Regroupée sous « Mère Exec » : 3 sous-tâches petites et enchaînées")

    # Réglage sur la mère : une conversation par tâche pour ses sous-tâches.
    ligne(page, "Mère Exec").click()
    expect(page.locator(".d-titre")).to_have_text("Mère Exec")
    page.locator(".d-meta select[data-execution]").select_option("par_tache")
    expect(page.locator(".d-meta select[data-execution]")).to_have_value("par_tache")
    ligne(page, "Sous B Exec").click()
    expect(motif).to_contain_text("Une conversation par tâche : réglage « une conversation par tâche » posé sur Mère Exec")

    # Réglage sur le conteneur : la mère revient à l'héritage, le conteneur impose le regroupement.
    ligne(page, "Mère Exec").click()
    page.locator(".d-meta select[data-execution]").select_option("")
    ligne(page, "Exec").click()
    choix = page.locator(".casc-execution select[data-execution]")
    choix.select_option("regroupee")
    expect(choix).to_have_value("regroupee")
    contexte = serveur.vault / "Projets/C1-Exec/contexte.md"
    for _ in range(50):  # écriture du réglage par la route : rien à attendre à l'écran
        if "execution: regroupee" in contexte.read_text("utf-8"):
            break
        page.wait_for_timeout(100)
    assert "execution: regroupee" in contexte.read_text("utf-8")
    ligne(page, "Sous A Exec").click()
    expect(motif).to_contain_text("posé sur Exec")
    assert not page.erreurs, page.erreurs
