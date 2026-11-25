"""Scénario des coupures réseau (INV-RESEAU-1, 2) : un tour échoue sur une erreur réseau, le bandeau « Réseau perdu »
paraît et la tâche passe « En attente du réseau » ; le point d'accès sondé se rouvre : le bandeau disparaît et l'agent
reprend de lui-même."""

import socket

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from conftest import deplier_infos
from playwright.sync_api import expect


def test_coupure_reseau_gele_l_agent_puis_il_reprend_au_retour(page, serveur):
    projet(serveur, "C1-ReseauCoupe", {"rc-agent": ("Agent sous coupure", "")})
    charger(page)
    expect(page.locator("#reseau-perdu")).to_be_hidden()
    ouvert = None
    try:
        ligne(page, "Agent sous coupure").click()
        page.fill(".composer textarea", "[reseau] travaille")
        page.press(".composer textarea", "Control+Enter")
        bandeau = page.locator("#reseau-perdu")
        deplier_infos(page, timeout=40000)
        expect(bandeau).to_be_visible()
        expect(bandeau).to_contain_text("Réseau perdu depuis")
        expect(bandeau).to_contain_text("1 agent en attente")
        expect(page.locator(".d-une .etat")).to_have_text("En attente du réseau")
        assert page.request.get(serveur.url + "/api/taches/rc-agent").json()["etat_execution"] == "attente_reseau"

        ouvert = socket.socket()  # le réseau revient : le point d'accès sondé répond
        ouvert.bind(("127.0.0.1", univers.PORT_SONDE))
        ouvert.listen()
        expect(bandeau).to_be_hidden(timeout=15000)
        expect(page.locator(".d-une .etat")).to_be_hidden(timeout=15000)
        assert page.request.get(serveur.url + "/api/taches/rc-agent").json()["etat_execution"] == "inactif"
    finally:
        if ouvert:
            ouvert.close()
    assert not page.erreurs, page.erreurs
