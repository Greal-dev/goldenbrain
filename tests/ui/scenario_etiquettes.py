"""Étiquettes libres (INV-ETIQUETTE-1..3) : ajout dans « Détails », puces dans l'arbre, filtre, réglage."""

from tests.ui import univers
from tests.ui.aides_arbre import deplier_tout


def test_ajout_puce_et_filtre(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C2-Beta/taches/etq-a.md", univers.tache("Cartographier les accès bancaires"))
    univers.ecrire(serveur.vault, "Projets/C2-Beta/taches/etq-b.md", univers.tache("Acheter des ampoules"))
    page.goto(page.url_serveur + "/#t=etq-a")
    page.wait_for_selector('[data-id="details-bascule"]')
    if not page.locator('[data-id="details"]').is_visible():
        page.click('[data-id="details-bascule"]')
    page.fill("#etiq-saisie", "Banque")
    with page.expect_response(lambda r: r.url.endswith("/etiquettes") and r.request.method == "POST") as rep:
        page.press("#etiq-saisie", "Enter")
    assert rep.value.status == 200
    page.wait_for_selector('.etiq-carte .etiq.retirable[data-etiquette="banque"]')
    page.goto(page.url_serveur + "/")
    page.reload()  # navigation sans rechargement sinon (même document, seul le fragment change)
    page.wait_for_selector("#arbre .ligne")
    deplier_tout(page)
    page.wait_for_selector('.etiq[data-etiquette="banque"]')  # puce dans l'arbre
    assert "#banque" in page.locator(".ligne", has_text="Cartographier").inner_text()
    assert "#banque" not in page.locator(".ligne", has_text="ampoules").inner_text()
    assert not page.erreurs, page.erreurs


def test_reglage_consigne(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C2-Beta/taches/etq-c.md", univers.tache("Tâche étiquetée", extra="etiquettes: [client]\n"))
    page.goto(page.url_serveur + "/")
    page.evaluate("fetch('/api/etiquettes/client',{method:'PUT',headers:{'X-Orchestrateur':'1','Content-Type':'application/json'},body:JSON.stringify({consigne:'Prudence'})})")
    reponse = page.evaluate("fetch('/api/etiquettes').then(r => r.json())")
    assert any(e["mot"] == "client" and e["consigne"] == "Prudence" for e in reponse["etiquettes"])
    assert not page.erreurs, page.erreurs
