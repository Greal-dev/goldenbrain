"""Scénario « Voir le résultat » (INV-RESULTAT-1) : message clair sans résultat ; avec un dossier de travail,
un site et une adresse citée dans la fiche, la liste des éléments s'affiche. Rien n'est ouvert pour de vrai
(le serveur est réel : l'ouverture par le système est vérifiée par les tests de la porte rapide)."""

import os

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect
import univers


def test_voir_le_resultat_message_puis_liste(page, serveur, tmp_path):
    projet(serveur, "C1-ResUI", {"res-vide": ("Sans résultat", ""), "res-site": ("Avec résultat", "")})
    charger(page)
    ligne(page, "Sans résultat").click()
    page.get_by_role("button", name="Voir le résultat").click()
    expect(page.locator("#banniere")).to_contain_text("Rien à montrer")

    site = tmp_path / "monsite"
    site.mkdir()
    (site / "index.html").write_text("<h1>Bonjour</h1>", encoding="utf-8")
    univers.ecrire(serveur.vault, "Projets/C1-ResUI/contexte.md",
                   f"---\ntype: contexte\ncasquette: C1-Pro\nnom: ResUI\ndepot: \"{site}\"\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-ResUI/taches/res-site.md",
                   univers.tache("Avec résultat") + "\n<!-- orchestrateur:debut -->\n## Fiche\n"
                   "- **Essai** : ouvrir http://localhost:5173/\n<!-- orchestrateur:fin -->\n")
    page.reload()
    page.wait_for_selector("#arbre .ligne")
    ligne(page, "Avec résultat").click()
    expect(page.get_by_role("button", name="Voir le résultat")).to_be_visible()
    if dossier := os.environ.get("GB_RESULTAT_CAPTURES"):
        page.set_viewport_size({"width": 1366, "height": 768})
        page.screenshot(path=os.path.join(dossier, "voir-resultat-bouton.png"))
    page.get_by_role("button", name="Voir le résultat").click()
    dlg = page.locator("dialog[open] .voir-resultats")
    expect(dlg.get_by_role("button", name="Site local localhost:5173/")).to_be_visible()
    expect(dlg.get_by_role("button", name="Site : index.html")).to_be_visible()
    expect(dlg.get_by_role("button", name="Dossier de travail : monsite")).to_be_visible()
    if dossier := os.environ.get("GB_RESULTAT_CAPTURES"):  # captures de la fiche de tâche, hors porte
        page.screenshot(path=os.path.join(dossier, "voir-resultat-liste.png"))
    assert not page.erreurs
