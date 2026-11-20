"""Scénario du chat de projet : sélection d'un projet → sa conversation ; un message → tâche enfant visible."""

import univers

PROJET = "Projets/C1-Pilote"


def test_conversation_du_projet_cree_une_tache_visible_dans_l_arbre(page, serveur):
    univers.ecrire(serveur.vault, f"{PROJET}/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Projet piloté\n---\n")
    univers.ecrire(serveur.vault, f"{PROJET}/taches/existante.md", univers.tache("Tâche existante"))
    page.goto(page.url_serveur + "/")
    page.click(".ligne.t-conteneur >> text=Projet piloté")
    bouton = page.locator("[data-pilotage]")
    bouton.wait_for()
    bouton.click()
    # « [lent 3] » : le transcript du harnais factice ne rend jamais le message de l'utilisateur ; il ne
    # s'affiche que tant que le tour dure (INV-EXEC-7). Sans ce délai le tour (≈ 0,5 s) peut finir avant
    # la première lecture de la conversation, et le message n'apparaît jamais (porte rouge, 20/11).
    page.fill(".casc-chat textarea", f"Crée la recette. [lent 3] [creer Recette pilotée | {PROJET}]")
    page.click(".casc-chat button[type=submit]")
    # Le panneau de tâche s'ouvre sur la conversation du projet, née de ce premier message.
    page.wait_for_selector(".d-titre >> text=Pilotage — Projet piloté")
    page.wait_for_selector(".msg >> text=Crée la recette.")
    # L'agent a créé la tâche par `orch creer` : elle paraît dans l'arbre, la conversation non.
    for _ in range(100):
        if list((serveur.vault / PROJET / "taches").glob("*recette-pilotee*")):
            break
        page.wait_for_timeout(200)  # processus `orch` : rien à attendre à l'écran avant sa fin
    assert list((serveur.vault / PROJET / "taches").glob("*recette-pilotee*"))
    page.locator(".ligne.t-conteneur", has_text="Projet piloté").locator(".chev").click()
    page.wait_for_selector(".ligne.t-tache >> text=Recette pilotée")
    assert page.locator(".ligne.t-tache >> text=Pilotage — Projet piloté").count() == 0
    # Revenir au projet : le bouton rouvre la même conversation au lieu d'en créer une autre.
    page.click(".ligne.t-conteneur >> text=Projet piloté")
    page.locator("[data-pilotage]").click()
    page.wait_for_selector(".d-titre >> text=Pilotage — Projet piloté")
    assert len(list((serveur.vault / PROJET / "taches").glob("*pilotage*"))) == 1
    assert not page.erreurs, page.erreurs
