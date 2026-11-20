"""Scénario de fumée : l'interface charge sans erreur, l'arbre s'affiche, un tour factice aboutit (fiche rendue, conversation relue)."""


def test_arbre_et_tour_factice(page):
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    assert page.locator(".ligne", has_text="Alpha").count() >= 1
    fermes = page.locator(".ligne .chev:not(.ouvert):not(.vide)")
    for _ in range(10):  # l'arbre se redessine à chaque dépliage : on relit le premier chevron fermé
        if not fermes.count():
            break
        fermes.first.click()
    page.click(".ligne.t-tache >> text=Mère")
    page.wait_for_selector(".d-titre")
    page.fill(".composer textarea", "Bonjour")
    page.press(".composer textarea", "Control+Enter")
    # La fiche rendue par le harnais factice remplace celle de la tâche : le tour est allé au bout.
    page.wait_for_selector("text=en bonne voie", timeout=10000)
    page.wait_for_selector(".msg.agent >> text=bonjour s-faux")
    assert not page.erreurs, page.erreurs
