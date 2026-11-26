"""Vue par étiquette (INV-ETIQUETTE-4) : adresse directe, tâches et routine réunies, « Lancer toutes » exécute les routines,
clic sur un titre ouvre la tâche, clic sur une puce de l'arbre ouvre la vue, commande de la palette."""

import json

import univers
from aides_arbre import _ECRITS, nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1", "Content-Type": "application/json"}


def _monde(page, serveur):
    _ECRITS.append(serveur.vault / "Projets" / "C1-VueEtiq")  # retiré en sortie : rien ne fuit vers les filtres d'autres scénarios
    univers.ecrire(serveur.vault, "Projets/C1-VueEtiq/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: VueEtiq\n---\n")
    for nom, titre in (("ve-a", "Relevés Alpha Etiq"), ("ve-b", "Relevés Beta Etiq")):
        univers.ecrire(serveur.vault, f"Projets/C1-VueEtiq/taches/{nom}.md", univers.tache(titre, extra="etiquettes: [vuebanque]\n"))
    r = page.request.post(serveur.url + "/api/routines", headers=H, data=json.dumps({
        "titre": "Routine Gamma Etiq", "consigne": "Contrôle.", "programme": "chaque jour 08:00", "conteneur": "Projets/C1-VueEtiq"}))
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    page.request.post(serveur.url + f"/api/taches/{rid}/etiquettes", headers=H, data=json.dumps({"ajouter": ["vuebanque"]}))
    return rid


def test_vue_etiquette_liste_lance_et_ouvre(page, serveur):
    rid = _monde(page, serveur)
    page.goto(page.url_serveur + "/#etiquette=vuebanque")
    page.reload()
    expect(page.locator('[data-id="etiq-ligne"]')).to_have_count(3)
    expect(page.locator('[data-id="etiq-ligne"]').first).to_contain_text("Routine Gamma Etiq")  # routines d'abord
    expect(page.locator('[data-id="etiq-routine"]')).to_contain_text("chaque jour 08:00")
    bouton = page.locator('[data-id="etiq-tout-lancer"]')
    expect(bouton).to_contain_text("(1)")
    bouton.click()
    expect(page.locator('[data-id="etiq-bilan"]')).to_contain_text("1 lancée", timeout=5000)
    historique = page.request.get(serveur.url + f"/api/routines/{rid}").json()["historique"]
    assert historique and historique[0]["origine"] == "manuelle"  # exécution soumise par la vue
    page.locator('[data-id="etiq-titre"]', has_text="Relevés Alpha Etiq").click()
    expect(page).to_have_url(page.url_serveur + "/#t=ve-a")
    assert not page.erreurs, page.erreurs


def test_puce_de_l_arbre_et_palette_ouvrent_la_vue(page, serveur):
    _monde(page, serveur)
    page.goto(page.url_serveur + "/")
    page.reload()
    page.wait_for_selector("#arbre .ligne")
    page.keyboard.press("Control+k")
    page.fill(".pal-champ", "vuebanque")
    page.locator('[data-id="palette-commande"]', has_text="Étiquette : vuebanque").click()
    expect(page).to_have_url(page.url_serveur + "/#etiquette=vuebanque")
    expect(page.locator('[data-id="etiq-ligne"]')).to_have_count(3)
    page.locator('[data-id="etiq-titre"]', has_text="Relevés Beta Etiq").click()
    expect(page).to_have_url(page.url_serveur + "/#t=ve-b")
    assert not page.erreurs, page.erreurs
