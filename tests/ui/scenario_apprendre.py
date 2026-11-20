"""Mode « Apprendre » (INV-APPRENDRE-1) : interrupteur général persisté, réglage par tâche, explications mises en valeur
dans la conversation, « Ce que vous pouvez retenir » dans la fiche ; inactif, rien ne change.
Le harnais factice obéit à la consigne reçue : sans elle, aucun encadré."""

import os

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}
ENCADRE = ".conv blockquote.callout.c-apprendre"


def _tour(page, serveur, nom, ident, titre, mode=None):
    projet(serveur, nom, {ident: (titre, "")})
    charger(page)
    ligne(page, titre).click()
    expect(page.locator(".d-titre")).to_have_text(titre)
    if mode is not None:
        page.select_option("[data-id=ap-tache]", mode)
        expect(page.locator("[data-id=ap-tache]")).to_have_value(mode)
    page.fill(".composer textarea", "Bonjour agent")
    page.press(".composer textarea", "Control+Enter")
    page.wait_for_selector("text=en bonne voie", timeout=10000)


def _capture(page, nom):
    if dossier := os.environ.get("GB_CAPTURES_APPRENDRE"):
        page.screenshot(path=os.path.join(dossier, nom))


def test_apprendre_inactif_puis_actif_puis_reglage_de_tache(page, serveur):
    try:
        # Inactif par défaut : comportement inchangé.
        _tour(page, serveur, "C1-ApprSans", "ap-sans", "Sans apprendre")
        expect(page.locator(ENCADRE)).to_have_count(0)
        expect(page.locator("[data-id=fiche-retenir]")).to_have_count(0)
        expect(page.locator("[data-id=ap-tache]")).to_have_value("")

        # Interrupteur général, persisté.
        page.goto(page.url_serveur + "/#reglages/apprendre")
        page.wait_for_selector("[data-id=ap-actif]")
        expect(page.locator("[data-id=ap-aide]")).to_contain_text("crédit d’utilisation")
        assert not page.locator("[data-id=ap-actif]").is_checked()
        with page.expect_response(lambda r: r.url.endswith("/api/apprendre") and r.request.method == "PUT") as rep:
            page.check("[data-id=ap-actif]")
        assert rep.value.json() == {"actif": True}
        _capture(page, "apprendre-reglage.png")
        page.reload()
        page.wait_for_selector("[data-id=ap-actif]")
        assert page.locator("[data-id=ap-actif]").is_checked()

        # Actif : encadré dans la conversation, points à retenir dans la fiche.
        _tour(page, serveur, "C1-ApprAvec", "ap-avec", "Avec apprendre")
        expect(page.locator(ENCADRE)).to_contain_text("Ce que je fais")
        expect(page.locator(ENCADRE)).to_contain_text("Je lis le dossier")
        expect(page.locator("[data-id=fiche-retenir] li")).to_have_count(3)
        expect(page.locator("[data-id=fiche-retenir]")).to_contain_text("vérifier ensuite")
        _capture(page, "apprendre-conversation.png")

        # Une tâche peut dire non malgré le réglage général…
        _tour(page, serveur, "C1-ApprNon", "ap-non", "Apprendre refusé", mode="non")
        expect(page.locator(ENCADRE)).to_have_count(0)
        assert serveur.vault.joinpath("Projets/C1-ApprNon/taches/ap-non.md").read_text(encoding="utf-8").count("apprendre: non") == 1
    finally:  # le serveur est partagé : rendre le réglage général
        page.request.put(serveur.url + "/api/apprendre", headers=H, data={"actif": False})
    # …ou oui malgré un réglage général coupé.
    _tour(page, serveur, "C1-ApprOui", "ap-oui", "Apprendre voulu", mode="oui")
    expect(page.locator(ENCADRE)).to_contain_text("Ce que je fais")
    assert not page.erreurs, page.erreurs
