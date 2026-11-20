"""Scénario des Réglages « Agents simultanés » : choix du mode, plafond en Go, persistance relue."""

H = {"X-Orchestrateur": "1"}


CLES = ("mode", "simultanes_max", "garde_max", "marge_pct", "plafond", "unite")


def test_reglages_agents_simultanes_trois_modes_et_plafond_en_go(page, serveur):
    # Le serveur est partagé : on rend le réglage tel qu'on l'a trouvé (un nombre fixe abaissé
    # bridait les scénarios suivants ; constat d'intégration du 15/11).
    initial = page.request.get(page.url_serveur + "/api/simultanes").json()
    try:
        page.goto(page.url_serveur + "/#reglages/simultanes")
        page.wait_for_selector("[data-id=sim-fixe]")
        assert page.locator("[data-id=sim-fixe]").is_checked()
        with page.expect_response(lambda r: r.url.endswith("/api/simultanes") and r.request.method == "PUT") as rep:
            page.fill("[data-id=sim-nombre]", "3")
            page.locator("[data-id=sim-nombre]").dispatch_event("change")
        assert rep.value.json()["simultanes_max"] == 3

        page.check("[data-id=sim-plafond]")
        page.wait_for_selector("[data-id=sim-unite]")
        page.evaluate("document.querySelector('[data-id=sim-plafond-valeur]').dataset.ancien = '1'")
        with page.expect_response(lambda r: r.url.endswith("/api/simultanes") and r.request.method == "PUT"):
            page.select_option("[data-id=sim-unite]", "go")
        # La réponse précède le redessin : saisir avant lui enverrait la valeur du champ recréé.
        page.wait_for_selector("[data-id=sim-plafond-valeur]:not([data-ancien])")
        page.fill("[data-id=sim-plafond-valeur]", "6")
        page.locator("[data-id=sim-plafond-valeur]").dispatch_event("change")
        page.wait_for_selector("[data-id=sim-etat] >> text=seuil 6 Go")

        page.check("[data-id=sim-optimiser]")
        page.wait_for_selector("[data-id=sim-marge]")
        assert page.locator("[data-id=sim-garde]").input_value() == "10"

        page.reload()  # le réglage est relu du serveur (config.toml)
        page.wait_for_selector("[data-id=sim-optimiser]:checked")
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(page.url_serveur + "/api/simultanes", headers=H, data={k: initial[k] for k in CLES})
        rendu = page.request.get(page.url_serveur + "/api/simultanes").json()
        assert {k: rendu[k] for k in CLES} == {k: initial[k] for k in CLES} and not rendu["pauses"]
