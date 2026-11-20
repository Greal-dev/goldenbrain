"""Scénario des Réglages « Appareils » (INV-DISTANT-5, INV-DISTANT-6) : au poste, « Ajouter un téléphone »
affiche un code QR ; le « téléphone » (un second contexte de navigateur, sur l'adresse d'écoute distante
127.0.0.2) ouvre le lien, est appairé, accède à l'interface ; révoqué au poste, il est refusé (401).
Serveur dédié : l'écoute distante et l'accès des appareils ne touchent pas les autres scénarios."""

import pytest
from playwright.sync_api import expect

from conftest import demarrer

DISTANT = "127.0.0.2"  # adresse de boucle locale distincte : joue l'adresse Tailscale du poste
SUPPLEMENT = f'\n[executeurs]\necoute = "{DISTANT}"\n\n[distant]\nappareils = true\n'


@pytest.fixture(scope="module")
def poste(tmp_path_factory):
    yield from demarrer(tmp_path_factory.mktemp("ui-appareils"), SUPPLEMENT)


def test_ajouter_un_telephone_puis_le_revoquer(navigateur, poste):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768})
    tel_ctx = navigateur.new_context(viewport={"width": 390, "height": 844})
    erreurs = []
    try:
        page = ctx.new_page()
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.goto(poste.url + "/#reglages/appareils")
        expect(page.locator("[data-id=app-etat]")).to_contain_text(f"Actif : http://{DISTANT}:{poste.port}")
        expect(page.locator("[data-id=app-sans-https]")).to_be_visible()
        expect(page.locator("[data-id=app-liste]")).to_contain_text("Aucun appareil")
        page.fill("[data-id=app-nom]", "téléphone d’essai")
        with page.expect_response(lambda r: r.url.endswith("/api/appareils/appairage")) as rep:
            page.click("[data-id=app-ajouter]")
        lien = rep.value.json()["lien"]
        expect(page.locator("[data-id=app-qr]")).to_be_visible()

        tel = tel_ctx.new_page()
        base = f"http://{DISTANT}:{poste.port}"
        assert tel.request.get(base + "/api/arbre").status == 401  # sans jeton : refusé
        tel.goto(lien)
        tel.wait_for_url(base + "/")
        assert tel.request.get(base + "/api/arbre").status == 200
        assert tel.request.get(base + "/api/appareils").status == 403  # réservé au poste

        page.reload()
        ligne = page.locator("[data-id=app-liste] li", has_text="téléphone d’essai")
        expect(ligne).to_contain_text("dernière connexion")
        page.once("dialog", lambda d: d.accept())
        ligne.locator("button", has_text="Révoquer").click()
        expect(page.locator("[data-id=app-liste]")).to_contain_text("Aucun appareil")
        assert tel.request.get(base + "/api/arbre").status == 401
        page.click("[data-id=app-journal] summary")
        expect(page.locator("[data-id=app-journal]")).to_contain_text("révocation")
    finally:
        ctx.close()
        tel_ctx.close()
    assert not erreurs, erreurs
