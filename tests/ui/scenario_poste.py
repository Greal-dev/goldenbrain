"""Scénario de la réservation du poste (INV-POSTE-1) : bandeau « Poste réservé », tâche aux épreuves
lourdes « En attente du poste », puis démarrage dès que le poste est rendu (bouton « Libérer »)."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from conftest import deplier_infos
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_poste_reserve_met_en_attente_une_tache_lourde_puis_la_laisse_partir(page, serveur):
    projet(serveur, "C1-PosteLourd", {
        "po-titulaire": ("Titulaire du poste", ""),
        "po-lourde": ("Épreuves lourdes", "epreuves: lourdes\n"),
    })
    charger(page)
    expect(page.locator("#poste-reserve")).to_be_hidden()
    try:
        r = page.request.post(serveur.url + "/api/poste/reserver", headers=H,
                              data={"tache": "po-titulaire", "motif": "porte complète"})
        assert r.status == 200, r.text()
        bandeau = page.locator("#poste-reserve")
        deplier_infos(page)
        expect(bandeau).to_be_visible(timeout=5000)
        expect(bandeau).to_contain_text("Poste réservé par po-titulaire : porte complète")

        ligne(page, "Épreuves lourdes").click()
        expect(page.locator(".d-titre")).to_have_text("Épreuves lourdes")
        page.fill(".composer textarea", "[lent 4] lance la porte")
        page.press(".composer textarea", "Control+Enter")
        expect(page.locator(".d-une .etat")).to_have_text(
            "En attente du poste (réservé par Titulaire du poste)", timeout=5000)
        assert page.request.get(serveur.url + "/api/taches/po-lourde").json()["etat_execution"] == "en_file"

        page.locator("#poste-reserve button", has_text="Libérer").click()
        expect(bandeau).to_be_hidden(timeout=5000)
        expect(page.locator(".d-une .etat")).to_have_text("Séance de travail en cours", timeout=8000)
    finally:
        page.request.post(serveur.url + "/api/poste/liberer", headers=H, data={})
        page.request.post(serveur.url + "/api/taches/po-lourde/arret", headers=H)
    assert not page.erreurs, page.erreurs


def test_file_du_poste_rang_affiche_sur_la_tache_puis_le_suivant_obtient_le_poste(page, serveur):
    projet(serveur, "C1-PosteFile", {
        "pf-titulaire": ("Premier du poste", ""),
        "pf-suivante": ("Seconde tâche", ""),
    })
    charger(page)
    try:
        post = lambda chemin, data: page.request.post(serveur.url + "/api/poste/" + chemin, headers=H, data=data)
        assert post("reserver", {"tache": "pf-titulaire", "motif": "porte"}).status == 200
        r = post("reserver", {"tache": "pf-suivante", "attendre": True}).json()
        assert r["poste"] is None and r["rang"] == 1
        expect(page.locator("#poste-reserve")).to_contain_text("File : 1. pf-suivante", timeout=5000)
        deplier_infos(page)
        ligne(page, "Seconde tâche").click()
        expect(page.locator(".d-une .etat")).to_have_text("En attente du poste (rang 1)", timeout=5000)

        # Attendre la libération : la redemande partie avant elle trouverait le poste encore pris.
        with page.expect_response(lambda r: r.url.endswith("/api/poste/liberer")):
            page.locator("#poste-reserve button", has_text="Libérer").click()
        assert post("reserver", {"tache": "pf-suivante", "attendre": True}).json()["poste"]["tache"] == "pf-suivante"
        expect(page.locator("#poste-reserve")).to_contain_text("Poste réservé par pf-suivante", timeout=5000)
        expect(page.locator(".d-une .etat")).to_have_count(0, timeout=5000)  # plus d'attente affichée
    finally:
        post("liberer", {})
    assert not page.erreurs, page.erreurs
