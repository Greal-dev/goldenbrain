"""Scénario des Réglages « PC connectés » (INV-DISTANT-1, INV-DISTANT-4) : création d'un jeton montré
une fois, annonce d'un exécuteur (faite ici par requête, comme le ferait `orch executeur`), puis
révocation."""

import re

from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def test_pc_connectes_jeton_annonce_puis_revocation(page, serveur):
    page.goto(page.url_serveur + "/#reglages/executeurs")
    page.wait_for_selector("[data-id=executeurs] [data-id=exe-liste]")
    page.fill("[data-id=exe-nom]", "pc-essai")
    with page.expect_response(lambda r: r.url.endswith("/api/executeurs/jetons")) as rep:
        page.click("[data-id=exe-creer]")
    jeton = rep.value.json()["jeton"]
    expect(page.locator("[data-id=exe-jeton]")).to_contain_text("montrée une seule fois")
    ligne = page.locator("[data-id=exe-pc-essai]")
    expect(ligne).to_contain_text("jamais vu")
    try:
        r = page.request.post(page.url_serveur + "/api/executeurs/annonce",
                              headers={**H, "X-Orch-Jeton": jeton},
                              data={"harnais": ["faux"], "places": 2,
                                    "memoire": {"libre": 6 * 1024 ** 3, "total": 16 * 1024 ** 3}})
        assert r.status == 200, r.text()
        expect(ligne).to_contain_text("connecté · 6 / 16 Go libres · 0/2 séance de travail", timeout=5000)
        expect(ligne).to_contain_text("faux")
        page.once("dialog", lambda d: d.accept())
        page.click("[data-id=exe-revoquer-pc-essai]")
        expect(page.locator("[data-id=exe-pc-essai]")).to_have_count(0, timeout=5000)
        r = page.request.post(page.url_serveur + "/api/executeurs/annonce",
                              headers={**H, "X-Orch-Jeton": jeton}, data={})
        assert r.status == 401
    finally:
        page.request.delete(page.url_serveur + "/api/executeurs/jetons/pc-essai", headers=H)
    assert not page.erreurs, page.erreurs


def test_appairage_par_code_affiche_puis_consomme(page, serveur):
    page.goto(page.url_serveur + "/#reglages/executeurs")
    page.wait_for_selector("[data-id=executeurs] [data-id=exe-liste]")
    page.fill("[data-id=exe-nom]", "pc-code")
    page.click("[data-id=exe-appairer]")
    code = page.locator("[data-id=exe-code]")
    expect(code).to_have_text(re.compile(r"^[A-Z2-9]{4}-[A-Z2-9]{4}$"))
    expect(page.locator("[data-id=exe-appairage]")).to_contain_text("--code")
    valeur = code.inner_text()
    try:
        # l'exécuteur saisit le code (sans jeton) et reçoit le sien ; le code disparaît de l'écran
        r = page.request.post(page.url_serveur + "/api/executeurs/appairage/echange",
                              headers=H, data={"code": valeur})
        assert r.status == 200 and r.json()["nom"] == "pc-code" and r.json()["jeton"]
        expect(page.locator("[data-id=exe-appairage]")).to_have_count(0, timeout=5000)
        expect(page.locator("[data-id=exe-pc-code]")).to_be_visible()
        assert page.request.post(page.url_serveur + "/api/executeurs/appairage/echange",
                                 headers=H, data={"code": valeur}).status == 400
    finally:
        page.request.delete(page.url_serveur + "/api/executeurs/jetons/pc-code", headers=H)
    assert not page.erreurs, page.erreurs


