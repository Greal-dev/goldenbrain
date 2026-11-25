"""Scénario « statut lisible, filtres et regroupements » du volet gauche : pastille de statut courte sur
chaque ligne, filtres combinés (statut, priorité, échéance) avec compteur, regroupement par statut,
mémoire du navigateur et usage au clavier."""

import re

import aides_arbre
import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne
from playwright.sync_api import expect

TACHES = {  # fichier: (titre, statut, extra)
    "fi-a": ("Alpha Filtre", "en-cours", "priorite: haute\n"),
    "fi-b": ("Beta Filtre", "a-faire", "priorite: basse\necheance: 2020-01-01\n"),
    "fi-c": ("Gamma Filtre", "bloque", ""),
    "fi-d": ("Delta Filtre", "retour-humain", "priorite: haute\n"),
}


def poser(serveur):
    dossier = serveur.vault / "Projets" / "C1-Filtres"
    aides_arbre._ECRITS.append(dossier)
    univers.ecrire(serveur.vault, "Projets/C1-Filtres/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Filtres\n---\n")
    for f, (titre, statut, extra) in TACHES.items():
        univers.ecrire(serveur.vault, f"Projets/C1-Filtres/taches/{f}.md", univers.tache(titre, statut, extra))


def titres(page):
    return page.locator("#arbre .ligne.t-tache .titre").all_inner_texts()


def mes(page):
    return [t for t in titres(page) if t.endswith("Filtre")]


def test_statut_visible_filtres_combines_groupement_et_memoire(page, serveur):
    poser(serveur)
    charger(page)
    # Statut lisible sans survol, distinct du repère « IA au travail ».
    assert ligne(page, "Alpha Filtre").locator(".badge-st").inner_text() == "en cours"
    assert ligne(page, "Beta Filtre").locator(".badge-st").inner_text() == "à faire"
    assert ligne(page, "Gamma Filtre").locator(".badge-st").inner_text() == "bloquée"
    assert ligne(page, "Delta Filtre").locator(".badge-st").inner_text() == "à moi"

    page.locator("#filtres summary").click()
    # Statut multiple + compteur.
    page.locator('.f-st[data-statut="en-cours"]').click()
    page.locator('.f-st[data-statut="bloque"]').click()
    assert sorted(mes(page)) == ["Alpha Filtre", "Gamma Filtre"]
    expect(page.locator("#f-compte")).to_have_text(re.compile(r"^2 sur \d+$"))
    # Combiné avec la priorité : l'intersection seule demeure.
    page.select_option("#f-priorite", "haute")
    assert mes(page) == ["Alpha Filtre"]
    expect(page.locator("#f-compte")).to_have_text(re.compile(r"^1 sur \d+$"))
    # Mémoire du navigateur : le filtre survit au rechargement.
    page.reload()
    page.wait_for_selector("#arbre .ligne")
    assert mes(page) == ["Alpha Filtre"]
    # Réinitialiser, puis échéance « en retard » et « à moi ».
    page.locator("#filtres summary").click()
    page.locator("#f-raz").click()
    page.select_option("#f-echeance", "retard")
    assert mes(page) == ["Beta Filtre"]
    page.locator("#f-raz").click()
    page.locator("#f-amoi").check()
    assert mes(page) == ["Delta Filtre"]
    page.locator("#f-raz").click()

    # Regroupement par statut : un en-tête par statut, tâches dessous.
    page.select_option("#f-groupe", "statut")
    entetes = page.locator("#arbre .ligne.t-groupe .titre").all_inner_texts()
    assert {"en cours", "à faire", "bloquée", "à moi"} <= set(entetes), entetes
    assert entetes.index("en cours") < entetes.index("bloquée")
    # Tri priorité puis échéance, groupement par priorité : « Haute » avant « Basse ».
    page.select_option("#f-groupe", "priorite")
    page.select_option("#f-tri", "priorite")
    entetes = page.locator("#arbre .ligne.t-groupe .titre").all_inner_texts()
    assert entetes.index("Haute") < entetes.index("Basse"), entetes

    # Clavier : le focus reste sur le champ modifié après redessin de la barre.
    page.focus("#f-groupe")
    page.keyboard.press("ArrowUp")
    expect(page.locator("#f-groupe")).to_be_focused()
    page.locator("#f-raz").click()
    assert not page.erreurs, page.erreurs
