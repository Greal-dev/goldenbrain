"""Scénarios du demi-verrou (INV-VERROU-1) : repère « IA au travail » en direct, « IA : n » sur les ancêtres,
confirmation d'un geste sur une tâche occupée (« Non » ne change rien, « Continuer quand même » l'applique)."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def _ouvrir_et_lancer(page, serveur, nom, taches, titre, message):
    projet(serveur, nom, taches)
    charger(page)
    ligne(page, titre).click()
    expect(page.locator(".d-titre")).to_have_text(titre)
    page.fill(".composer textarea", message)
    page.press(".composer textarea", "Control+Enter")


def test_repere_ia_en_direct_et_compte_des_ancetres(page, serveur):
    _ouvrir_et_lancer(page, serveur, "C1-IaTravail",
                      {"ia-mere": ("Mère IA", ""), "ia-fille": ("Fille IA", 'parent: "[[ia-mere]]"\n')},
                      "Fille IA", "[lent 4] travaille")
    repere = ligne(page, "Fille IA").locator("[data-ia='1']")
    expect(repere).to_be_visible(timeout=5000)
    assert "faux" in repere.get_attribute("title") and "depuis" in repere.get_attribute("title")
    expect(page.locator(".d-titre [data-ia='1']")).to_be_visible()
    expect(ligne(page, "Mère IA").locator(".ia-compte")).to_have_text("IA : 1")
    expect(ligne(page, "IaTravail").locator(".ia-compte")).to_have_text("IA : 1")
    # Fin du tour : le repère disparaît sans rechargement.
    expect(repere).to_have_count(0, timeout=15000)
    expect(page.locator(".d-titre [data-ia='1']")).to_have_count(0)
    expect(ligne(page, "Mère IA").locator(".ia-compte")).to_have_count(0)
    assert not page.erreurs, page.erreurs


def test_statut_d_une_tache_occupee_demande_confirmation(page, serveur):
    _ouvrir_et_lancer(page, serveur, "C1-IaStatut", {"ia-statut": ("Statut IA", "")}, "Statut IA",
                      "[lent 60] travaille longtemps")
    expect(page.locator(".d-titre [data-ia='1']")).to_be_visible(timeout=5000)
    statut = page.locator(".d-une select[aria-label='Statut']")
    expect(statut).to_have_value("en-cours")
    try:
        statut.select_option("bloque")
        dlg = page.locator("dialog.dlg")
        expect(dlg).to_contain_text("Un agent travaille sur « Statut IA » depuis")
        non = dlg.locator("button", has_text="Non")
        expect(non).to_be_focused()
        non.click()
        expect(dlg).to_have_count(0)
        expect(page.locator(".d-une select[aria-label='Statut']")).to_have_value("en-cours")
        assert page.request.get(serveur.url + "/api/taches/ia-statut").json()["statut"] == "en-cours"
        assert not page.locator("#banniere:visible").count()  # « Non » : aucune erreur affichée

        page.locator(".d-une select[aria-label='Statut']").select_option("bloque")
        with page.expect_response(lambda r: r.url.endswith("/ia-statut/statut") and r.status == 200):
            page.locator("dialog.dlg button", has_text="Continuer quand même").click()
        expect(page.locator(".d-une select[aria-label='Statut']")).to_have_value("bloque")
        assert page.request.get(serveur.url + "/api/taches/ia-statut").json()["statut"] == "bloque"
    finally:
        page.request.post(serveur.url + "/api/taches/ia-statut/arret", headers=H)
    # Le navigateur consigne les deux 409 attendus (le demi-verrou) : seules erreurs admises.
    assert all("409" in e for e in page.erreurs), page.erreurs
