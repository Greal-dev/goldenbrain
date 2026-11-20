"""Scénario du codespace d'une tâche : bloc absent sans déclaration ; état, gestes et réglage « Où ».

`gh` n'est jamais appelé : les routes `/codespace` sont servies par `page.route` (état imposé, gestes
consignés) ; la route `/ou` est la vraie (clé `ou:` écrite dans le vault temporaire).
"""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

ETAT = {"declaration": "proprio/depot", "ou": "poste", "nom": "cs-depot-1", "etat": "Available",
        "depot": "proprio/depot", "erreur": ""}


def _ouvrir(page, serveur, nom, taches, titre):
    projet(serveur, nom, taches)
    charger(page)
    ligne(page, titre).click()
    expect(page.locator(".d-titre")).to_have_text(titre)


def test_sans_codespace_declare_aucun_bloc(page, serveur):
    with page.expect_response("**/api/taches/scs-un/codespace") as rep:
        _ouvrir(page, serveur, "C1-SansCs", {"scs-un": ("Un SCS", "")}, "Un SCS")
    assert rep.value.json()["declaration"] == ""  # vraie route : aucun appel à gh
    expect(page.locator(".d-meta .codespace")).to_be_hidden()
    assert not page.erreurs, page.erreurs


def test_codespace_etat_gestes_et_lieu(page, serveur):
    gestes = []

    def servir(route):
        if route.request.method == "POST":
            gestes.append(route.request.url.rsplit("/", 1)[-1])
            route.fulfill(json={**ETAT, "etat": "Shutdown"} if gestes[-1] == "arreter" else ETAT)
        else:
            route.fulfill(json=ETAT)
    page.route("**/api/taches/*/codespace**", servir)
    _ouvrir(page, serveur, "C1-AvecCs", {"acs-un": ("Un ACS", "")}, "Un ACS")
    bloc = page.locator(".d-meta .codespace")
    expect(bloc).to_contain_text("cs-depot-1")
    expect(bloc.locator(".cs-etat")).to_have_text("disponible")
    bloc.locator("button:has-text('VS Code')").click()
    bloc.locator("button:has-text('Navigateur')").click()
    page.locator(".d-meta .codespace button:has-text('Arrêter')").click()
    expect(page.locator(".d-meta .codespace .cs-etat")).to_have_text("arrêté")
    expect(page.locator(".d-meta .codespace button:has-text('Arrêter')")).to_be_disabled()
    assert gestes == ["code", "web", "arreter"]
    with page.expect_response("**/api/taches/acs-un/ou") as rep:
        page.locator(".d-meta .codespace select").select_option("codespace")
    assert rep.value.ok
    lu = serveur.vault / "Projets/C1-AvecCs/taches/acs-un.md"
    assert "ou: codespace" in lu.read_text(encoding="utf-8")
    assert not page.erreurs, page.erreurs
