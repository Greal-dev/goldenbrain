"""Scénario de la page « Décisions » (INV-DECISIONS-1) : adresse directe, question visible sans ouvrir la
fiche, décision sur place (réponse, acceptation), fermetures de revue cochées, lot de validations."""

import re

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}
BLOC = ("\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : fait\n- **Résultat** : {res}\n"
        "- **Essai** : lancer {res}\n- **Situation** : \n- **Reste à faire** : \n- **Prochain pas** : \n"
        "<!-- orchestrateur:fin -->\n")


def _a_valider(serveur, nom, titre, res):
    texte = univers.tache(titre, statut="fait", extra="session: s-dec\n") + BLOC.format(res=res)
    univers.ecrire(serveur.vault, f"Projets/C1-Decis/taches/{nom}.md", texte)


def _monde(serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Decis/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Decis\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Decis/taches/dc-q.md",
                   univers.tache("Question Decis", statut="retour-humain", extra='commentaire: "Quelle option : A ou B ?"\n'))
    univers.ecrire(serveur.vault, "Projets/C1-Decis/taches/dc-f1.md", univers.tache("Fermable Un Decis"))
    univers.ecrire(serveur.vault, "Projets/C1-Decis/taches/dc-f2.md", univers.tache("Fermable Deux Decis"))
    _a_valider(serveur, "dc-v1", "Validation Un Decis", "livrable-un")
    _a_valider(serveur, "dc-v2", "Validation Deux Decis", "livrable-deux")
    univers.ecrire(serveur.vault, "Projets/C1-Decis/taches/dc-v3.md",
                   univers.tache("Muette Trois Decis", statut="fait", extra="session: s-dec3\n"))


def carte(page, titre):
    return page.locator(".dc-reponse, .dc-validation", has=page.locator(".dc-titre", has_text=re.compile(rf"^{titre}$")))


