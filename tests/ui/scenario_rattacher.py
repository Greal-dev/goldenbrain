"""Proposition « rattacher » (INV-RATTACHER-1) : un lot en UNE carte de la page « Décisions », acceptée d'un clic."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_proposition_rattacher_un_lot_acceptee_d_un_clic(page, serveur):
    projet(serveur, "C1-Ratt", {"ra-groupe": ("Groupe Développement RA", ""), "ra-a": ("Premier travail RA", ""),
                                "ra-b": ("Second travail RA", "")})
    r = page.request.post(serveur.url + "/api/propositions", headers=H, data={
        "type": "rattacher", "tache": "ra-a", "valeur": "ra-groupe", "taches": ["ra-b"], "de": "revue-ra", "motif": "Ranger le développement."})
    assert r.status == 201 and r.json()["taches"] == ["ra-a", "ra-b"]
    page.goto(page.url_serveur + "/#decisions")
    carte = page.locator(".dc-q", has_text="Rattacher 2 tâches sous")
    expect(carte).to_have_count(1)  # un lot = UNE entrée
    expect(page.get_by_text("Ranger le développement.")).to_be_visible()
    page.locator("li, .dc", has=carte).get_by_role("button", name="Accepter").click()
    expect(carte).to_have_count(0)
    for nom in ("ra-a", "ra-b"):
        assert "parent: ra-groupe" in serveur.vault.joinpath(f"Projets/C1-Ratt/taches/{nom}.md").read_text(encoding="utf-8")
    assert not page.erreurs, page.erreurs
