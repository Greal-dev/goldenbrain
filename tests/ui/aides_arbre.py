"""Aides communes aux scénarios d'arbre, de tâche et de glisser-déposer.

Rôle : écrire un petit projet dans le vault temporaire du serveur partagé, charger l'interface, déplier
l'arbre, retrouver une ligne par son titre exact (volet gauche ou cascade).
Frontières : n'écrit que sous `serveur.vault` ; chaque scénario donne à son projet un nom propre (le serveur
est partagé par toute la session pytest).
"""

from __future__ import annotations

import re
import shutil

import pytest

import univers

_ECRITS: list = []  # dossiers de projet écrits par le scénario en cours


def projet(serveur, nom: str, taches: dict[str, tuple[str, str]], casquette: str = "C1-Pro") -> None:
    """Écrit `Projets/<nom>/` : un contexte et des tâches `{fichier: (titre, extra_frontmatter)}`."""
    _ECRITS.append(serveur.vault / "Projets" / nom)
    titre = nom.split("-", 1)[-1]  # « C1-Alpha » : le dossier porte le préfixe de casquette, le titre non
    univers.ecrire(serveur.vault, f"Projets/{nom}/contexte.md",
                   f"---\ntype: contexte\ncasquette: {casquette}\nnom: {titre}\n---\n")
    for fichier, (titre, extra) in taches.items():
        univers.ecrire(serveur.vault, f"Projets/{nom}/taches/{fichier}.md", univers.tache(titre, extra=extra))


def exact(titre: str):
    return re.compile(rf"^{re.escape(titre)}$")


def charger(page, deplier: bool = True) -> None:
    # Le serveur est partagé : l'arbre grossit à chaque scénario. Fenêtre haute = toutes les lignes visibles,
    # donc des coordonnées de souris sûres pour les glissers à la main.
    page.set_viewport_size({"width": 1366, "height": 2600})
    page.goto(page.url_serveur + "/")
    page.wait_for_selector("#arbre .ligne")
    if deplier:
        deplier_tout(page)


def deplier_tout(page, racine: str = "#arbre .ligne") -> None:
    fermes = page.locator(f"{racine} .chev:not(.ouvert):not(.vide)")
    for _ in range(40):  # l'arbre se redessine à chaque dépliage : on relit le premier chevron fermé
        if not fermes.count():
            return
        fermes.first.click()


def ligne(page, titre: str):
    """Ligne du volet gauche dont le titre est exactement `titre`."""
    return page.locator("#arbre .ligne").filter(has=page.locator(".titre", has_text=exact(titre))).first


def rang(page, titre: str):
    """Ligne de la cascade (volet droit) dont le titre est exactement `titre`."""
    return page.locator(".casc-corps .cl").filter(has=page.locator(".c-t", has_text=exact(titre))).first


def niveau(loc) -> int:
    return int(loc.get_attribute("data-niveau"))


@pytest.fixture(autouse=True)
def nettoyer_vault():
    """Le serveur est partagé par toute la session : chaque scénario retire ses projets en sortant,
    pour ne laisser à ceux des autres familles ni lignes en trop ni état résiduel."""
    yield
    while _ECRITS:
        shutil.rmtree(_ECRITS.pop(), ignore_errors=True)
