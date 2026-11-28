"""Arbre : « ＋ Nouveau projet » / « ＋ Nouvelle tâche » en pied de liste au survol (INV-ARBRE-3) ;
le dialogue « Nouvelle tâche » tient dans la fenêtre, bouton « Créer » visible."""

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import _ECRITS, charger, ligne

CAS = "Casquettes/C7-Ajout"


def _univers(serveur):
    _ECRITS.append(serveur.vault / CAS)  # le projet créé y naît aussi : tout part au nettoyage
    univers.ecrire(serveur.vault, f"{CAS}/Ecrits-aj/contexte.md", "---\ntype: contexte\ncasquette: C7\nnom: Écrits AJ\n---\n")
    univers.ecrire(serveur.vault, f"{CAS}/Ecrits-aj/taches/aj-mere.md", univers.tache("Mère AJ"))
    univers.ecrire(serveur.vault, f"{CAS}/Ecrits-aj/taches/aj-fille.md", univers.tache("Fille AJ", extra="parent: aj-mere\n"))


def _pied(page, rangee):
    """Survole une ligne : le pied de SA liste (et lui seul) se montre."""
    rangee.hover()
    return page.locator("#arbre .pied.vu")


def test_nouveau_projet_sous_une_casquette(page, serveur):
    _univers(serveur)
    charger(page)
    n_lignes = page.locator("#arbre .ligne").count()
    pied = _pied(page, ligne(page, "C7"))
    assert pied.count() == 1 and pied.locator("[data-ajout]").all_inner_texts() == ["＋ Nouveau projet"]
    assert pied.get_attribute("data-pour") == "casquette:casquette:C7"  # le pied de la liste survolée, seul
    assert page.locator("#arbre .ligne").count() == n_lignes  # le pied n'est pas un nœud
    pied.locator("[data-ajout=projet]").click()
    page.fill("dialog[open] input[name=nom]", "Roman AJ")
    with page.expect_response(lambda r: r.url.endswith("/api/conteneurs") and r.request.method == "POST") as rep:
        page.click("dialog[open] .primaire")
    assert rep.value.status == 201 and rep.value.json()["id"] == f"{CAS}/Roman-AJ"
    page.wait_for_selector("#arbre .ligne.t-conteneur .titre:text-is('Roman AJ')")
    assert (serveur.vault / CAS / "Roman-AJ/contexte.md").is_file()
    # Projet neuf, vide : un clic propose sa première tâche, emplacement pré-choisi.
    ligne(page, "Roman AJ").click()
    assert page.locator("dialog[open] select[name=conteneur]").input_value() == f"{CAS}/Roman-AJ"
    assert not page.erreurs, page.erreurs


def test_nouveau_projet_sous_une_casquette_dont_les_projets_sont_ailleurs(page, serveur):
    # Régression (28/11) : casquette sans projet sous « Casquettes/ » mais avec son propre dossier de tâches →
    # la création s'arrêtait avant tout envoi ; le projet naît désormais dans ce dossier.
    seul = "Casquettes/C8-Seul"
    _ECRITS.extend([serveur.vault / seul, serveur.vault / "Projets/C8-Ailleurs"])
    univers.ecrire(serveur.vault, f"{seul}/contexte.md", "---\ntype: contexte\ncasquette: C8\nnom: Seul C8\n---\n")
    univers.ecrire(serveur.vault, f"{seul}/taches/c8-t.md", univers.tache("Tâche C8", extra="casquette: C8\n"))
    univers.ecrire(serveur.vault, "Projets/C8-Ailleurs/contexte.md", "---\ntype: contexte\ncasquette: C8\nnom: Ailleurs C8\n---\n")
    charger(page)
    _pied(page, ligne(page, "C8")).locator("[data-ajout=projet]").click()
    page.fill("dialog[open] input[name=nom]", "Neuf C8")
    with page.expect_response(lambda r: r.url.endswith("/api/conteneurs") and r.request.method == "POST") as rep:
        page.click("dialog[open] .primaire")
    assert rep.value.status == 201 and rep.value.json()["id"] == f"{seul}/Neuf-C8", rep.value.text()
    page.wait_for_selector("#arbre .ligne.t-conteneur .titre:text-is('Neuf C8')")
    assert not page.erreurs, page.erreurs


def test_nouvelle_tache_sous_un_projet_et_une_tache_groupe(page, serveur):
    _univers(serveur)
    charger(page)
    pied = _pied(page, ligne(page, "Mère AJ"))  # ligne directe du projet : pied du projet
    assert pied.locator("[data-ajout]").all_inner_texts() == ["＋ Nouveau projet", "＋ Nouvelle tâche"]
    pied.locator("[data-ajout=tache]").click()
    assert page.locator("dialog[open] select[name=conteneur]").input_value() == f"{CAS}/Ecrits-aj"
    page.keyboard.press("Escape")
    pied = _pied(page, ligne(page, "Fille AJ"))  # sous-tâche : pied de la tâche-groupe
    assert pied.locator("[data-ajout]").all_inner_texts() == ["＋ Nouvelle tâche"]
    pied.locator("[data-ajout=tache]").click()
    assert page.locator("dialog[open] input[name=sous]").input_value() == "Mère AJ"
    page.fill("dialog[open] input[name=titre]", "Rédiger la préface du recueil")
    with page.expect_response(lambda r: r.url.endswith("/api/taches") and r.request.method == "POST") as rep:
        page.click("dialog[open] .primaire")
    assert rep.value.status == 201, rep.value.text()
    assert rep.value.json()["fil"][-1]["id"] == "aj-mere"  # rangée sous la tâche-groupe
    assert not page.erreurs, page.erreurs


def test_dialogue_nouvelle_tache_tient_dans_la_fenetre(page, serveur):
    charger(page, deplier=False)
    for largeur, hauteur in ((1366, 717), (1366, 600), (390, 844)):
        page.set_viewport_size({"width": largeur, "height": hauteur})
        page.click("#btn-nouvelle")
        page.select_option("dialog[open] select[name=conteneur]", label="＋ Nouveau projet…")  # le plus haut
        page.wait_for_selector("[data-id=nouveau-groupe]:not([hidden])")
        dlg = page.locator("dialog[open]").bounding_box()
        btn = page.locator("dialog[open] .dlg-actions .primaire").bounding_box()
        assert dlg["y"] <= 16, (largeur, hauteur, dlg)  # ancré en haut
        assert dlg["y"] + dlg["height"] <= hauteur and btn["y"] + btn["height"] <= hauteur, (largeur, hauteur, btn)
        page.keyboard.press("Escape")
        page.wait_for_selector("dialog[open]", state="detached")
    assert not page.erreurs, page.erreurs
