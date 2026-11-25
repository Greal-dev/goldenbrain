"""Scénario de l'ordonnancement (INV-ORDO-1, INV-ORDO-2) : lien « a pour prérequis » posé par le
dialogue « Lier… », tâche « En attente de : … » puis partie seule quand le prérequis est fait ; rang
et motif d'un tour en file dans le bandeau et sur la tâche."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_prerequis_pose_attente_visible_puis_depart_et_rang_dans_la_file(page, serveur):
    projet(serveur, "C1-Ordo", {
        "or-a": ("Prérequis Ordo", ""),
        "or-b": ("Attend Ordo", ""),
        "or-c": ("Occupe Ordo", ""),
        "or-d": ("Suivante Ordo", "priorite: haute\n"),
    })
    charger(page)
    try:
        ligne(page, "Attend Ordo").click()
        expect(page.locator(".d-titre")).to_have_text("Attend Ordo")
        page.locator(".liens-carte button", has_text="Lier…").click()
        page.locator("dialog.dlg input[value=prerequis]").check()
        page.fill("#lier-q", "Prérequis Ordo")
        page.locator("#lier-liste li", has_text="Prérequis Ordo").first.dispatch_event("mousedown")
        page.locator("dialog.dlg button[type=submit]").click()
        expect(page.locator(".liens-carte .lien-groupe", has_text="Prérequis (à terminer avant)")).to_contain_text(
            "Prérequis Ordo")

        page.fill(".composer textarea", "[lent 20] travaille")
        page.press(".composer textarea", "Control+Enter")
        expect(page.locator(".d-une [data-id=main-phrase]")).to_contain_text("Prérequis Ordo", timeout=5000)
        expect(page.locator("#file [data-id=or-b]")).to_contain_text("En attente de : Prérequis Ordo", timeout=5000)

        r = page.request.post(serveur.url + "/api/taches/or-a/statut", headers=H, data={"statut": "fait"})
        assert r.status == 200, r.text()
        expect(page.locator(".d-une .main")).to_have_attribute("data-main", "ia", timeout=10000)

        # Rang : un seul créneau, occupé ; la tâche suivante attend à son rang, motif affiché.
        page.request.post(serveur.url + "/api/taches/or-b/arret", headers=H)
        page.request.put(serveur.url + "/api/simultanes", headers=H, data={"mode": "fixe", "simultanes_max": 1})
        page.request.post(serveur.url + "/api/taches/or-c/messages", headers=H, data={"texte": "[lent 30] occupe"})
        expect(page.locator("#tours")).to_contain_text("Occupe Ordo", timeout=5000)
        ligne(page, "Suivante Ordo").click()
        page.fill(".composer textarea", "à ton tour")
        page.press(".composer textarea", "Control+Enter")
        expect(page.locator(".d-une .main")).to_have_attribute("data-main", "file", timeout=5000)
        expect(page.locator("#file [data-id=or-d]")).to_contain_text("1ᵉʳ — message d'un humain")
    finally:
        for t in ("or-b", "or-c", "or-d"):
            page.request.post(serveur.url + f"/api/taches/{t}/arret", headers=H)
        page.request.put(serveur.url + "/api/simultanes", headers=H, data={"mode": "fixe", "simultanes_max": 2})
    assert not page.erreurs, page.erreurs
