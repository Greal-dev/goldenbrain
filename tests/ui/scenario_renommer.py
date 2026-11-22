"""Renommer une tâche (INV-RENOMMER-1) : clic sur le titre, Échap annule, Entrée enregistre sans changer
le fichier ; proposition « renommer » acceptée depuis la page « Décisions » (INV-RENOMMER-2)."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_renommer_depuis_la_fiche(page, serveur):
    projet(serveur, "C1-Renom", {"rn-un": ("Ventes du club RN", "")})
    fichier = serveur.vault / "Projets" / "C1-Renom" / "taches" / "rn-un.md"
    charger(page)
    ligne(page, "Ventes du club RN").click()
    titre = page.locator(".d-titre")
    expect(titre).to_have_text("Ventes du club RN")

    titre.click()  # Échap annule : rien n'est écrit
    champ = page.locator("[data-id=titre-champ]")
    expect(champ).to_be_focused()
    champ.fill("Abandonné")
    champ.press("Escape")
    expect(page.locator(".d-titre")).to_have_text("Ventes du club RN")
    assert "# Ventes du club RN" in fichier.read_text(encoding="utf-8")

    page.locator(".d-titre").click()  # Entrée enregistre
    page.locator("[data-id=titre-champ]").fill("API/MCP ventes du club RN")
    page.locator("[data-id=titre-champ]").press("Enter")
    expect(page.locator(".d-titre")).to_have_text("API/MCP ventes du club RN")
    texte = fichier.read_text(encoding="utf-8")
    assert "# API/MCP ventes du club RN" in texte and "Ventes du club RN\n" not in texte.replace("API/MCP ventes du club RN", "")
    assert fichier.exists() and page.locator("[data-id=titre-champ]").count() == 0
    expect(ligne(page, "API/MCP ventes du club RN")).to_be_visible()  # le volet de gauche suit
    assert not page.erreurs, page.erreurs


def test_proposition_renommer_acceptee_sur_la_page_decisions(page, serveur):
    projet(serveur, "C1-RenomProp", {"rp-un": ("Ventes du club RP", "")})
    p = page.request.post(serveur.url + "/api/propositions", headers=H, data={
        "type": "renommer", "tache": "rp-un", "valeur": "API/MCP ventes du club RP", "de": "revue-rp",
        "motif": "Le contenu est un accès MCP/API, pas les ventes."}).json()
    assert p["etat"] == "en_attente"
    page.goto(page.url_serveur + "/#decisions")
    carte = page.locator(".dc-q", has_text="Renommer « Ventes du club RP » en « API/MCP ventes du club RP »")
    expect(carte).to_be_visible()
    expect(page.get_by_text("Le contenu est un accès MCP/API, pas les ventes.")).to_be_visible()
    assert serveur.vault.joinpath("Projets/C1-RenomProp/taches/rp-un.md").read_text(encoding="utf-8").count("# Ventes du club RP") == 1
    page.locator("li, .dc", has=carte).get_by_role("button", name="Accepter").click()
    expect(carte).to_have_count(0)
    texte = serveur.vault.joinpath("Projets/C1-RenomProp/taches/rp-un.md").read_text(encoding="utf-8")
    assert "# API/MCP ventes du club RP" in texte
    assert not page.erreurs, page.erreurs
