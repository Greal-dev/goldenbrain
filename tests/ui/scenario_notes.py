"""Scénarios des notes : lecture, édition, conflit d'édition (409) — contre le vrai serveur.

Les notes sont écrites sur le disque du vault temporaire, hors de l'interface (comme le ferait Obsidian
ou un agent) : c'est précisément ce qui provoque le conflit. Chaque scénario a ses propres fichiers.
"""

import univers

DOSSIER = "Projets/C1-NotesUI"


def _note(titre: str, corps: str = "") -> str:
    return f"---\ntype: ressource\ntags: [essai]\n---\n\n# {titre}\n\n{corps}\n"


def _attendre_index(page, chemin, entrants=0):
    """L'index des notes se rafraîchit en arrière-plan : attendre qu'il voie la note (et ses liens entrants)."""
    for _ in range(60):
        r = page.request.get(f"{page.url_serveur}/api/vault/note?chemin={chemin}")
        if r.ok and len(r.json().get("entrants", [])) >= entrants:
            return
        page.wait_for_timeout(500)
    raise AssertionError(f"l'index ne voit pas {chemin} avec {entrants} lien(s) entrant(s)")


def _ouvrir_note(page, nom):
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.click("#onglet-notes")
    for dossier in ("Projets", "C1-NotesUI"):
        page.click(f".ligne.t-dossier >> text={dossier}")
    page.click(f".ligne.t-note >> text={nom}")
    page.wait_for_selector(".vue-note .d-titre")


def _editer(page, nom, texte):
    _ouvrir_note(page, nom)
    page.click("button:has-text('Modifier')")
    page.wait_for_selector(".n-editeur")
    page.fill(".n-editeur", texte)
    page.wait_for_selector(".n-etat.modifie")


def test_lecture_note_proprietes_rendu_et_liens_entrants(page, serveur):
    univers.ecrire(serveur.vault, f"{DOSSIER}/lecture-cible.md", _note("Cible de lecture", "Texte **gras** de la cible."))
    univers.ecrire(serveur.vault, f"{DOSSIER}/lecture-source.md", _note("Source de lecture", "Voir [[lecture-cible]]."))
    _attendre_index(page, f"{DOSSIER}/lecture-cible.md", entrants=1)
    _ouvrir_note(page, "lecture-cible")
    assert page.locator(".vue-note .d-titre").inner_text() == "Cible de lecture"
    assert page.locator(".n-props-t th", has_text="tags").count() == 1  # propriétés du frontmatter
    assert page.locator(".note-md strong", has_text="gras").count() == 1  # corps rendu
    assert page.locator(".n-entrants h3").text_content() == "Liens entrants (1)"
    # Suivre le lien entrant ouvre la note source.
    page.click(".n-entrants .lien-titre")
    page.wait_for_selector(".vue-note .d-titre >> text=Source de lecture")
    assert not page.erreurs, page.erreurs


def test_edition_enregistre_sur_le_disque(page, serveur):
    chemin = serveur.vault / DOSSIER / "edition.md"
    univers.ecrire(serveur.vault, f"{DOSSIER}/edition.md", _note("Édition", "avant"))
    _attendre_index(page, f"{DOSSIER}/edition.md")
    nouveau = _note("Édition", "après") + "\nLigne ajoutée.\n"
    _editer(page, "edition", nouveau)
    page.press(".n-editeur", "Control+s")
    page.wait_for_selector(".n-etat >> text=enregistré")
    assert chemin.read_text(encoding="utf-8") == nouveau
    page.click("button:has-text('Terminer')")
    page.wait_for_selector(".note-md >> text=Ligne ajoutée.")
    assert not page.erreurs, page.erreurs


def test_conflit_garder_la_mienne(page, serveur):
    chemin = serveur.vault / DOSSIER / "conflit-mienne.md"
    univers.ecrire(serveur.vault, f"{DOSSIER}/conflit-mienne.md", _note("Conflit A", "origine"))
    _attendre_index(page, f"{DOSSIER}/conflit-mienne.md")
    mienne = _note("Conflit A", "ma version")
    _editer(page, "conflit-mienne", mienne)
    ailleurs = _note("Conflit A", "version écrite ailleurs")
    univers.ecrire(serveur.vault, f"{DOSSIER}/conflit-mienne.md", ailleurs)  # Obsidian, un agent…
    page.click("button:has-text('Enregistrer')")
    dlg = page.locator("dialog.conflit")
    dlg.wait_for()
    assert "La note a changé ailleurs" in dlg.inner_text()
    assert dlg.locator(".cf-diff", has_text="ma version").count() == 1       # ma colonne surligne mon écart
    assert dlg.locator(".cf-diff", has_text="écrite ailleurs").count() == 1  # l'autre aussi
    assert chemin.read_text(encoding="utf-8") == ailleurs  # rien n'est écrasé avant le choix
    dlg.locator("button:has-text('Garder la mienne')").click()
    page.wait_for_selector(".n-etat >> text=enregistré")
    assert chemin.read_text(encoding="utf-8") == mienne
    assert not page.erreurs or all("409" in e for e in page.erreurs), page.erreurs


def test_conflit_reprendre_la_version_courante(page, serveur):
    chemin = serveur.vault / DOSSIER / "conflit-courante.md"
    univers.ecrire(serveur.vault, f"{DOSSIER}/conflit-courante.md", _note("Conflit B", "origine"))
    _attendre_index(page, f"{DOSSIER}/conflit-courante.md")
    _editer(page, "conflit-courante", _note("Conflit B", "ma version"))
    ailleurs = _note("Conflit B", "version écrite ailleurs")
    univers.ecrire(serveur.vault, f"{DOSSIER}/conflit-courante.md", ailleurs)
    page.click("button:has-text('Enregistrer')")
    dlg = page.locator("dialog.conflit")
    dlg.wait_for()
    dlg.locator("button:has-text('Reprendre la version courante')").click()
    dlg.wait_for(state="detached")
    assert page.input_value(".n-editeur") == ailleurs
    assert chemin.read_text(encoding="utf-8") == ailleurs  # le disque n'a pas bougé
    assert not page.erreurs or all("409" in e for e in page.erreurs), page.erreurs


def test_conflit_continuer_a_editer_garde_mon_texte(page, serveur):
    chemin = serveur.vault / DOSSIER / "conflit-continuer.md"
    univers.ecrire(serveur.vault, f"{DOSSIER}/conflit-continuer.md", _note("Conflit C", "origine"))
    _attendre_index(page, f"{DOSSIER}/conflit-continuer.md")
    mienne = _note("Conflit C", "ma version")
    _editer(page, "conflit-continuer", mienne)
    ailleurs = _note("Conflit C", "version écrite ailleurs")
    univers.ecrire(serveur.vault, f"{DOSSIER}/conflit-continuer.md", ailleurs)
    page.click("button:has-text('Enregistrer')")
    dlg = page.locator("dialog.conflit")
    dlg.wait_for()
    dlg.locator("button:has-text('Continuer à éditer')").click()
    dlg.wait_for(state="detached")
    assert page.input_value(".n-editeur") == mienne
    assert chemin.read_text(encoding="utf-8") == ailleurs
    assert not page.erreurs or all("409" in e for e in page.erreurs), page.erreurs
