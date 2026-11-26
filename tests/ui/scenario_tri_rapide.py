"""Scénario du « Tri rapide » des décisions : une carte à la fois, geste à la touche (A accepte, R refuse,
→ passe, Échap quitte), sans recharger la liste ; fin de file « Tout est trié ».
Le serveur est partagé : d'autres cartes peuvent précéder les nôtres, on les passe."""

import univers
from aides_arbre import _ECRITS, nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect
from scenario_decisions import _a_valider

H = {"X-Orchestrateur": "1"}


def _monde(serveur):
    _ECRITS.append(serveur.vault / "Projets" / "C1-Decis")  # retiré en sortie : un renvoi relance l'agent (en-cours) et fausserait les filtres d'autres scénarios
    univers.ecrire(serveur.vault, "Projets/C1-Decis/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Decis\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Decis/taches/dc-f1.md", univers.tache("Fermable Un Decis"))
    _a_valider(serveur, "dc-v1", "Validation Un Decis", "livrable-un")
    _a_valider(serveur, "dc-v2", "Validation Deux Decis", "livrable-deux")


def _etat(page, serveur, tache):
    return page.request.get(serveur.url + f"/api/taches/{tache}").json()["statut"]


def _jusqu_a(page, tri, titre):
    """Passe (→) les cartes jusqu'à celle du titre donné."""
    for _ in range(200):
        if tri.locator(".tri-tete b").inner_text() == titre:
            return
        compte = tri.locator(".tri-compte").inner_text()
        page.keyboard.press("ArrowRight")
        expect(tri.locator(".tri-compte")).not_to_have_text(compte)
    raise AssertionError(f"carte « {titre} » introuvable")


def test_tri_rapide_accepte_refuse_passe_et_quitte(page, serveur):
    _monde(serveur)
    p = page.request.post(serveur.url + "/api/propositions", headers=H, data={
        "type": "perimetre", "tache": "dc-f1", "valeur": "Seulement le volet A", "de": "agent", "motif": "recentrer"}).json()
    assert p["etat"] == "en_attente"
    page.goto(page.url_serveur + "/#decisions")
    page.click("#dc-tri")
    tri = page.locator("dialog.tri")
    expect(tri).to_be_visible()
    expect(tri.locator(".tri-compte")).to_contain_text("1 / ")
    # A valide la 1re de nos validations, R refuse notre proposition ; tout le reste, y compris dc-v2, est passé (→).
    gestes = {"Validation Un Decis": "a", "Fermable Un Decis": "r"}
    for _ in range(200):
        if tri.locator(".tri-fini").count():
            break
        compte = tri.locator(".tri-compte").inner_text()
        page.keyboard.press(gestes.get(tri.locator(".tri-tete b").inner_text(), "ArrowRight"))
        expect(tri.locator(".tri-compte, .tri-fini").first).not_to_have_text(compte)  # la carte suivante n'apparaît qu'une fois le geste fait
    expect(tri).to_contain_text("Tout est trié")
    assert _etat(page, serveur, "dc-v1") == "cloture"
    assert _etat(page, serveur, "dc-v2") == "fait"  # passée, pas validée
    etats = {x["n"]: x["etat"] for x in page.request.get(serveur.url + "/api/propositions").json()}
    assert etats[p["n"]] == "refusee"
    page.click("#tri-fermer")
    expect(tri).to_have_count(0)
    expect(page.locator(".dc-validation .dc-titre", has_text="Validation Un Decis")).to_have_count(0, timeout=5000)

    # Échap quitte ; les boutons font les mêmes gestes que les touches.
    page.click("#dc-tri")
    expect(tri).to_be_visible()
    page.keyboard.press("Escape")
    expect(tri).to_have_count(0)
    page.click("#dc-tri")
    _jusqu_a(page, tri, "Validation Deux Decis")
    tri.get_by_role("button", name="Passer (→)").click()
    for _ in range(200):
        if tri.locator(".tri-fini").count():
            break
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    expect(tri).to_have_count(0)
    assert not page.erreurs, page.erreurs


def test_tri_rapide_refus_d_une_validation_demande_un_motif(page, serveur):
    _monde(serveur)
    page.goto(page.url_serveur + "/#decisions")
    page.click("#dc-tri")
    tri = page.locator("dialog.tri")
    _jusqu_a(page, tri, "Validation Un Decis")
    page.keyboard.press("r")
    champ = tri.locator("input.tri-champ")
    expect(champ).to_be_focused()
    page.keyboard.press("a")  # dans le champ, la lettre s'écrit : aucun geste
    expect(champ).to_have_value("a")
    champ.fill("à refaire [lent 20]")  # tour lent : l'agent reste en cours le temps de la vérification
    champ.press("Enter")
    expect(champ).to_have_count(0)
    for _ in range(100):  # le renvoi a relancé l'agent de la tâche
        if page.request.get(serveur.url + "/api/taches/dc-v1").json()["etat_execution"] == "en_cours":
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("le renvoi n'a pas relancé la tâche")
    page.request.post(serveur.url + "/api/taches/dc-v1/arret", headers=H)
    assert _etat(page, serveur, "dc-v2") == "fait"
    assert not page.erreurs, page.erreurs
