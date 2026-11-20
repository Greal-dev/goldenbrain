"""Scénarios de l'alignement : pastille et panneau des écarts, plan (simulation), application, conflit.

Un écart naît d'un projet dont le `parent:` contredit son dossier : l'arbre le place sous son père, le
dossier est resté à plat. Chaque scénario a ses propres projets (le serveur est partagé).
"""

import univers


def _projet(vault, dossier, nom, parent=None):
    parent_fm = f"parent: {parent}\n" if parent else ""
    univers.ecrire(vault, f"Projets/{dossier}/contexte.md",
                   f"---\ntype: contexte\ncasquette: C1-Pro\nnom: {nom}\n{parent_fm}---\n")
    univers.ecrire(vault, f"Projets/{dossier}/taches/t-{dossier.lower()}.md", univers.tache(f"Tâche de {nom}"))


def _attendre_ecart(page, conteneur):
    for _ in range(60):
        ecarts = page.request.get(f"{page.url_serveur}/api/alignement").json()
        if any(e["conteneur"] == conteneur for e in ecarts):
            return
        page.wait_for_timeout(500)
    raise AssertionError(f"aucun écart pour {conteneur}")


def _ouvrir_panneau(page):
    page.goto(page.url_serveur + "/")
    page.wait_for_selector("#btn-align:not([hidden])")
    page.click("#btn-align")
    page.wait_for_selector("#panneau-align:not([hidden]) .al-ecart")


def test_plan_puis_application_deplace_le_dossier(page, serveur):
    _projet(serveur.vault, "C1-AlignPere", "AlignPere")
    _projet(serveur.vault, "C1-AlignFils", "AlignFils", parent="C1-AlignPere")
    _attendre_ecart(page, "Projets/C1-AlignFils")
    _ouvrir_panneau(page)
    ligne = page.locator(".al-ecart", has_text="AlignFils")
    assert "Projets/C1-AlignPere/C1-AlignFils" in ligne.locator(".al-chemins").inner_text()
    voir = page.locator("#panneau-align button:has-text('Voir le plan')")
    assert voir.is_disabled()  # rien de coché
    ligne.locator("input[type=checkbox]").check()
    voir.click()
    plan = page.locator("dialog.plan")
    plan.wait_for()
    texte = plan.inner_text()
    assert "1 dossier à déplacer" in texte and "Rien n’a encore été modifié" in texte, texte
    assert (serveur.vault / "Projets/C1-AlignFils/contexte.md").exists()  # simulation : rien écrit
    # Annuler : toujours rien de touché.
    plan.locator("button:has-text('Annuler')").click()
    plan.wait_for(state="detached")
    assert (serveur.vault / "Projets/C1-AlignFils/contexte.md").exists()
    # Refaire le plan et appliquer (le vault de test n'est pas un dépôt git : pas de point de restauration).
    page.click("#btn-align")
    page.locator(".al-ecart", has_text="AlignFils").locator("input[type=checkbox]").check()
    page.click("#panneau-align button:has-text('Voir le plan')")
    plan = page.locator("dialog.plan")
    plan.wait_for()
    plan.locator("input[type=checkbox]").uncheck()
    plan.locator("button:has-text('Appliquer')").click()
    page.wait_for_selector("dialog.plan >> text=Alignement terminé", timeout=15000)
    assert "1 dossier déplacé" in plan.inner_text()
    plan.locator("button:has-text('Fermer')").click()
    assert (serveur.vault / "Projets/C1-AlignPere/C1-AlignFils/contexte.md").exists()
    assert not (serveur.vault / "Projets/C1-AlignFils").exists()
    # L'écart a disparu de la liste du serveur.
    assert all(e["conteneur"] != "Projets/C1-AlignFils"
               for e in page.request.get(f"{page.url_serveur}/api/alignement").json())
    assert not page.erreurs, page.erreurs


def test_ecart_en_conflit_n_est_pas_selectionnable(page, serveur):
    _projet(serveur.vault, "C1-AlignPere2", "AlignPere2")
    _projet(serveur.vault, "C1-AlignBloque", "AlignBloque", parent="C1-AlignPere2")
    univers.ecrire(serveur.vault, "Projets/C1-AlignPere2/C1-AlignBloque/occupe.md", "occupé\n")  # destination prise
    _attendre_ecart(page, "Projets/C1-AlignBloque")
    _ouvrir_panneau(page)
    ligne = page.locator(".al-ecart.en-conflit", has_text="AlignBloque")
    assert "la destination existe déjà" in ligne.locator(".al-conflit").inner_text()
    assert ligne.locator("input[type=checkbox]").is_disabled()
    assert (serveur.vault / "Projets/C1-AlignBloque/contexte.md").exists()
    assert not page.erreurs, page.erreurs
