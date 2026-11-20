"""Rapprochement avant création : suggestions au fil de la saisie, « Compléter celle-ci », « Créer quand même »."""

from tests.ui import univers


def test_suggestions_et_completer(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C2-Beta/taches/rapp-porte.md",
                   univers.tache("Refondre la grille tarifaire des cautions"))
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.click("#btn-nouvelle")
    page.fill("input[name=titre]", "Refondre la grille tarifaire cautions")
    page.wait_for_selector("[data-id=proches] .proche")  # temporisation puis liste
    assert "Refondre la grille tarifaire des cautions" in page.locator("[data-id=proches]").inner_text()
    with page.expect_response(lambda r: "/completer" in r.url and r.request.method == "POST") as rep:
        page.click("[data-completer=rapp-porte]")
    assert rep.value.status == 202
    mesure = page.evaluate("fetch('/api/rapprochement/mesure').then(r => r.json())")
    assert mesure["complements"] >= 1
    assert not page.erreurs, page.erreurs


def test_creer_quand_meme_apres_refus(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C2-Beta/taches/rapp-bail.md",
                   univers.tache("Régulariser quittances annuelles locataires"))
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.click("#btn-nouvelle")
    page.fill("input[name=titre]", "Régulariser quittances annuelles locataires")
    page.click(".dlg-actions .primaire")  # Créer : correspondance forte → refus doux
    page.wait_for_selector("[data-id=doublon] .proche")
    with page.expect_response(lambda r: r.url.endswith("/api/taches") and r.request.method == "POST") as rep:
        page.click(".dlg-actions .primaire")  # Créer quand même
    assert rep.value.status == 201
    inattendues = [e for e in page.erreurs if "409" not in e]  # le refus doux est un 409 voulu
    assert not inattendues, inattendues
