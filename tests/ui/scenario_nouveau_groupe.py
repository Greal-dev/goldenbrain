"""Nouvelle tâche : « ＋ Nouveau groupe… » crée le projet qui manque et y range la tâche."""

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import _ECRITS, charger, ligne, niveau


def test_nouveau_groupe_a_la_creation(page, serveur):
    _ECRITS.append(serveur.vault / "Casquettes" / "C3-NG")  # le groupe créé y naît aussi : tout part au nettoyage
    univers.ecrire(serveur.vault, "Casquettes/C3-NG/Livres-ng/contexte.md",
                   "---\ntype: contexte\ncasquette: C3-NG\nnom: Livres NG\n---\n")
    univers.ecrire(serveur.vault, "Casquettes/C3-NG/Livres-ng/taches/ng-existant.md", univers.tache("Livre existant NG"))
    charger(page)
    page.click("#btn-nouvelle")
    page.fill("input[name=titre]", "Écrire le plan du roman NG")
    assert page.locator("[data-id=nouveau-groupe]").is_hidden()
    page.select_option("select[name=conteneur]", label="＋ Nouveau groupe…")
    page.wait_for_selector("[data-id=nouveau-groupe]:not([hidden])")
    page.fill("input[name=groupe_nom]", "Roman NG")
    page.select_option("select[name=groupe_dans]", "Casquettes/C3-NG/Livres-ng")
    with page.expect_response(lambda r: r.url.endswith("/api/taches") and r.request.method == "POST") as rep:
        page.click(".dlg-actions .primaire")
    assert rep.value.status == 201
    assert rep.value.json()["conteneur"] == "Casquettes/C3-NG/Livres-ng/Roman-NG"
    charger(page)
    groupe, tache = ligne(page, "Roman NG"), ligne(page, "Écrire le plan du roman NG")
    assert niveau(tache) == niveau(groupe) + 1
    assert (serveur.vault / "Casquettes/C3-NG/Livres-ng/Roman-NG/contexte.md").is_file()
    assert not page.erreurs, page.erreurs
