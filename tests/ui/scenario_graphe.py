"""Scénarios du second cerveau : mentions non liées, graphe local, graphe global filtré, clic d'ouverture.

Contre le vrai serveur (vault temporaire). Le canvas n'a pas de nœud DOM par élément : le clic vise la
position que la vue expose (`positionNoeud`) une fois la simulation stabilisée (`data-stable`).
"""

import univers

DOSSIER = "Projets/C1-GrapheUI"


def _note(titre: str, corps: str = "", tags: str = "[essai]") -> str:
    return f"---\ntype: ressource\ntags: {tags}\n---\n\n# {titre}\n\n{corps}\n"


def _attendre_index(page, chemin, entrants=0):
    for _ in range(60):
        r = page.request.get(f"{page.url_serveur}/api/vault/note?chemin={chemin}")
        if r.ok and len(r.json().get("entrants", [])) >= entrants:
            return
        page.wait_for_timeout(500)
    raise AssertionError(f"l'index ne voit pas {chemin}")


def _univers(serveur, page):
    univers.ecrire(serveur.vault, f"{DOSSIER}/centrale.md", _note("Notion centrale", "Point de départ.", "[cerveau]"))
    univers.ecrire(serveur.vault, f"{DOSSIER}/voisine.md", _note("Voisine", "Renvoie à [[centrale]]."))
    univers.ecrire(serveur.vault, f"{DOSSIER}/lointaine.md", _note("Lointaine", "Renvoie à [[voisine]]."))
    univers.ecrire(serveur.vault, f"{DOSSIER}/lectrice.md", _note("Lectrice", "On y parle de notion centrale sans lien."))
    _attendre_index(page, f"{DOSSIER}/centrale.md", entrants=1)
    _attendre_index(page, f"{DOSSIER}/voisine.md", entrants=1)


def _stable(page):
    page.wait_for_selector(".g-canvas[data-stable='1']", timeout=20000)


def test_mentions_non_liees_puis_graphe_local(page, serveur):
    _univers(serveur, page)
    page.goto(f"{page.url_serveur}/#n={DOSSIER}/centrale.md")
    page.wait_for_selector(".vue-note .d-titre >> text=Notion centrale")
    page.click(".n-mentions summary")
    page.wait_for_selector(".n-mentions .lien-titre >> text=Lectrice")
    # Graphe local, profondeur 1 : la voisine, pas la lointaine.
    page.click("button:has-text('Graphe local')")
    page.wait_for_selector(".vue-graphe")
    _stable(page)
    assert "#g=" in page.url
    noms = page.locator(".g-liste [data-noeud]").all_text_contents()
    assert "Voisine" in noms and "Lointaine" not in noms
    page.select_option("select[data-filtre='profondeur']", "2")
    page.wait_for_selector(".g-liste [data-noeud] >> text=Lointaine", state="attached")
    assert not page.erreurs, page.erreurs


def test_graphe_global_filtre_et_clic_ouvre_la_note(page, serveur):
    _univers(serveur, page)
    page.goto(page.url_serveur + "/")
    page.evaluate("localStorage.removeItem('orch.graphe.filtres')")
    page.goto(page.url_serveur + "/#g")
    page.wait_for_selector(".vue-graphe")
    page.select_option("select[data-filtre='tag']", "cerveau")
    page.wait_for_selector("[data-id='graphe-compte'] >> text=1 nœud ·")
    _stable(page)
    pos = page.evaluate(f"document.querySelector('.g-canvas').positionNoeud('{DOSSIER}/centrale.md')")
    boite = page.locator(".g-canvas").bounding_box()
    page.mouse.click(boite["x"] + pos["x"], boite["y"] + pos["y"])
    page.wait_for_selector(".vue-note .d-titre >> text=Notion centrale")
    page.evaluate("localStorage.removeItem('orch.graphe.filtres')")
    assert not page.erreurs, page.erreurs


def test_notes_liees_sur_la_tache(page, serveur):
    _univers(serveur, page)
    univers.ecrire(serveur.vault, f"{DOSSIER}/taches/etudier.md",
                   "---\ntype: tache\nstatut: a-faire\n---\n\n# Étudier la centrale\n\nVoir [[centrale]].\n")
    _attendre_index(page, f"{DOSSIER}/centrale.md", entrants=2)
    page.goto(f"{page.url_serveur}/#t=etudier")
    page.click(".d-notes-liees summary")
    page.wait_for_selector(".d-notes-liees .lien-titre >> text=centrale")
    page.click(".d-actions button:text-is('Graphe')")
    page.wait_for_selector(".vue-graphe .d-titre >> text=Étudier la centrale")
    assert not page.erreurs, page.erreurs


def test_mouvement_reduit_dessine_une_fois_stabilise(page, serveur):
    _univers(serveur, page)
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{page.url_serveur}/#g={DOSSIER}/centrale.md")
    _stable(page)
    pos = page.evaluate(f"document.querySelector('.g-canvas').positionNoeud('{DOSSIER}/centrale.md')")
    assert pos and pos["x"] > 0, pos
    page.evaluate("document.documentElement.dataset.theme = 'sombre'")  # redessin sur changement de thème
    page.evaluate("delete document.documentElement.dataset.theme")
    assert not page.erreurs, page.erreurs
