"""Scénario du curseur « Moi / IA » et des notes (INV-EXECUTANT-1, INV-EXECUTANT-2) : deux panneaux
réductibles (état mémorisé), conversation inactive en mode Moi, ajout et modification d'une note,
pastille, filtre « Qui la mène », puis « Confier la suite » qui rend la tâche à l'IA et lance son tour."""

import re

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def test_panneaux_moi_notes_filtre_puis_confier_la_suite(page, serveur):
    projet(serveur, "C1-ExecUI", {"ex-moi": ("Moi ExecUI", ""), "ex-ia": ("IA ExecUI", "")})
    charger(page)
    ligne(page, "Moi ExecUI").click()
    expect(page.locator(".d-titre")).to_have_text("Moi ExecUI")
    expect(page.locator(".cur-ex.actif")).to_have_attribute("data-executant", "ia")

    # Deux panneaux côte à côte, chacun réductible ; l'état survit au rechargement.
    conv, notes = page.locator(".volet-t-conv"), page.locator(".volet-t-notes")
    expect(conv).to_be_visible()
    expect(notes).to_be_visible()
    bc, bn = conv.bounding_box(), notes.bounding_box()
    assert bc["x"] + bc["width"] <= bn["x"] + 1 and abs(bc["y"] - bn["y"]) < 2  # côte à côte, sans onglet
    expect(page.locator(".d-onglet")).to_have_count(0)
    notes.locator(".p-replier").click()
    expect(notes).to_have_class(re.compile(r"\breplie\b"))
    expect(notes.locator(".p-corps")).to_be_hidden()
    conv.locator(".p-replier").click()
    expect(conv.locator(".p-corps")).to_be_hidden()
    page.reload()
    ligne(page, "Moi ExecUI").click()
    expect(page.locator(".volet-t-notes .p-corps")).to_be_hidden()
    expect(page.locator(".volet-t-conv .p-corps")).to_be_hidden()
    page.locator(".volet-t-conv .p-replier").click()
    page.locator(".volet-t-notes .p-replier").click()
    expect(page.locator(".volet-t-conv .p-corps")).to_be_visible()
    expect(page.locator(".volet-t-notes .p-corps")).to_be_visible()

    # Bascule sur Moi : conversation inactive (saisie désactivée), pastille 👤 dans l'arbre.
    page.locator(".cur-ex[data-executant='humain']").click()
    expect(page.locator(".cur-ex.actif")).to_have_attribute("data-executant", "humain")
    expect(page.locator(".volet-t-conv")).to_have_class(re.compile(r"\binactive\b"))
    expect(page.locator(".composer textarea")).to_be_disabled()
    expect(ligne(page, "Moi ExecUI").locator(".pastille-moi")).to_have_count(1)
    expect(ligne(page, "IA ExecUI").locator(".pastille-moi")).to_have_count(0)
    texte = (serveur.vault / "Projets/C1-ExecUI/taches/ex-moi.md").read_text("utf-8")
    assert "executant: humain" in texte

    # Une note, sans tour d'agent, puis sa modification.
    ta = page.locator(".notes-ajout textarea")
    ta.fill("Devis reçu, reste à comparer")
    ta.press("Control+Enter")
    expect(page.locator(".note-t")).to_contain_text("Devis reçu, reste à comparer")
    assert page.request.get(serveur.url + "/api/taches/ex-moi").json()["etat_execution"] == "inactif"
    page.locator(".note-modifier").click()
    page.locator(".note-edition textarea").fill("Devis reçus (2), reste à comparer")
    page.get_by_role("button", name="Enregistrer").click()
    expect(page.locator(".note-t")).to_contain_text("Devis reçus (2)")
    expect(page.locator(".note-t .note-modif")).to_contain_text("modifiée")
    texte = (serveur.vault / "Projets/C1-ExecUI/taches/ex-moi.md").read_text("utf-8")
    assert "Devis reçus (2), reste à comparer" in texte

    # Filtre « À faire par moi » : seule la tâche menée par moi reste.
    page.click("#btn-filtres")
    page.select_option("#f-executant", "humain")
    expect(ligne(page, "IA ExecUI")).to_have_count(0)
    expect(ligne(page, "Moi ExecUI")).to_have_count(1)
    page.select_option("#f-executant", "")

    # Confier la suite : le premier tour part (notes en contexte : test_executant.py).
    page.locator(".cur-ex[data-executant='ia']").click()
    dlg = page.locator("dialog.dlg")
    expect(dlg).to_contain_text("1 note")
    dlg.locator("input[name='consigne']").fill("Comparer les devis")
    dlg.get_by_role("button", name="Confier la suite").click()
    expect(page.locator(".cur-ex.actif")).to_have_attribute("data-executant", "ia")
    expect(page.locator(".composer textarea")).to_be_enabled()
    expect(page.locator(".msg.agent.final")).to_contain_text("bonjour s-faux")  # le tour confié a tourné
    assert not page.erreurs, page.erreurs


def test_notes_ia_selection_synthetiser_inserer_puis_annuler(page, serveur):
    """INV-EXECUTANT-3 : sélection dans une note → Synthétiser → proposition (rien d'écrit) → Insérer → Annuler."""
    projet(serveur, "C1-NotesIA", {"nia": ("Notes IA", "")})
    charger(page)
    ligne(page, "Notes IA").click()
    page.locator(".cur-ex[data-executant='humain']").click()  # disponible aussi en mode Moi
    expect(page.locator(".cur-ex.actif")).to_have_attribute("data-executant", "humain")
    for texte in ("Note sans rapport", "Appel du notaire : signer jeudi"):
        page.locator(".notes-ajout textarea").fill(texte)
        page.locator(".notes-ajout textarea").press("Control+Enter")
        expect(page.locator(".note-t").last).to_contain_text(texte)
    fichier = serveur.vault / "Projets/C1-NotesIA/taches/nia.md"
    page.evaluate("""() => { const p = document.querySelectorAll('.note-t .md')[1].querySelector('p');
        const r = document.createRange(); r.selectNodeContents(p);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""")
    avant = fichier.read_text("utf-8")
    page.locator(".ia-barre [data-ia='synthetiser']").click()
    prop = page.locator(".ia-prop")
    expect(prop).to_contain_text("synthèse de : Appel du notaire : signer jeudi")
    expect(prop).not_to_contain_text("Note sans rapport")  # seule la sélection est partie
    expect(prop).to_contain_text("sélection")
    assert fichier.read_text("utf-8") == avant  # aucune écriture avant le geste
    prop.get_by_role("button", name="Insérer en dessous").click()
    expect(page.locator(".note-t").nth(1)).to_contain_text("Synthétiser (IA)")
    assert "synthèse de : Appel du notaire" in fichier.read_text("utf-8")
    page.get_by_role("button", name="Annuler la modification").click()
    expect(page.locator(".note-t").nth(1)).not_to_contain_text("Synthétiser (IA)")
    expect(page.locator(".note-t").nth(1)).to_contain_text("Appel du notaire : signer jeudi")
    assert "synthèse de" not in fichier.read_text("utf-8")
    assert not page.erreurs, page.erreurs