def test_etat_des_prerequis_et_bouton_reparer(page, serveur):
    page.goto(page.url_serveur + "/#reglages/executeurs")
    page.wait_for_selector("[data-id=executeurs] [data-id=exe-liste]")
    page.fill("[data-id=exe-nom]", "pc-etat")
    with page.expect_response(lambda r: r.url.endswith("/api/executeurs/jetons")) as rep:
        page.click("[data-id=exe-creer]")
    jeton = rep.value.json()["jeton"]
    prerequis = [{"id": "git", "libelle": "git", "etat": "manquant", "genre": "outil", "optionnel": False,
                  "commande": "winget install --id Git.Git -e", "instructions": "", "attend": []},
                 {"id": "tailscale", "libelle": "Tailscale", "etat": "ok", "genre": "outil", "optionnel": False,
                  "commande": "", "instructions": "", "attend": []}]
    entetes = {**H, "X-Orch-Jeton": jeton}
    try:
        r = page.request.post(page.url_serveur + "/api/executeurs/annonce", headers=entetes,
                              data={"harnais": ["faux"], "prerequis": prerequis})
        assert r.status == 200, r.text()
        zone = page.locator("[data-id=exe-prerequis-pc-etat]")
        expect(zone).to_contain_text("1 étape à faire", timeout=5000)
        expect(page.locator("[data-id=exe-etape-pc-etat-git]")).to_contain_text("manquant")
        # l'accord porte la commande exacte ; le chef met l'ordre en file pour l'exécuteur
        page.once("dialog", lambda d: (assert_commande(d.message), d.accept()))
        page.click("[data-id=exe-reparer-pc-etat-git]")
        ordres = page.request.get(page.url_serveur + "/api/executeurs/travail?attente=1", headers=entetes).json()["ordres"]
        assert ordres == [{"type": "reparer", "etape": "git", "accord": "winget install --id Git.Git -e"}]
        # l'exécuteur rend son résultat dans l'annonce suivante
        prerequis[0]["etat"] = "ok"
        page.request.post(page.url_serveur + "/api/executeurs/annonce", headers=entetes,
                          data={"prerequis": prerequis, "reparation": {"etape": "git", "etat": "ok", "code": 0, "message": ""}})
        expect(zone).to_contain_text("tout est prêt", timeout=5000)
        expect(page.locator("[data-id=exe-reparation-pc-etat]")).to_contain_text("git")
    finally:
        page.request.delete(page.url_serveur + "/api/executeurs/jetons/pc-etat", headers=H)
    assert not page.erreurs, page.erreurs


def test_reponse_tardive_n_ecrase_pas_l_etat_recent_des_prerequis(page, serveur):
    """Régression : « tout est prêt » ne revenait pas après réparation (lecture ancienne arrivée en retard)."""
    page.goto(page.url_serveur + "/#reglages/executeurs")
    page.wait_for_selector("[data-id=executeurs] [data-id=exe-liste]")
    page.fill("[data-id=exe-nom]", "pc-tardif")
    with page.expect_response(lambda r: r.url.endswith("/api/executeurs/jetons")) as rep:
        page.click("[data-id=exe-creer]")
    jeton = rep.value.json()["jeton"]
    entetes = {**H, "X-Orch-Jeton": jeton}
    etape = {"id": "git", "libelle": "git", "etat": "manquant", "genre": "outil", "optionnel": False,
             "commande": "winget install --id Git.Git -e", "instructions": "", "attend": []}
    premiere = []

    def retarder(route):
        if route.request.method != "GET" or premiere:
            return route.continue_()
        premiere.append((route, route.fetch()))  # corps pris maintenant (ancien), livré plus tard par le test

    motif = re.compile(r"/api/executeurs$")
    page.route(motif, retarder)
    try:
        def post(donnees):
            return page.request.post(page.url_serveur + "/api/executeurs/annonce", headers=entetes, data=donnees)

        post({"prerequis": [etape]})
        for _ in range(50):  # attendre que la lecture « ancienne » soit partie avant la seconde annonce
            if premiere:
                break
            page.wait_for_timeout(100)
        assert premiere, "la lecture ancienne n'a pas été déclenchée"
        post({"prerequis": [{**etape, "etat": "ok"}], "reparation": {"etape": "git", "etat": "ok", "code": 0, "message": ""}})
        zone = page.locator("[data-id=exe-prerequis-pc-tardif]")
        expect(zone).to_contain_text("tout est prêt", timeout=5000)
        route, reponse = premiere[0]
        route.fulfill(response=reponse)  # la lecture ancienne arrive après la récente
        page.wait_for_timeout(500)
        expect(zone).to_contain_text("tout est prêt")
    finally:
        page.unroute(motif)
        page.request.delete(page.url_serveur + "/api/executeurs/jetons/pc-tardif", headers=H)


def assert_commande(message):
    assert "winget install --id Git.Git -e" in message and "pc-etat" in message
