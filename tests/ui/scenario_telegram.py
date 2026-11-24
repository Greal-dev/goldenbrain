"""Scénario des Réglages → Telegram : section affichée, discussions enregistrées dans [telegram], test de connexion
sans jeton qui échoue proprement. Jamais de jeton saisi : aucun appel au vrai Telegram (INV-TELEGRAM-1)."""


def test_reglages_telegram(page, serveur):
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.evaluate("location.hash = '#reglages/telegram'")
    page.wait_for_selector("[data-id=tg-avance]")
    page.click("[data-id=tg-avance] > summary")  # réglages avancés repliés sous l'assistant
    assert not page.locator("[data-id=tg-actif]").is_checked()  # désactivé par défaut
    page.fill("[data-id=tg-discussions]", "111, -222")
    page.evaluate("window.ancien = document.querySelector('[data-id=tg-resultat]')")
    with page.expect_response(lambda r: r.url.endswith("/api/telegram") and r.request.method == "PUT") as rep:
        page.click("[data-id=tg-enregistrer]")  # attendre la fin de l'enregistrement avant de lire le fichier
    assert rep.value.ok
    for _ in range(100):  # formulaire recréé : sondage côté test (la CSP interdit l'eval de wait_for_function)
        if page.evaluate("document.querySelector('[data-id=tg-resultat]') !== window.ancien"):
            break
        page.wait_for_timeout(50)
    else:
        raise AssertionError("formulaire Telegram non recréé après l'enregistrement")
    chemin = next(serveur.vault.parent.glob("*.toml"))
    for essai in range(20):  # Windows : lecture refusée le temps de os.replace (INV-INTERFACE-2)
        try:
            config = chemin.read_text("utf-8")
            break
        except PermissionError:
            page.wait_for_timeout(100)
    else:
        config = chemin.read_text("utf-8")
    assert '[telegram]' in config and 'discussions = ["111", "-222"]' in config and "jeton" not in config.split("[telegram]")[1]
    if not page.locator("[data-id=tg-avance]").evaluate("e => e.open"):
        page.click("[data-id=tg-avance] > summary")
    page.click("[data-id=tg-tester]")
    page.wait_for_selector("[data-id=tg-resultat] >> text=Échec", timeout=90000)  # sous charge, la réponse tarde
    assert "jeton du bot absent" in page.locator("[data-id=tg-resultat]").inner_text()
    assert not page.erreurs, page.erreurs


def test_assistant_de_bout_en_bout(page, serveur):
    """Accueil → assistant : bot, jeton saisi hors navigateur (terminal simulé, commande `saisir` réelle), nom lu,
    ancien webhook levé, discussion reconnue, test reçu, terminé. API Telegram factice : aucun réseau (INV-TELEGRAM-1)."""
    from orchestrateur import config as cfg, telegram_jeton
    from faux_telegram import CHAT, JETON
    page.request.put(page.url_serveur + "/api/telegram", data={"discussions": [], "actif": False},
                     headers={"X-Orchestrateur": "1"})  # état neuf, quel que soit le scénario précédent
    ouvert = []
    page.route("**/api/telegram/jeton/terminal", lambda route: (ouvert.append(route.request.post_data_json), route.fulfill(json={"ok": True, "motif": ""})))
    page.on("dialog", lambda d: d.accept())  # confirmation de la commande exacte
    page.goto(page.url_serveur + "/#aujourdhui")
    page.click("[data-id=au-telegram-aller]")  # invitation de l'accueil
    page.wait_for_selector("[data-id=tg-corps][data-etape=botfather]")
    assert "t.me/BotFather" in page.locator("[data-id=tg-corps] a").get_attribute("href")
    assert "/newbot" in page.locator("[data-id=tg-corps]").inner_text()
    assert "Quoi." in page.locator("[data-id=tg-aide]").inner_text()  # guide à côté
    page.click("[data-id=tg-botfather-ok]")
    page.wait_for_selector("[data-id=tg-corps][data-etape=jeton]")
    page.click("[data-id=tg-terminal]")
    page.wait_for_selector("[data-id=tg-terminal-etat]")
    assert ouvert and "telegram-jeton" in ouvert[0]["accord"]  # la commande montrée, rendue telle quelle
    # Ce que fait le terminal ouvert : la commande réelle, jeton « tapé » sans écho, vérifié par getMe, rangé dans le coffre.
    sortie = []
    assert telegram_jeton.saisir(cfg.charger(str(serveur.config)), lire=lambda _: JETON, sortie=sortie.append) == 0
    assert sortie[0] == "jeton enregistré pour @essai_bot" and JETON not in "".join(sortie)
    page.wait_for_selector("[data-id=tg-corps][data-etape=nom]", timeout=10000)  # détecté tout seul
    page.wait_for_selector("[data-id=tg-nom] >> text=@essai_bot")
    page.click("[data-id=tg-bon-bot]")
    page.wait_for_selector("[data-id=tg-corps][data-etape=webhook]")  # ancien webhook détecté
    # La page Réglages se redessine à chaque événement : le nom confirmé ne doit pas être redemandé (18/11).
    page.evaluate("location.hash = '#equipe'")
    page.wait_for_timeout(300)
    page.evaluate("location.hash = '#reglages/telegram'")
    page.wait_for_selector("[data-id=tg-corps][data-etape=webhook]")
    page.click("[data-id=tg-webhook-off]")
    page.wait_for_selector("[data-id=tg-corps][data-etape=discussion]")
    assert serveur.telegram.webhook == ""
    page.click("[data-id=tg-reconnaitre]")
    page.check(f"[data-id=tg-trouvee-{CHAT}]")
    page.click("[data-id=tg-autoriser]")
    page.wait_for_selector("[data-id=tg-corps][data-etape=test]")
    page.click("[data-id=tg-essai]")
    page.wait_for_selector("[data-id=tg-essai-ok]")
    assert [str(m["chat_id"]) for m in serveur.telegram.envoyes][-1] == str(CHAT)
    page.click("[data-id=tg-terminer]")
    page.wait_for_selector("[data-id=tg-fini]")
    assert JETON not in page.content()  # jamais réaffiché (INV-TELEGRAM-2)
    page.request.put(page.url_serveur + "/api/telegram", data={"actif": False}, headers={"X-Orchestrateur": "1"})
    assert not page.erreurs, page.erreurs
