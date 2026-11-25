"""Scénarios des bandeaux de version (dont le redémarrage différé) : « serveur à mettre à jour » (code du disque plus récent) et « mise à jour disponible ».

Le vrai serveur de test est toujours à jour et le dépôt distant n'est jamais contacté : l'état de version
(`/api/etat`, `/api/mise-a-jour`) est donc altéré au passage par `page.route`, et les POST qui
redémarreraient ou mettraient à jour le serveur sont interceptés (jamais envoyés au vrai serveur,
qui s'arrêterait). Tout le reste — bandeaux, boutons, dialogues, voile d'attente — est l'interface réelle.
"""

import json

from conftest import deplier_infos

MAJ_RIEN = {"depot": True, "retard": 0, "distant": "origin", "branche": "main", "dernier_controle": None}


def _etat(page, a_jour):
    """Intercepte GET /api/etat : le vrai état, mais avec `version.a_jour` imposé."""
    def gerer(route):
        corps = route.fetch().json()
        corps["version"] = {**corps["version"], "a_jour": a_jour}
        route.fulfill(json=corps)
    page.route("**/api/etat", gerer)


def _maj(page, valeur):
    page.route("**/api/mise-a-jour", lambda route: route.fulfill(json=valeur)
               if route.request.method == "GET" else route.abort())


def _charger(page):
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")


def test_serveur_a_jour_aucun_bandeau(page):
    _etat(page, True)
    _maj(page, MAJ_RIEN)
    _charger(page)
    page.wait_for_function("document.querySelector('#n-tours').textContent !== ''")
    assert page.locator("#maj-serveur").is_hidden()
    assert page.locator("#maj-dispo").is_hidden()
    assert not page.erreurs, page.erreurs


def test_code_perime_bandeau_et_redemarrage_refuse_puis_annule(page):
    _etat(page, False)
    _maj(page, MAJ_RIEN)
    envois = []

    def redemarrer(route):
        envois.append(route.request.post_data_json or {})
        route.fulfill(status=409, json={"detail": "un tour tourne ou attend en file : redémarrer après, ou forcer"})
    page.route("**/api/redemarrer", redemarrer)
    _charger(page)
    deplier_infos(page)
    bandeau = page.locator("#maj-serveur")
    bandeau.wait_for()
    assert "GoldenBrain a été mis à jour" in bandeau.inner_text()
    bandeau.locator("button:has-text('Redémarrer')").click()
    dlg = page.locator("dialog[aria-label='Redémarrer quand même ?']")
    dlg.wait_for()
    assert "un tour tourne" in dlg.inner_text()
    dlg.locator("button:has-text('Attendre')").click()
    dlg.wait_for(state="detached")
    assert envois == [{"par": "interface"}]  # une seule demande, sans force ; le voile d'attente n'est pas apparu
    assert page.locator("#voile-redemarrage").is_hidden()
    assert bandeau.is_visible()  # le serveur reste périmé : le bandeau persiste
    assert not [e for e in page.erreurs if "409" not in e], page.erreurs


def test_redemarrer_quand_meme_force_et_affiche_le_voile(page):
    _etat(page, False)
    _maj(page, MAJ_RIEN)
    envois = []

    def redemarrer(route):
        envois.append(route.request.post_data_json or {})
        if envois[-1].get("force"):
            route.fulfill(status=202, json={"code_sortie": 3})
        else:
            route.fulfill(status=409, json={"detail": "un tour tourne ou attend en file"})
    page.route("**/api/redemarrer", redemarrer)
    _charger(page)
    deplier_infos(page)
    page.locator("#maj-serveur button:has-text('Redémarrer')").click()
    dlg = page.locator("dialog[aria-label='Redémarrer quand même ?']")
    dlg.wait_for()
    dlg.locator("button:has-text('Redémarrer quand même')").click()
    voile = page.locator("#voile-redemarrage")
    voile.wait_for()
    assert "redémarrage" in voile.inner_text()
    assert envois == [{"par": "interface"}, {"force": True, "par": "interface"}]
    assert page.evaluate("document.querySelector('#corps').inert") is True  # l'interface est gelée pendant l'attente


