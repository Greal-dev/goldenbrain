"""Scénario de la pastille « intégration en retard » (INV-INTEG-1) : visible sur une tâche terminée dont la
branche gb/* n'est pas fusionnée depuis plus de 2 h, levée par la fusion ; seuil réglable dans Réglages."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, projet
from playwright.sync_api import expect
from orchestrateur.fiches import ecrire_fiche, fiche_vide
from univers import git

H = {"X-Orchestrateur": "1"}


def test_pastille_integration_en_retard_visible_puis_levee_par_la_fusion(page, serveur):
    depot = serveur.vault.parent / "depot-git"
    projet(serveur, "C1-Integ", {
        "fini": ("Tâche finie", "statut: fait\nsession: s1\n"),
        "neuve": ("Tâche ouverte", "")})
    fiche = serveur.vault / "Projets/C1-Integ/taches/fini.md"
    fiche.write_text(ecrire_fiche(fiche.read_text(encoding="utf-8"),
                                  {**fiche_vide(), "resultat": "branche gb/ui-retard, commit abc"}), encoding="utf-8")
    try:
        charger(page)
        ligne = page.locator("#arbre .ligne", has_text="Tâche finie")
        expect(ligne.locator("[data-id=integration-retard]")).to_contain_text("intégration en retard", timeout=10000)
        expect(page.locator("#arbre .ligne", has_text="Tâche ouverte").locator("[data-id=integration-retard]")).to_have_count(0)

        git(depot, "merge", "-q", "--ff-only", "gb/ui-retard")  # fusion dans gb/integration
        page.wait_for_timeout(1500)  # cache_s = 1 dans la config d'essai
        # Une lecture périmée est servie telle quelle et relance le calcul : la page suivante montre l'état frais
        # (l'arbre se recharge seul toutes les 60 s ; ici on le recharge à la main).
        for _ in range(5):
            charger(page)
            if not page.locator("#arbre .ligne", has_text="Tâche finie").locator("[data-id=integration-retard]").count():
                break
            page.wait_for_timeout(500)
        expect(page.locator("#arbre .ligne", has_text="Tâche finie").locator("[data-id=integration-retard]")).to_have_count(0)

        page.goto(page.url_serveur + "/#reglages/integration")
        page.wait_for_selector("[data-id=ig-retard]")
        assert page.locator("[data-id=ig-retard]").input_value() == "2"
        with page.expect_response(lambda r: r.url.endswith("/api/integration") and r.request.method == "PUT") as rep:
            page.fill("[data-id=ig-retard]", "6")
            page.locator("[data-id=ig-retard]").dispatch_event("change")
        assert rep.value.json()["retard_h"] == 6
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(serveur.url + "/api/integration", headers=H, data={"retard_h": 2})
