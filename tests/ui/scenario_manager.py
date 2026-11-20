"""Volet « manager » (INV-MANAGER-1) : ouverture mémorisée, message envoyé à l'assistant, réponse à boutons
confirmée dans le volet (geste appliqué), fermeture ; plein écran avec retour sur téléphone.
Frontières : la réponse de l'assistant est simulée par `POST /api/telegram/question` (ce que fait `orch telegram`) ;
captures dans `GB_CAPTURES` si posé, sinon dans le dossier temporaire du test."""

import os
from pathlib import Path

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def _dossier(tmp_path) -> Path:
    return Path(os.environ.get("GB_CAPTURES") or tmp_path)


def test_volet_manager_message_geste_confirme_et_memoire(page, serveur, tmp_path):
    univers.ecrire(serveur.vault, "Projets/C1-Mgr/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: Mgr\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Mgr/taches/mgr-a.md", univers.tache("Tâche du manager"))
    page.goto(page.url_serveur + "/")
    page.wait_for_selector("#arbre .ligne", state="attached")  # interface prête (dictionnaire chargé, volet branché)
    volet = page.locator("#volet-manager")
    expect(volet).to_be_hidden()  # fermé par défaut : rien n'est chargé
    page.locator("#btn-manager").click()
    expect(volet).to_be_visible()
    expect(page.locator("#btn-manager")).to_have_attribute("aria-pressed", "true")

    saisie = page.locator("#mgr-saisie")
    saisie.fill("Passe la tâche du manager en bloqué")
    saisie.press("Enter")
    expect(volet.locator(".msg.user")).to_contain_text("Passe la tâche du manager en bloqué")
    expect(saisie).to_have_value("")

    # L'assistant répond par `orch telegram --tache … --geste …` : la question à boutons paraît dans le volet.
    tri = page.request.get(serveur.url + "/api/manager").json()["tache"]
    r = page.request.post(serveur.url + "/api/telegram/question", headers=H,
                          data={"tache": tri, "texte": "Je la passe en bloqué ?", "vise": "mgr-a", "geste": "statut=bloque"})
    assert r.ok, r.text()
    reponse = volet.locator(".msg.agent", has_text="Je la passe en bloqué ?")
    expect(reponse.locator(".mgr-boutons button")).to_have_count(2)
    page.screenshot(path=str(_dossier(tmp_path) / "manager-bureau.png"))
    reponse.get_by_role("button", name="Confirmer").click()
    expect(reponse.locator(".mgr-issue")).to_have_text("Fait : statut = bloque")
    expect(reponse.locator(".mgr-boutons")).to_have_count(0)
    assert "statut: bloque" in (serveur.vault / "Projets/C1-Mgr/taches/mgr-a.md").read_text("utf-8")

    # État mémorisé : rouvert au rechargement, puis fermé.
    page.reload()
    expect(volet).to_be_visible()
    expect(volet.locator(".mgr-issue")).to_have_text("Fait : statut = bloque")
    volet.locator(".mgr-fermer").click()
    expect(volet).to_be_hidden()
    page.reload()
    expect(volet).to_be_hidden()
    assert not page.erreurs


def test_volet_manager_plein_ecran_sur_telephone(navigateur, serveur, tmp_path):
    ctx = navigateur.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        page.goto(serveur.url + "/")
        page.wait_for_selector("#arbre .ligne", state="attached")
        bouton = page.locator("#btn-manager")
        expect(bouton).to_be_visible()
        bouton.tap()
        volet = page.locator("#volet-manager")
        expect(volet.locator(".mgr-aide, .msg").first).to_be_visible()  # fil chargé avant la capture
        boite = volet.bounding_box()
        assert boite["width"] >= 410 and boite["height"] >= 800  # plein écran
        page.screenshot(path=str(_dossier(tmp_path) / "manager-telephone.png"))
        volet.locator(".mgr-retour").tap()
        expect(volet).to_be_hidden()
        assert not erreurs
    finally:
        ctx.close()
