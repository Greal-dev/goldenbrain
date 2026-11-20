"""Scénarios de glisser-déposer (volet gauche et cascade) : dépôt admis, refusé, menu tâche sur tâche, annulation, clavier."""

import re

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, niveau, projet, rang
from playwright.sync_api import expect


def _fichiers(serveur, nom):
    return sorted(p.relative_to(serveur.vault).as_posix() for p in serveur.vault.rglob(f"{nom}.md"))


def _texte(serveur, rel):
    return (serveur.vault / rel).read_text(encoding="utf-8")


def _deux_projets(serveur, nom):
    """Deux projets voisins : `<nom>A` (tâches X et Y) et `<nom>B` (tâche Z)."""
    projet(serveur, f"C1-{nom}A", {f"{nom}-x": (f"X {nom}", ""), f"{nom}-y": (f"Y {nom}", "")})
    projet(serveur, f"C1-{nom}B", {f"{nom}-z": (f"Z {nom}", "")})


def _glisser_a_la_souris(page, source, cible):
    """Glisse sans lâcher : l'état de survol de la cible reste observable."""
    s = source.bounding_box()
    page.mouse.move(s["x"] + 40, s["y"] + s["height"] / 2)
    page.mouse.down()
    page.mouse.move(s["x"] + 45, s["y"] + s["height"] / 2 + 3, steps=3)  # amorce le glisser (dragstart)
    c = cible.bounding_box()
    page.mouse.move(c["x"] + 50, c["y"] + c["height"] / 2, steps=10)
    for i in range(40):  # le navigateur lance dragstart de façon asynchrone : on rebouge jusqu'au premier dragover reçu
        if cible.evaluate("(e) => /cible-(ok|ko)/.test(e.className)"):
            break
        page.mouse.move(c["x"] + 50 + i % 5, c["y"] + c["height"] / 2)


def test_glisser_tache_sur_un_projet_puis_annuler(page, serveur):
    _deux_projets(serveur, "gp")
    charger(page)
    ligne(page, "X gp").drag_to(ligne(page, "gpB"))
    expect(page.locator("#info-geste")).to_contain_text("X gp est maintenant sous gpB")
    assert _fichiers(serveur, "gp-x") == ["Projets/C1-gpB/taches/gp-x.md"]  # le fichier a changé de projet
    expect(ligne(page, "X gp")).to_have_class(re.compile(r"marque"))  # l'élément déplacé est mis en évidence
    assert niveau(ligne(page, "X gp")) == niveau(ligne(page, "Z gp"))
    page.locator("#info-geste").get_by_role("button", name="Annuler").click()  # geste inverse
    expect(page.locator("#info-geste")).to_contain_text("revenu à sa place")
    assert _fichiers(serveur, "gp-x") == ["Projets/C1-gpA/taches/gp-x.md"]
    assert not page.erreurs, page.erreurs


def test_glisser_tache_sur_tache_ouvre_le_menu_et_fait_un_enfant(page, serveur):
    _deux_projets(serveur, "gt")
    charger(page)
    ligne(page, "Y gt").drag_to(ligne(page, "X gt"))
    menu = page.locator(".menu-depot")
    expect(menu).to_be_visible()
    expect(menu.locator(".menu-item")).to_have_text(["En faire un enfant", "Lier : alimente", "Lier : a pour prérequis", "Lier : voir aussi", "Annuler"])
    menu.get_by_role("menuitem", name="En faire un enfant").click()
    expect(menu).to_have_count(0)
    expect(ligne(page, "X gt")).to_have_attribute("aria-expanded", "false")  # X a désormais un enfant, replié
    ligne(page, "X gt").locator(".chev").click()
    expect(ligne(page, "Y gt")).to_have_attribute("data-niveau", str(niveau(ligne(page, "X gt")) + 1))
    assert "parent: gt-x" in _texte(serveur, "Projets/C1-gtA/taches/gt-y.md")
    assert not page.erreurs, page.erreurs


def test_glisser_tache_sur_tache_menu_annule_ne_change_rien(page, serveur):
    _deux_projets(serveur, "gm")
    charger(page)
    chemin = serveur.vault / "Projets/C1-gmA/taches/gm-y.md"
    avant = chemin.read_bytes()
    ligne(page, "Y gm").drag_to(ligne(page, "X gm"))
    page.locator(".menu-depot").get_by_role("menuitem", name="Annuler").click()
    expect(page.locator(".menu-depot")).to_have_count(0)
    assert chemin.read_bytes() == avant
    assert not page.erreurs, page.erreurs


def test_glisser_tache_sur_tache_lier_voir_aussi(page, serveur):
    _deux_projets(serveur, "gl")
    charger(page)
    ligne(page, "Y gl").drag_to(ligne(page, "Z gl"))
    page.locator(".menu-depot").get_by_role("menuitem", name="Lier : voir aussi").click()
    expect(page.locator(".menu-depot")).to_have_count(0)
    # le lien est écrit côté serveur : le repère ⇄ apparaît sur la ligne dès que l'arbre est rechargé
    expect(ligne(page, "Y gl").locator(".repere-liens")).to_have_count(1)
    assert "voir_aussi: [gl-z]" in _texte(serveur, "Projets/C1-glA/taches/gl-y.md")
    assert not page.erreurs, page.erreurs


