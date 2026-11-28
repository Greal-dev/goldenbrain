"""Supprimer une tâche ou un projet : confirmation forte, sous-tâches déplacées, annexes rangées (INV-SUPPR-1)."""

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import _ECRITS, charger, ligne, niveau, projet

DLG = "dialog[aria-label^='Supprimer']"


def test_supprimer_tache_sous_taches_deplacees(page, serveur):
    projet(serveur, "C1-SupprSrc", {"suppr-mere": ("Mère à supprimer", ""),
                                    "suppr-f1": ("Fille un supprimée", "parent: suppr-mere\n"),
                                    "suppr-f2": ("Fille deux supprimée", "parent: suppr-mere\n")})
    projet(serveur, "C1-SupprCible", {"suppr-cible": ("Déjà dans la cible", "")})
    charger(page)
    ligne(page, "Mère à supprimer").locator(".titre").click()
    page.click(".d-actions button:has-text('Supprimer…')")
    dlg = page.locator(DLG)
    dlg.wait_for(timeout=10000)
    assert "Suppression définitive" in dlg.inner_text() and "2 sous-tâches" in dlg.inner_text()
    ok = dlg.locator("button[type=submit]")
    assert ok.is_disabled()  # tant que l'irréversibilité n'est pas reconnue
    dlg.locator("input[name=mode][value=deplacer]").check()
    dlg.locator("select[name=vers]").select_option("Projets/C1-SupprCible")
    dlg.locator("input[name=compris]").check()
    assert ok.is_enabled()
    with page.expect_response(lambda r: r.url.endswith("/api/taches/suppr-mere/supprimer")) as rep:
        ok.click()
    assert rep.value.status == 200, rep.value.text()
    assert not (serveur.vault / "Projets/C1-SupprSrc/taches/suppr-mere.md").exists()
    charger(page)
    assert page.locator("#arbre .ligne .titre", has_text="Mère à supprimer").count() == 0
    cible = ligne(page, "SupprCible")
    for titre in ("Fille un supprimée", "Fille deux supprimée"):
        assert niveau(ligne(page, titre)) == niveau(cible) + 1
    assert not page.erreurs, page.erreurs


def test_supprimer_projet_annexe_rangee(page, serveur):
    projet(serveur, "C1-SupprProj", {"suppr-p1": ("Tâche du projet supprimé", "")})
    univers.ecrire(serveur.vault, "Projets/C1-SupprProj/pieces/contrat.md", "# Contrat\n")
    _ECRITS.append(serveur.vault / "Archives" / "supprimes")
    charger(page)
    ligne(page, "SupprProj").locator(".titre").click()
    page.click("[data-id=supprimer-projet]")
    dlg = page.locator(DLG)
    dlg.wait_for(timeout=10000)
    assert "1 autre note ou fichier" in dlg.inner_text()
    dlg.locator("input[name=mode][value=supprimer]").check()
    dlg.locator("input[name=compris]").check()
    with page.expect_response(lambda r: r.url.endswith("/api/conteneurs/supprimer")) as rep:
        dlg.locator("button[type=submit]").click()
    assert rep.value.status == 200, rep.value.text()
    assert not (serveur.vault / "Projets/C1-SupprProj").exists()
    ranges = list((serveur.vault / "Archives/supprimes").glob("*/Projets/C1-SupprProj/pieces/contrat.md"))
    assert ranges and ranges[0].read_text(encoding="utf-8") == "# Contrat\n"
    charger(page)
    assert page.locator("#arbre .ligne .titre", has_text="Tâche du projet supprimé").count() == 0
    assert not page.erreurs, page.erreurs


def test_supprimer_depuis_la_note_de_contexte_du_projet(page, serveur):
    projet(serveur, "C1-SupprNote", {"suppr-n1": ("Tâche de la note", "")})
    charger(page, deplier=False)
    page.click("#onglet-notes")
    for dossier in ("Projets", "C1-SupprNote"):
        page.click(f".ligne.t-dossier >> text={dossier}")
    page.click(".ligne.t-note >> text=contexte")
    page.click("button:has-text('Supprimer…')")
    dlg = page.locator(DLG)
    dlg.wait_for(timeout=10000)
    assert "SupprNote" in dlg.inner_text() and dlg.locator("button[type=submit]").is_disabled()
    page.keyboard.press("Escape")
    assert (serveur.vault / "Projets/C1-SupprNote/contexte.md").exists()
    assert not page.erreurs, page.erreurs
