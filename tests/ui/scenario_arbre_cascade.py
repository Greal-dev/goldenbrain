"""Scénarios d'arbre (volet gauche) et de cascade (volet droit) : hiérarchie, replis, clavier, bascule, filtres."""

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, deplier_tout, ligne, niveau, projet, rang
from playwright.sync_api import expect


def _projet_arbre(serveur):
    projet(serveur, "C1-ArbreCasc", {
        "ac-racine": ("Racine AC", ""),
        "ac-fille": ("Fille AC", 'parent: "[[ac-racine]]"\n'),
        "ac-petite": ("Petite AC", "parent: ac-fille\n"),
        "ac-autre": ("Autre AC", ""),
    })
    univers.ecrire(serveur.vault, "Projets/C1-ArbreCasc/taches/ac-close.md",
                   univers.tache("Close AC", statut="fait"))


def test_arbre_hierarchie_et_replis(page, serveur):
    _projet_arbre(serveur)
    charger(page)
    racine, fille, petite = ligne(page, "Racine AC"), ligne(page, "Fille AC"), ligne(page, "Petite AC")
    assert niveau(racine) < niveau(fille) < niveau(petite)
    assert racine.get_attribute("aria-expanded") == "true"
    racine.locator(".chev").click()  # replier : les descendantes disparaissent
    expect(ligne(page, "Racine AC")).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#arbre .ligne", has_text="Fille AC")).to_have_count(0)
    expect(page.locator("#arbre .ligne", has_text="Petite AC")).to_have_count(0)
    ligne(page, "Racine AC").locator(".chev").click()  # déplier : elles reviennent
    expect(page.locator("#arbre .ligne", has_text="Petite AC")).to_have_count(1)
    assert not page.erreurs, page.erreurs


def test_arbre_clavier(page, serveur):
    _projet_arbre(serveur)
    charger(page)
    ligne(page, "Racine AC").focus()
    page.keyboard.press("ArrowLeft")  # replie la racine
    expect(ligne(page, "Racine AC")).to_have_attribute("aria-expanded", "false")
    page.keyboard.press("ArrowRight")  # la redéplie
    expect(ligne(page, "Racine AC")).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("ArrowRight")  # entre dans ses enfants
    expect(ligne(page, "Fille AC")).to_be_focused()
    page.keyboard.press("ArrowDown")  # la fille est dépliée : la flèche basse descend à sa petite
    expect(ligne(page, "Petite AC")).to_be_focused()
    page.keyboard.press("Enter")  # ouvre la tâche dans le volet droit
    expect(page.locator(".d-titre")).to_have_text("Petite AC")
    assert not page.erreurs, page.erreurs


def test_arbre_ouvre_la_tache_et_fil_d_ariane(page, serveur):
    _projet_arbre(serveur)
    charger(page)
    ligne(page, "Petite AC").locator(".titre").click()  # le centre de la ligne tombe sur la pastille de statut (menu)
    expect(page.locator(".d-titre")).to_have_text("Petite AC")
    expect(ligne(page, "Petite AC")).to_have_attribute("aria-selected", "true")
    expect(page.locator(".d-tete nav.fil")).to_contain_text("Fille AC")
    expect(page.locator(".d-rattache")).to_contain_text("Fille AC")
    expect(page.locator(".d-rattache .badge-type")).to_have_text("tâche mère")
    assert not page.erreurs, page.erreurs


def test_arbre_bascule_ouvertes_toutes(page, serveur):
    _projet_arbre(serveur)
    charger(page)
    assert ligne(page, "Autre AC").count() == 1
    expect(page.locator("#arbre .ligne", has_text="Close AC")).to_have_count(0)
    page.click("#vue-toutes")
    expect(page.locator("#vue-toutes")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#arbre .ligne", has_text="Close AC")).to_have_count(1)
    page.click("#vue-ouvertes")
    expect(page.locator("#arbre .ligne", has_text="Close AC")).to_have_count(0)
    assert not page.erreurs, page.erreurs


def test_cascade_projet_portee_et_replis(page, serveur):
    _projet_arbre(serveur)
    charger(page)
    ligne(page, "ArbreCasc").click()  # un projet : sa cascade
    expect(page.locator(".casc-titre")).to_have_text("ArbreCasc")
    expect(page.locator(".casc-fil")).to_contain_text("Ensemble")
    for titre in ("Racine AC", "Fille AC", "Petite AC", "Autre AC"):
        expect(page.locator(".casc-corps .cl .c-t", has_text=titre)).to_have_count(1)
    expect(page.locator(".casc-corps .cl .c-t", has_text="Close AC")).to_have_count(0)
    assert niveau(rang(page, "Racine AC")) < niveau(rang(page, "Petite AC"))
    page.get_by_role("button", name="Tout replier").click()
    expect(page.locator(".casc-corps .cl .c-t", has_text="Petite AC")).to_have_count(0)
    expect(page.locator(".casc-corps .cl .c-t", has_text="Racine AC")).to_have_count(1)
    page.get_by_role("button", name="Tout déplier").click()
    expect(page.locator(".casc-corps .cl .c-t", has_text="Petite AC")).to_have_count(1)
    page.get_by_role("button", name="← Ensemble").click()  # retour à la vue d'ensemble
    expect(page.locator(".casc-titre")).to_have_text("Vue d’ensemble")
    assert not page.erreurs, page.erreurs


def test_cascade_filtre_par_statut_et_ouverture(page, serveur):
    _projet_arbre(serveur)
    univers.ecrire(serveur.vault, "Projets/C1-ArbreCasc/taches/ac-bloquee.md",
                   univers.tache("Bloquée AC", statut="bloque"))
    charger(page)
    ligne(page, "ArbreCasc").click()
    expect(page.locator(".casc-titre")).to_have_text("ArbreCasc")
    page.locator(".chip-st", has_text="Bloquée").click()  # filtre cumulable : seules les tâches de ce statut
    expect(page.locator(".chip-st", has_text="Bloquée")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".casc-corps .cl:not(.ctx) .c-t")).to_have_text(["Bloquée AC"])
    page.get_by_role("button", name="effacer le filtre").click()
    expect(page.locator(".casc-corps .cl .c-t", has_text="Autre AC")).to_have_count(1)
    rang(page, "Fille AC").locator(".c-t").click()  # un clic sur une tâche l'ouvre
    expect(page.locator(".d-titre")).to_have_text("Fille AC")
    assert not page.erreurs, page.erreurs
