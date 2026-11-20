"""Invitation à l'étoile GitHub : fenêtre à trois boutons, réponse envoyée au serveur, interrupteur des Réglages.

L'état serveur (`/api/etoile`) est imposé par `page.route` : le vrai dépôt est privé et le réseau n'est jamais sondé.
Les POST de réponse sont interceptés (le fichier d'état du serveur de test n'est pas touché).
"""

URL = "https://github.com/exemple/depot"


def _etat(page, afficher):
    page.route("**/api/etoile", lambda route: route.fulfill(json={"actif": True, "afficher": afficher, "url": URL, "essai": False})
               if route.request.method == "GET" else route.fallback())


def test_fenetre_trois_boutons_et_plus_tard(page):
    _etat(page, True)
    envois = []
    page.route("**/api/etoile/reponse", lambda route: (envois.append(route.request.post_data_json), route.fulfill(json={"actif": True, "afficher": False, "url": URL, "essai": False})))
    page.goto(page.url_serveur + "/")
    dlg = page.locator("dialog[data-id='etoile']")
    dlg.wait_for()
    assert "GoldenBrain vous est utile" in dlg.inner_text()
    for libelle in ("Mettre une étoile", "Plus tard", "Ne plus demander"):
        assert dlg.locator(f"button:has-text('{libelle}')").count() == 1
    dlg.locator("button:has-text('Plus tard')").click()
    page.wait_for_function("!document.querySelector(\"dialog[data-id='etoile']\")")
    assert envois == [{"choix": "plus_tard"}]
    assert not page.erreurs, page.erreurs


def test_mettre_une_etoile_ouvre_le_depot(page):
    _etat(page, True)
    envois = []
    page.route("**/api/etoile/reponse", lambda route: (envois.append(route.request.post_data_json), route.fulfill(json={"actif": True, "afficher": False, "url": URL, "essai": False})))
    page.context.route(URL, lambda route: route.fulfill(body="ok"))  # la nouvelle fenêtre aussi : jamais le réseau réel (CI du 19/11)
    page.goto(page.url_serveur + "/")
    page.locator("dialog[data-id='etoile'] button:has-text('Mettre une étoile')").wait_for()
    with page.context.expect_page() as nouvelle:
        page.locator("dialog[data-id='etoile'] button:has-text('Mettre une étoile')").click()
    assert nouvelle.value.url.startswith(URL)
    page.wait_for_function("!document.querySelector(\"dialog[data-id='etoile']\")")
    assert envois == [{"choix": "etoile"}]


def test_rien_quand_elle_n_est_pas_due(page):
    _etat(page, False)
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    assert page.locator("dialog[data-id='etoile']").count() == 0


def test_interrupteur_des_reglages(page):
    page.goto(page.url_serveur + "/#reglages/etoile")
    case = page.locator("[data-id='etoile-actif']")
    case.wait_for()
    assert case.is_checked()
    case.uncheck()
    page.wait_for_function("!document.querySelector(\"[data-id='etoile-actif']\").checked")
    case.check()
    assert not page.erreurs, page.erreurs