def test_page_decisions_question_decision_sur_place_et_lot(page, serveur):
    _monde(serveur)
    p1 = page.request.post(serveur.url + "/api/propositions", headers=H, data={
        "type": "echeance", "tache": "dc-q", "valeur": "2031-05-05", "de": "agent", "motif": "m"}).json()
    assert p1["etat"] == "acceptee" and p1["auto"]  # INV-PROP-1 : geste de routine, appliqué d'office
    for t in ("dc-q", "dc-f1"):
        page.request.post(serveur.url + "/api/propositions", headers=H, data={
            "type": "perimetre", "tache": t, "valeur": "Seulement le volet A", "de": "agent", "motif": "recentrer"})
    for t, s in (("dc-f1", "cloture"), ("dc-f2", "abandonne")):
        page.request.post(serveur.url + "/api/propositions", headers=H,
                          data={"type": "fermer", "tache": t, "valeur": s, "de": "revue-dec", "motif": "obsolète"})
    page.goto(page.url_serveur + "/#decisions")
    expect(page.locator("#btn-decisions")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#n-decisions")).not_to_have_text("0")

    # La question est lisible sans ouvrir la fiche ; la validation montre résultat et essai.
    expect(carte(page, "Question Decis")).to_contain_text("Quelle option : A ou B ?")
    expect(carte(page, "Validation Un Decis")).to_contain_text("Résultat : livrable-un")
    expect(carte(page, "Validation Un Decis")).to_contain_text("Essai : lancer livrable-un")

    # Fiche muette : le sujet et le fait manquent ; « Faire documenter » relance l'agent de la tâche.
    assert page.locator(".dc-validation", has=page.locator(".dc-titre", has_text="Muette Trois Decis")).count() == 1
    muette = carte(page, "Muette Trois Decis")
    expect(muette.locator(".tag.muette")).to_have_text("Fiche muette")
    expect(carte(page, "Validation Un Decis")).not_to_contain_text("Fiche muette")
    expect(carte(page, "Validation Un Decis")).to_contain_text("De quoi il s’agit : Corps de Validation Un Decis.")
    expect(carte(page, "Validation Un Decis")).to_contain_text("Ce qui a été fait : fait")
    muette.locator("[data-documenter]").click()
    for _ in range(200):
        if carte(page, "Muette Trois Decis").locator(".tag.muette").count() == 0:
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("la fiche muette n'a pas été documentée")

    # Répondre sur place : le message part à la tâche.
    c = carte(page, "Question Decis")
    c.locator("textarea").fill("Option A")
    c.get_by_role("button", name="Répondre").click()
    for _ in range(200):  # le message relance l'agent factice, qui déclare la tâche terminée
        if page.request.get(serveur.url + "/api/taches/dc-q").json()["statut"] != "retour-humain":
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("la réponse n'a pas relancé la tâche")

    # Propositions à trancher : une entrée repliée par tâche émettrice, « Tout accepter » d'un clic (INV-PROP-1).
    lot = page.locator(".dc-proposition")
    expect(lot).to_have_count(1)
    expect(lot).to_contain_text("Propositions de")
    expect(lot.locator("li.dc-prop")).to_have_count(2)
    expect(lot.locator("li.dc-prop").first).to_have_attribute("title", "recentrer")
    lot.get_by_role("button", name="Tout accepter").click()
    expect(page.locator(".dc-proposition")).to_have_count(0, timeout=5000)

    # Geste appliqué d'office : listé à part, annulable depuis le journal.
    assert page.request.get(serveur.url + "/api/taches/dc-q").json()["frontmatter"].get("echeance")
    office = page.locator(".dc-office")
    # Un rafraîchissement de la page referme parfois le volet entre l'ouverture et le clic : on le rouvre.
    for _ in range(6):
        page.evaluate("() => { const o = document.querySelector('.dc-office'); if (o) o.open = true }")
        try:
            office.locator(f"li.dc-office-geste[data-n='{p1['n']}'] [data-annuler]").click(timeout=4000)
            break
        except PlaywrightTimeoutError:
            continue
    else:
        raise AssertionError("bouton « Annuler » du geste d'office introuvable")
    expect(page.locator(f"li.dc-office-geste[data-n='{p1['n']}']")).to_have_count(0, timeout=5000)
    assert not page.request.get(serveur.url + "/api/taches/dc-q").json()["frontmatter"].get("echeance")

    # Revue : seule la fermeture cochée est appliquée.
    revue = page.locator(".dc-revue")
    revue.locator("li", has_text="Fermable Un Decis").locator("input").check()
    revue.locator("[data-appliquer]").click()
    expect(revue.locator("li")).to_have_count(1, timeout=5000)
    assert page.request.get(serveur.url + "/api/taches/dc-f1").json()["statut"] == "cloture"
    assert page.request.get(serveur.url + "/api/taches/dc-f2").json()["statut"] == "a-faire"

    # Filtre « rapides » : la question ne se tranche pas en un clic.
    page.check("#dc-rapides")
    expect(carte(page, "Question Decis")).to_have_count(0)
    expect(carte(page, "Validation Un Decis")).to_have_count(1)

    # Lot : deux validations cochées, une seule action.
    carte(page, "Validation Un Decis").locator(".dc-coche").check()
    carte(page, "Validation Deux Decis").locator(".dc-coche").check()
    expect(page.locator("#dc-lot")).to_have_text("Valider la sélection (2)")
    page.click("#dc-lot")
    expect(carte(page, "Validation Un Decis")).to_have_count(0, timeout=5000)
    for t in ("dc-v1", "dc-v2"):
        assert page.request.get(serveur.url + f"/api/taches/{t}").json()["statut"] == "cloture"
    assert p1["n"]
    assert not page.erreurs, page.erreurs


def test_decision_repondue_disparait_et_ne_revient_pas_pendant_le_tour_de_l_agent(page, serveur):
    """Symptôme (22/11) : après la réponse, la décision restait affichée jusqu'à la conclusion de l'agent
    (INV-DECISIONS-2). Elle quitte la liste (mention « l'agent reprend ») et ne revient qu'en nouvelle entrée."""
    fichier = "Projets/C1-Decis/taches/dc-r.md"
    univers.ecrire(serveur.vault, "Projets/C1-Decis/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Decis\n---\n")
    univers.ecrire(serveur.vault, fichier, univers.tache("Reprise Decis", statut="retour-humain", extra='commentaire: "A ou B ?"\n'))
    page.goto(page.url_serveur + "/#decisions")
    c = carte(page, "Reprise Decis")
    c.locator("textarea").fill("Option A [lent 20]")
    c.get_by_role("button", name="Répondre").click()
    expect(carte(page, "Reprise Decis")).to_have_count(0, timeout=5000)
    expect(page.locator("[data-reprises]")).to_contain_text("Reprise Decis")
    for _ in range(100):  # le tour court ; le fichier retrouve le statut de retour (écriture tardive) : toujours masquée
        if page.request.get(serveur.url + "/api/taches/dc-r").json()["etat_execution"] == "en_cours":
            break
        page.wait_for_timeout(100)
    univers.ecrire(serveur.vault, fichier, univers.tache("Reprise Decis", statut="retour-humain", extra='commentaire: "A ou B ?"\n'))
    page.reload()
    page.goto(page.url_serveur + "/#decisions")
    expect(page.locator(".decisions")).to_contain_text("Décisions", timeout=5000)
    expect(carte(page, "Reprise Decis")).to_have_count(0)
    # L'agent s'arrête puis conclut à une nouvelle question : nouvelle entrée, nouvelle question.
    page.request.post(serveur.url + "/api/taches/dc-r/arret", headers=H)
    for _ in range(100):
        if page.request.get(serveur.url + "/api/taches/dc-r").json()["etat_execution"] != "en_cours":
            break
        page.wait_for_timeout(100)
    univers.ecrire(serveur.vault, fichier, univers.tache("Reprise Decis", statut="retour-humain", extra='commentaire: "Et pour B ?"\n'))
    page.reload()
    page.goto(page.url_serveur + "/#decisions")
    expect(carte(page, "Reprise Decis")).to_contain_text("Et pour B ?", timeout=5000)
    assert not page.erreurs, page.erreurs


def test_reponse_a_une_decision_s_affiche_dans_le_fil_avec_celle_de_l_agent(page, serveur):
    """Symptôme (28/11) : l'utilisateur répond à une décision, « il ne se passe rien » (ni écho, ni indicateur, ni la
    réponse de l'agent) et renvoie 3-4 fois le même message. Le message s'affiche aussitôt, un indicateur dit que l'agent
    répond, sa réponse arrive sans recharger, même si la décision a quitté la liste ; un seul envoi part."""
    univers.ecrire(serveur.vault, "Projets/C1-Decis/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Decis\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Decis/taches/dc-e.md",
                   univers.tache("Echange Decis", statut="retour-humain", extra='commentaire: "A ou B ?"\n'))
    envois = []
    page.on("request", lambda r: envois.append(r.url) if r.method == "POST" and r.url.endswith("/api/taches/dc-e/messages") else None)
    page.goto(page.url_serveur + "/#decisions")
    c = carte(page, "Echange Decis")
    c.locator("textarea").fill("Option A [lent 2]")
    bouton = c.get_by_role("button", name="Répondre")
    bouton.evaluate("b => { b.click(); b.click(); }")  # double envoi : la 2e pression part avant tout redessin
    echange = page.locator(".dc-echange", has_text="Echange Decis")
    expect(echange.locator(".msg.user")).to_contain_text("Option A", timeout=3000)
    expect(echange.locator(".activite")).to_be_visible()
    expect(echange.locator(".msg.agent")).to_contain_text("bonjour s-faux", timeout=10000)  # transcript du harnais factice
    expect(echange.locator(".activite")).to_have_count(0)
    assert len(envois) == 1, envois
    assert not page.erreurs, page.erreurs


def test_decision_reportee_disparait_jusqu_a_sa_date_puis_reapparait(page, serveur):
    """Symptôme (23/11) : « Reporter » ne retirait pas l'entrée ni sa pastille avant la nouvelle date (INV-DECISIONS-3)."""
    univers.ecrire(serveur.vault, "Projets/C1-Decis/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Decis\n---\n")
    fichier = "Projets/C1-Decis/taches/dc-p.md"
    univers.ecrire(serveur.vault, fichier, univers.tache("Report Decis", statut="retour-humain", extra='commentaire: "Plus tard ?"\n'))
    page.goto(page.url_serveur + "/#decisions")
    c = carte(page, "Report Decis")
    expect(c).to_have_count(1)
    expect(page.locator("#n-decisions")).not_to_have_text("0")
    avant = int(page.locator("#n-decisions").inner_text())
    c.locator(".dc-report input[type=date]").fill("2031-05-05")
    c.get_by_role("button", name="Reporter").click()
    expect(carte(page, "Report Decis")).to_have_count(0, timeout=5000)
    expect(page.locator("#n-decisions")).to_have_text(str(avant - 1), timeout=5000)
    # La date atteinte (ici : la veille), l'entrée revient d'elle-même.
    univers.ecrire(serveur.vault, fichier, univers.tache(
        "Report Decis", statut="retour-humain", extra='commentaire: "Plus tard ?"\necheance: 2020-01-01\nreporte_jusqu_au: 2020-01-01\n'))
    page.goto(page.url_serveur + "/#decisions")
    page.reload()
    expect(carte(page, "Report Decis")).to_have_count(1, timeout=5000)
    assert not page.erreurs, page.erreurs