def test_mise_a_jour_disponible_bandeau_et_pluriel(page):
    _maj(page, {**MAJ_RIEN, "retard": 2})
    _charger(page)
    deplier_infos(page)
    bandeau = page.locator("#maj-dispo")
    bandeau.wait_for()
    assert "Une mise à jour est disponible : 2 modifications de retard sur origin/main." in bandeau.inner_text()
    assert bandeau.locator("button:has-text('Mettre à jour')").count() == 1
    assert not page.erreurs, page.erreurs


def test_mise_a_jour_disponible_masquee_sur_telephone(page):
    """Compagnon : la mise à jour ne se fait que depuis le poste, la bande est masquée sous 480 px."""
    _maj(page, {**MAJ_RIEN, "retard": 2})
    page.set_viewport_size({"width": 390, "height": 800})
    _charger(page)
    page.wait_for_timeout(600)
    assert page.locator("#maj-dispo").is_hidden()
    assert not page.erreurs, page.erreurs


def test_mise_a_jour_refusee_affiche_le_motif(page):
    _maj(page, {**MAJ_RIEN, "retard": 1})
    page.route("**/api/mise-a-jour", lambda route: route.fulfill(
        status=409, json={"detail": "un tour tourne ou attend en file : mettre à jour après"})
        if route.request.method == "POST" else route.fulfill(json={**MAJ_RIEN, "retard": 1}))
    _charger(page)
    deplier_infos(page)
    bandeau = page.locator("#maj-dispo")
    bandeau.wait_for()
    assert "1 modification de retard" in bandeau.inner_text()
    bandeau.locator("button:has-text('Mettre à jour')").click()
    page.wait_for_selector("#banniere >> text=mettre à jour après")
    # La bannière d'erreur passe devant (un seul bandeau à la fois) : « mettre à jour » reste disponible, simplement replié.
    assert not bandeau.evaluate("e => e.hidden") and page.locator("#voile-redemarrage").is_hidden()


def test_redemarrage_differe_bandeau_annuler_puis_voile(page):
    """INV-VERSION-3 : 409 -> « dès que les tours sont finis » -> bandeau -> Annuler ; puis le serveur s'éteint -> voile."""
    _etat(page, False)
    _maj(page, MAJ_RIEN)
    etat = {"differe": False}
    envois = []

    def etat_differe(route):
        try:
            corps = route.fetch().json()
        except Exception:  # page fermée pendant une sonde de fond
            return
        corps["version"] = {**corps["version"], "a_jour": False, "differe": etat["differe"]}
        corps["tours"] = [{"tache": "x", "titre": "x", "depuis": "", "dernier": ""}] if etat["differe"] else corps.get("tours", [])
        route.fulfill(json=corps)
    page.unroute("**/api/etat")
    page.route("**/api/etat", etat_differe)
    page.route("**/api/redemarrer", lambda route: route.fulfill(status=409, json={"detail": "un tour tourne ou attend en file"}))

    def differe(route):
        envois.append(route.request.method)
        etat["differe"] = route.request.method == "POST"
        route.fulfill(status=202, json={"differe": etat["differe"]})
    page.route("**/api/redemarrer-differe", differe)
    _charger(page)
    deplier_infos(page)
    page.locator("#maj-serveur button:has-text('Redémarrer')").click()
    dlg = page.locator("dialog[aria-label='Redémarrer quand même ?']")
    dlg.wait_for()
    dlg.locator("button:has-text('Redémarrer GoldenBrain dès que les séances de travail sont finies')").click()
    bandeau = page.locator("#redemarrage-differe")
    bandeau.wait_for()
    page.wait_for_selector("#redemarrage-differe >> text=(1)")
    assert "GoldenBrain redémarrera dès que les séances de travail en cours seront finies (1)" in bandeau.inner_text()
    assert "ordinateur" in bandeau.inner_text()
    bandeau.locator("button:has-text('Annuler')").click()
    bandeau.wait_for(state="hidden")
    assert envois == ["POST", "DELETE"]
    assert page.locator("#voile-redemarrage").is_hidden()
    assert not [e for e in page.erreurs if "409" not in e], page.erreurs
