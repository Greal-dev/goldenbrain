"""Scénario des Réglages « Performance ↔ Économie » : curseur à cinq positions, famille par défaut,
repère de l'en-tête, persistance relue (INV-ECO-1)."""

H = {"X-Orchestrateur": "1"}
CLES = ("position", "famille_defaut")


def test_reglages_curseur_economie_et_repere_d_entete(page, serveur):
    initial = page.request.get(page.url_serveur + "/api/economie").json()
    try:
        page.goto(page.url_serveur + "/#reglages/economie")
        page.wait_for_selector("[data-id=eco-position]")
        page.wait_for_selector("[data-id=eco-repere] >> text=Intelligent")
        with page.expect_response(lambda r: r.url.endswith("/api/economie") and r.request.method == "PUT") as rep:
            page.fill("[data-id=eco-position]", "0")
            page.locator("[data-id=eco-position]").dispatch_event("change")
        assert rep.value.json()["position"] == "economie_max"
        page.wait_for_selector("[data-id=eco-motif] >> text=Économie max")
        page.wait_for_selector("[data-id=eco-repere] >> text=Économie max")
        with page.expect_response(lambda r: r.url.endswith("/api/economie") and r.request.method == "PUT"):
            page.select_option("[data-id=eco-famille]", "opus")
        page.reload()  # relu du serveur (config.toml)
        page.wait_for_selector("[data-id=eco-position]")
        assert page.locator("[data-id=eco-position]").input_value() == "0"
        assert page.locator("[data-id=eco-famille]").input_value() == "opus"
        page.wait_for_selector("[data-id=eco-conso]")
        assert not page.erreurs, page.erreurs
    finally:
        page.request.put(page.url_serveur + "/api/economie", headers=H, data={k: initial[k] for k in CLES})