def test_glisser_refuse_sur_un_descendant(page, serveur):
    projet(serveur, "C1-GrefA", {"gr-m": ("Mère gr", ""), "gr-e": ("Enfant gr", "parent: gr-m\n")})
    charger(page)
    _glisser_a_la_souris(page, ligne(page, "Mère gr"), ligne(page, "Enfant gr"))
    expect(ligne(page, "Enfant gr")).to_have_class(re.compile(r"cible-ko"))  # refusé sans appel au serveur
    page.mouse.up()
    expect(page.locator("#info-geste")).to_have_count(0)  # aucun geste : la ligne d'information n'est même pas créée
    assert _fichiers(serveur, "gr-m") == ["Projets/C1-GrefA/taches/gr-m.md"]
    assert "parent:" not in _texte(serveur, "Projets/C1-GrefA/taches/gr-m.md")
    assert not page.erreurs, page.erreurs


def test_glisser_admis_surligne_la_cible(page, serveur):
    _deux_projets(serveur, "ga")
    charger(page)
    _glisser_a_la_souris(page, ligne(page, "X ga"), ligne(page, "gaB"))
    expect(ligne(page, "gaB")).to_have_class(re.compile(r"cible-ok"))
    page.mouse.up()
    expect(page.locator("#info-geste")).to_contain_text("est maintenant sous")
    assert not page.erreurs, page.erreurs


def test_monter_d_un_niveau_bouton_et_clavier(page, serveur):
    projet(serveur, "C1-MontA", {"mo-m": ("Mère mo", ""), "mo-e": ("Enfant mo", "parent: mo-m\n"),
                                  "mo-p": ("Petit mo", "parent: mo-e\n")})
    charger(page)
    assert niveau(ligne(page, "Petit mo")) == niveau(ligne(page, "Enfant mo")) + 1
    ligne(page, "Petit mo").hover()
    ligne(page, "Petit mo").locator("[data-act='monter']").click()  # bouton discret au survol
    expect(page.locator("#info-geste")).to_contain_text("remonté d’un niveau")
    expect(ligne(page, "Petit mo")).to_have_attribute("data-niveau", str(niveau(ligne(page, "Enfant mo"))))
    ligne(page, "Petit mo").focus()
    page.keyboard.press("Shift+ArrowLeft")  # raccourci clavier : sa mère remonte aussi d'un niveau
    expect(ligne(page, "Petit mo")).to_have_attribute("data-niveau", str(niveau(ligne(page, "Mère mo"))))
    assert "parent:" not in _texte(serveur, "Projets/C1-MontA/taches/mo-p.md")
    assert not page.erreurs, page.erreurs


def test_deplacer_vers_au_clavier(page, serveur):
    _deux_projets(serveur, "dv")
    charger(page)
    ligne(page, "X dv").focus()
    page.keyboard.press("m")
    dlg = page.locator("dialog.dlg")
    expect(dlg).to_be_visible()
    champ = dlg.get_by_role("combobox")
    expect(champ).to_be_focused()
    champ.fill("dvB")
    projets = dlg.get_by_role("option").filter(has_text="projet")
    expect(projets).to_have_count(1)  # filtré : un seul projet « dvB » (sa tâche Z y figure aussi, comme tâche)
    projets.click()
    expect(page.locator("#info-geste")).to_contain_text("X dv est maintenant sous dvB")
    assert _fichiers(serveur, "dv-x") == ["Projets/C1-dvB/taches/dv-x.md"]
    assert not page.erreurs, page.erreurs


def test_cascade_glisser_tache_sur_un_projet(page, serveur):
    _deux_projets(serveur, "cg")
    charger(page)
    page.locator("#marque").click()  # vue d'ensemble : la cascade de tout l'arbre
    page.wait_for_selector(".casc-corps .cl")
    page.get_by_role("button", name="Tout déplier").click()
    rang(page, "X cg").drag_to(rang(page, "cgB"))
    expect(page.locator("#info-geste")).to_contain_text("X cg est maintenant sous cgB")
    assert _fichiers(serveur, "cg-x") == ["Projets/C1-cgB/taches/cg-x.md"]
    expect(rang(page, "X cg")).to_have_class(re.compile(r"marque"))
    assert not page.erreurs, page.erreurs


def test_glisser_projet_montre_le_plan_sans_rien_ecrire(page, serveur):
    _deux_projets(serveur, "gj")
    charger(page)
    ligne(page, "gjA").drag_to(ligne(page, "gjB"))
    dlg = page.locator("dialog.dlg.plan")
    expect(dlg).to_be_visible()
    expect(dlg).to_contain_text("Rien n’a encore été modifié")
    dlg.get_by_role("button", name="Annuler").click()
    expect(dlg).to_have_count(0)
    assert _fichiers(serveur, "gj-x") == ["Projets/C1-gjA/taches/gj-x.md"]  # dossier intact
    assert "parent:" not in _texte(serveur, "Projets/C1-gjA/contexte.md")
    assert not page.erreurs, page.erreurs
