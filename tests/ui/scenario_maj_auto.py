"""Scénario de la mise à jour automatique (INV-MAJ-3) : réglage dans Réglages (relu du serveur) et bandeaux
(préparation, « Mis à jour vers … », incident). Le serveur de test est partagé : le réglage est rendu tel que trouvé ;
les bandeaux viennent d'un `/api/etat` altéré par `page.route` (aucune vraie mise à jour n'est tentée)."""

from conftest import deplier_infos

H = {"X-Orchestrateur": "1"}


def _etat_avec(page, maj_auto):
    def gerer(route):
        try:
            corps = route.fetch().json()
        except Exception:  # page fermée pendant une sonde de fond
            return
        corps["version"] = {**corps["version"], "a_jour": True, "maj_auto": maj_auto}
        route.fulfill(json=corps)
    page.route("**/api/etat", gerer)


BASE = {"reglage": {"actif": True, "delai_min": 30, "fenetre_debut": "", "fenetre_fin": ""}, "phase": "veille",
        "cible": "", "attendus": 0, "gel": False, "bandeau": None, "incident": None}


def test_reglage_mise_a_jour_automatique_desactive_par_defaut_puis_persiste(page, serveur):
    initial = page.request.get(page.url_serveur + "/api/maj-auto").json()["reglage"]
    try:
        page.goto(page.url_serveur + "/#reglages/maj-auto")
        page.wait_for_selector("[data-id=maj-auto-actif]")
        assert initial["actif"] is False and not page.locator("[data-id=maj-auto-actif]").is_checked()
        with page.expect_response(lambda r: r.url.endswith("/api/maj-auto") and r.request.method == "PUT") as rep:
            page.check("[data-id=maj-auto-actif]")
        assert rep.value.json()["reglage"]["actif"] is True
        page.fill("[data-id=maj-auto-delai]", "45")
        with page.expect_response(lambda r: r.url.endswith("/api/maj-auto") and r.request.method == "PUT"):
            page.evaluate("document.querySelector('[data-id=maj-auto-debut]').dataset.ancien = '1'")
            page.click("[data-id=maj-auto-delai-ok]")  # le formulaire se redessine avec la valeur du serveur
        # La réponse précède le redessin : saisir avant lui perdrait la fenêtre (champs remplacés).
        page.wait_for_selector("[data-id=maj-auto-debut]:not([data-ancien])")
        page.fill("[data-id=maj-auto-debut]", "22:00")
        page.fill("[data-id=maj-auto-fin]", "06:00")
        with page.expect_response(lambda r: r.url.endswith("/api/maj-auto") and r.request.method == "PUT"):
            page.click("[data-id=maj-auto-fenetre-ok]")
        page.reload()
        page.wait_for_selector("[data-id=maj-auto-actif]:checked")
        assert page.locator("[data-id=maj-auto-delai]").input_value() == "45"
        assert page.locator("[data-id=maj-auto-debut]").input_value() == "22:00"
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(page.url_serveur + "/api/maj-auto", headers=H, data=initial)


def test_bandeau_apres_mise_a_jour_puis_fermer(page, serveur):
    _etat_avec(page, {**BASE, "bandeau": {"version": "abc1234", "a": "03:12", "reprises": 2}})
    fermetures = []
    page.route("**/api/maj-auto/bandeau", lambda r: (fermetures.append(r.request.method), r.fulfill(status=200, json={})))
    page.goto(page.url_serveur + "/")
    deplier_infos(page)
    bandeau = page.locator("#maj-auto")
    bandeau.wait_for()
    assert "Mis à jour vers abc1234 à 03:12 ; 2 tâches reprises." in bandeau.inner_text()
    bandeau.locator("button:has-text('Fermer')").click()
    bandeau.wait_for(state="hidden")
    assert fermetures == ["DELETE"]


def test_bandeau_preparation_et_incident_avec_geste(page, serveur):
    _etat_avec(page, {**BASE, "phase": "gel", "gel": True, "attendus": 1})
    page.goto(page.url_serveur + "/")
    deplier_infos(page)
    page.wait_for_selector("#maj-auto >> text=Mise à jour en préparation")
    assert "aucune nouvelle séance de travail ne démarre" in page.locator("#maj-auto").inner_text()
    page.unroute("**/api/etat")
    _etat_avec(page, {**BASE, "incident": {"cause": "la nouvelle version ne se charge pas", "geste": "attendre une version corrigée",
                                            "version": "abc", "a": "03:12"}})
    page.reload()
    deplier_infos(page)
    page.wait_for_selector("#maj-auto >> text=abandonnée")
    texte = page.locator("#maj-auto").inner_text()
    assert "la nouvelle version ne se charge pas" in texte and "Que faire : attendre une version corrigée" in texte
