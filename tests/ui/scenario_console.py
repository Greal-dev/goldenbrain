"""Scénario du bouton « Console GoldenBrain » : toujours offert, il demande l'onglet `orch console <id>`."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def test_bouton_console_goldenbrain_ouvre_l_onglet(page, serveur):
    projet(serveur, "C1-Console", {"co-un": ("Un CO", "")})
    charger(page)
    ligne(page, "Un CO").click()
    bouton = page.get_by_role("button", name="Console GoldenBrain")
    expect(bouton).to_be_enabled()  # sans session ni tour : toujours disponible
    with page.expect_response(lambda r: r.url.endswith("/api/taches/co-un/console")) as rep:
        bouton.click()
    commande = rep.value.json()["commande"]
    assert commande[-4:-1] == ["console", "co-un", "--url"] and commande[1].endswith("orch.py")
    page.wait_for_selector("#banniere >> text=Console GoldenBrain ouverte")
    assert not page.erreurs, page.erreurs
