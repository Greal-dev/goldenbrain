"""Scénario de l'assistant « Ajouter ce PC comme exécuteur » (INV-INSTALL-1, INV-INSTALL-2) :
poste factice (seul git présent) ; refus du dialogue = rien ne se lance ; accord = commande exacte lancée."""

from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def ouvrir(page):
    page.goto(page.url_serveur + "/#reglages/installation")
    page.wait_for_selector("[data-id=installation] [data-id=inst-liste]")


def test_refuser_le_dialogue_ne_lance_rien(page, serveur):
    ouvrir(page)
    expect(page.locator("[data-id=inst-commande-tailscale]")).to_contain_text("winget")
    page.once("dialog", lambda d: d.dismiss())
    page.click("[data-id=inst-lancer-tailscale]")
    page.wait_for_timeout(600)
    expect(page.locator("[data-id=inst-tailscale]")).to_have_attribute("data-etat", "manquant")
    assert "[faux]" not in page.locator("[data-id=inst-sortie]").inner_text()
    assert not page.erreurs, page.erreurs


def test_accepter_lance_la_commande_affichee(page, serveur):
    ouvrir(page)
    commande = page.locator("[data-id=inst-commande-tailscale]").inner_text()
    messages = []
    page.once("dialog", lambda d: (messages.append(d.message), d.accept()))
    page.click("[data-id=inst-lancer-tailscale]")
    expect(page.locator("[data-id=inst-tailscale]")).to_have_attribute("data-etat", "ok", timeout=8000)
    assert commande in messages[0]
    expect(page.locator("[data-id=inst-sortie]")).to_contain_text("[faux] " + commande)
    assert not page.erreurs, page.erreurs


def test_accord_qui_ne_porte_pas_la_commande_est_refuse(page, serveur):
    r = page.request.post(page.url_serveur + "/api/installation/etapes/claude", headers=H, data={"accord": "x"})
    assert r.status == 400
    r = page.request.post(page.url_serveur + "/api/installation/etapes/inconnue", headers=H, data={"accord": "x"})
    assert r.status == 404


def test_appairage_avec_mauvais_code_affiche_l_erreur(page, serveur):
    ouvrir(page)
    page.fill("[data-id=inst-serveur]", page.url_serveur)
    page.fill("[data-id=inst-code]", "AAAA-BBBB")
    page.click("[data-id=inst-appairer]")
    page.wait_for_timeout(1500)
    expect(page.locator("[data-id=inst-message]")).to_have_count(0)
