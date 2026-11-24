"""Proposition « rattacher » (INV-RATTACHER-1) : un lot en UNE carte de la page « Décisions », appliqué d'office, annulable d'un clic."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_proposition_rattacher_un_lot_applique_d_office_et_annulable(page, serveur):
    projet(serveur, "C1-Ratt", {"ra-groupe": ("Groupe Développement RA", ""), "ra-a": ("Premier travail RA", ""),
                                "ra-b": ("Second travail RA", "")})
    r = page.request.post(serveur.url + "/api/propositions", headers=H, data={
        "type": "rattacher", "tache": "ra-a", "valeur": "ra-groupe", "taches": ["ra-b"], "de": "revue-ra", "motif": "Ranger le développement."})
    assert r.status == 201 and r.json()["taches"] == ["ra-a", "ra-b"]
    assert r.json()["etat"] == "acceptee" and r.json()["auto"]  # INV-PROP-1 : geste de routine, appliqué d'office
    chemin = lambda nom: serveur.vault.joinpath(f"Projets/C1-Ratt/taches/{nom}.md")
    for nom in ("ra-a", "ra-b"):
        assert "parent: ra-groupe" in chemin(nom).read_text(encoding="utf-8")
    page.goto(page.url_serveur + "/#decisions")
    expect(page.locator(".dc-proposition")).to_have_count(0)
    office = page.locator(".dc-office")
    office.locator(":scope > summary").click()
    geste = office.locator(f"li.dc-office-geste[data-n='{r.json()['n']}']")
    expect(geste).to_contain_text("Rattacher 2 tâches sous")  # un lot = UNE entrée
    geste.locator("[data-annuler]").click()
    expect(geste).to_have_count(0, timeout=5000)
    for nom in ("ra-a", "ra-b"):
        assert "parent: ra-groupe" not in chemin(nom).read_text(encoding="utf-8")
    assert not page.erreurs, page.erreurs
