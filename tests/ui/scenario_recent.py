"""Étiquette « Récent » (INV-RECENT-1) : la tâche créée entre dans la pastille et la vue, « Non prioritaire » l'en sort."""

from playwright.sync_api import expect

from tests.ui import univers

CREER = ("fetch('/api/taches',{method:'POST',headers:{'X-Orchestrateur':'1','Content-Type':'application/json'},"
         "body:JSON.stringify({titre:'Suivi récent interface',conteneur:'Projets/C2-Beta'})}).then(r => r.json())")


def test_pastille_vue_et_non_prioritaire(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C2-Beta/taches/rec-ancienne.md", univers.tache("Ancienne sans étiquette"))
    page.goto(page.url_serveur + "/")
    ident = page.evaluate(CREER)["id"]
    page.reload()
    expect(page.locator("#n-recent")).not_to_have_text("0")  # pastille du bandeau
    page.click("#btn-recent")
    ligne = f'[data-id="etiq-ligne"][data-tache="{ident}"]'
    page.wait_for_selector(ligne)
    assert page.locator('[data-id="etiq-ligne"]', has_text="Ancienne sans étiquette").count() == 0
    page.goto(page.url_serveur + f"/#t={ident}")
    page.reload()
    page.wait_for_selector('[data-id="details-bascule"]')
    if not page.locator('[data-id="details"]').is_visible():
        page.click('[data-id="details-bascule"]')
    with page.expect_response(lambda r: r.url.endswith("/etiquettes") and r.request.method == "POST") as rep:
        page.click('[data-id="non-prioritaire"]')
    assert rep.value.status == 200
    page.wait_for_selector('[data-id="non-prioritaire"]', state="detached")
    page.click("#btn-recent")
    page.wait_for_selector('[data-id="etiq-ligne"], .vide')
    assert page.locator(ligne).count() == 0
    assert not page.erreurs, page.erreurs
