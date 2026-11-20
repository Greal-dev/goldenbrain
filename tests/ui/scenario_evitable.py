"""Scénario de la pastille « évitable ? » (INV-EVITABLE-1) : réglée depuis Réglages, lue sur Décisions
(motif au survol et en clair), disparaît à la désactivation, suit le seuil."""

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}
BLOC = ("\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : fait\n- **Résultat** : livrable-ev\n"
        "- **Essai** : lancer livrable-ev\n- **Situation** : \n- **Reste à faire** : \n- **Prochain pas** : \n"
        "<!-- orchestrateur:fin -->\n")


def test_pastille_evitable_reglable(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Evit/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: Evit\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Evit/taches/ev-v.md",
                   univers.tache("Validation Evit", statut="fait", extra="session: s-ev\n") + BLOC)
    pastille = page.locator("li.dc[data-tache='ev-v'] [data-evitable]")
    try:
        page.goto(page.url_serveur + "/#reglages/evitable")
        page.wait_for_selector("[data-id=ev-actif]")
        assert page.locator("[data-id=ev-actif]").is_checked()
        assert page.locator("[data-id=ev-seuil]").input_value() == "75"

        page.goto(page.url_serveur + "/#decisions")  # 3 critères sur 4 (aucun contrôle déclaré) : 75 % atteint
        expect(pastille).to_have_text("évitable ?")
        expect(pastille).to_have_attribute("title", "3/4 critères : ✓ fiche avec Résultat et Essai ; ✓ Essai sans geste dans l'interface ; ✗ contrôle réussi et non périmé ; ✓ aucun refus de la revue IA. Aucune exclusion sensible.")
        expect(page.locator("li.dc[data-tache='ev-v'] .dc-evitable")).to_contain_text("3/4 critères")

        page.goto(page.url_serveur + "/#reglages/evitable")  # seuil à 100 % : plus atteint
        page.wait_for_selector("[data-id=ev-seuil]")
        with page.expect_response(lambda r: r.url.endswith("/api/decisions/evitable") and r.request.method == "PUT"):
            page.fill("[data-id=ev-seuil]", "100")
            page.locator("[data-id=ev-seuil]").dispatch_event("change")
        page.goto(page.url_serveur + "/#decisions")
        expect(page.locator("li.dc[data-tache='ev-v']")).to_be_visible()
        expect(pastille).to_have_count(0)

        page.goto(page.url_serveur + "/#reglages/evitable")  # seuil à 50 % puis désactivée
        page.wait_for_selector("[data-id=ev-seuil]")
        with page.expect_response(lambda r: r.url.endswith("/api/decisions/evitable") and r.request.method == "PUT"):
            page.fill("[data-id=ev-seuil]", "50")
            page.locator("[data-id=ev-seuil]").dispatch_event("change")
        page.goto(page.url_serveur + "/#decisions")
        expect(pastille).to_have_count(1)
        page.goto(page.url_serveur + "/#reglages/evitable")
        page.wait_for_selector("[data-id=ev-actif]")
        with page.expect_response(lambda r: r.url.endswith("/api/decisions/evitable") and r.request.method == "PUT"):
            page.locator("[data-id=ev-actif]").uncheck()
        page.goto(page.url_serveur + "/#decisions")
        expect(page.locator("li.dc[data-tache='ev-v']")).to_be_visible()
        expect(pastille).to_have_count(0)
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(serveur.url + "/api/decisions/evitable", headers=H, data={"actif": True, "seuil": 75})
