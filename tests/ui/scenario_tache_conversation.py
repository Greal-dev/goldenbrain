"""Scénarios de tâche et de conversation : en-tête, tour de l'agent, étapes à la demande, changement de parent."""

import re

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def _ouvrir(page, serveur, nom, taches, titre):
    projet(serveur, nom, taches)
    charger(page)
    ligne(page, titre).click()
    expect(page.locator(".d-titre")).to_have_text(titre)


def _envoyer(page, texte):
    page.fill(".composer textarea", texte)
    page.press(".composer textarea", "Control+Enter")


def test_tache_en_tete_et_fiche(page, serveur):
    _ouvrir(page, serveur, "C1-TacheEntete", {"te-un": ("Un TE", "")}, "Un TE")
    expect(page.locator(".d-une select[aria-label='Statut']")).to_have_value("a-faire")
    expect(page.locator(".d-meta .session")).to_have_text("pas de conversation")
    expect(page.locator(".d-tete nav.fil")).to_contain_text("TacheEntete")
    expect(page.locator(".conv .vide")).to_have_text("Aucun échange pour le moment.")
    expect(page.locator(".d-details .corps summary")).to_have_text("Contenu de la tâche")
    assert not page.erreurs, page.erreurs


def test_conversation_tour_complet_et_message_affiche(page, serveur):
    _ouvrir(page, serveur, "C1-ConvTour", {"ct-un": ("Un CT", "")}, "Un CT")
    _envoyer(page, "Bonjour agent")
    page.wait_for_selector("text=en bonne voie", timeout=10000)  # fiche rendue par le harnais factice
    expect(page.locator(".msg.agent.final")).to_contain_text("bonjour s-faux")
    expect(page.locator(".d-meta .session")).to_contain_text("conversation s-faux")  # INV-EXEC-3
    expect(page.locator(".composer textarea")).to_have_value("")
    assert not page.erreurs, page.erreurs


def test_conversation_etapes_masquees_puis_affichees(page, serveur):
    _ouvrir(page, serveur, "C1-ConvEtapes", {"ce-un": ("Un CE", "")}, "Un CE")
    _envoyer(page, "Montre tes étapes")
    page.wait_for_selector(".msg.agent.final")
    bascule = page.locator(".btn-etapes")
    expect(bascule).to_have_attribute("aria-pressed", "false")
    expect(page.locator(".conv")).to_have_class(re.compile(r"masque"))
    expect(page.locator(".etapes-n")).to_contain_text("1 étape masquée")
    bascule.click()  # tout s'affiche, sans nouveau rendu
    expect(bascule).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".conv")).not_to_have_class(re.compile(r"masque"))
    page.reload()  # le choix est mémorisé (localStorage)
    page.wait_for_selector(".msg.agent.final")
    expect(page.locator(".btn-etapes")).to_have_attribute("aria-pressed", "true")
    page.locator(".btn-etapes").click()
    expect(page.locator(".btn-etapes")).to_have_attribute("aria-pressed", "false")
    assert not page.erreurs, page.erreurs


def test_conversation_compteur_deplie_un_tour(page, serveur):
    _ouvrir(page, serveur, "C1-ConvCompteur", {"cc-un": ("Un CC", "")}, "Un CC")
    _envoyer(page, "Déplie-moi")
    page.wait_for_selector(".msg.agent.final")
    compteur = page.locator(".etapes-n")
    expect(compteur).to_have_attribute("aria-expanded", "false")
    compteur.click()  # ce tour seulement
    expect(compteur).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".tour-c").first).to_have_class(re.compile(r"deplie"))
    compteur.click()
    expect(compteur).to_have_attribute("aria-expanded", "false")
    assert not page.erreurs, page.erreurs


def test_tache_changer_de_parent_depuis_l_en_tete(page, serveur):
    _ouvrir(page, serveur, "C1-ChangeParent", {"cp-mere": ("Mère CP", ""), "cp-fille": ("Fille CP", "")}, "Fille CP")
    expect(page.locator(".d-rattache")).to_contain_text("ChangeParent")
    page.get_by_role("button", name="Changer…").click()
    dlg = page.locator("dialog.dlg")
    expect(dlg).to_be_visible()
    dlg.get_by_role("combobox").fill("Mère CP")
    dlg.get_by_role("option", name="Mère CP").click()
    expect(page.locator(".d-rattache")).to_contain_text("Mère CP")  # la tâche reste ouverte, rattachement à jour
    expect(page.locator(".d-titre")).to_have_text("Fille CP")
    fichier = serveur.vault / "Projets/C1-ChangeParent/taches/cp-fille.md"
    assert "parent:" in fichier.read_text(encoding="utf-8") and "cp-mere" in fichier.read_text(encoding="utf-8")
    assert not page.erreurs, page.erreurs


def test_echec_de_tour_message_du_systeme_et_repere(page, serveur):
    _ouvrir(page, serveur, "C1-EchecTour", {"et-un": ("Un ET", "")}, "Un ET")
    _envoyer(page, "[echec] travaille")
    msg = page.locator(".msg.systeme")
    expect(msg).to_contain_text("Quota épuisé", timeout=10000)
    expect(msg).to_contain_text("Reprise possible : 5 hours")
    expect(msg.locator("header b")).to_have_text("GoldenBrain · échec de la séance de travail")
    expect(ligne(page, "Un ET").locator(".echec")).to_have_count(1)  # repère dans l'arbre
    _envoyer(page, "reprends")  # tour réussi : le repère s'efface, le message reste
    page.wait_for_selector("text=en bonne voie", timeout=10000)
    expect(ligne(page, "Un ET").locator(".echec")).to_have_count(0)
    expect(page.locator(".msg.systeme")).to_have_count(1)
    assert not page.erreurs, page.erreurs


def test_quota_epuise_tache_en_pause_reprendre_maintenant_puis_arreter(page, serveur):
    _ouvrir(page, serveur, "C1-PauseQuota", {"pq-un": ("Un PQ", "")}, "Un PQ")
    _envoyer(page, "[echec] travaille")
    expect(page.locator(".d-une [data-id=main-phrase]")).to_contain_text("En pause : quota faux, reprise à", timeout=10000)  # INV-MAIN-1 : la pastille dit « En file », la phrase le motif
    expect(ligne(page, "Un PQ").locator(".echec")).to_have_attribute("title", re.compile("En pause : quota faux"))
    page.get_by_role("button", name="Reprendre maintenant").click()  # relance aussitôt : échoue encore (factice)
    expect(page.locator(".msg.systeme")).to_have_count(2, timeout=10000)
    expect(page.locator(".d-une .etat.en_pause")).to_be_visible()
    page.get_by_role("button", name="Arrêter").click()  # annule le réveil
    expect(page.locator(".d-une .etat.en_pause")).to_have_count(0)
    expect(page.get_by_role("button", name="Reprendre maintenant")).to_have_count(0)
    assert not page.erreurs, page.erreurs


def test_tour_interrompu_affiche_relancer_et_reprend_la_session(page, serveur):
    # Anomalie A3 de la recette du 15/11 : un tour interrompu n'offrait aucun moyen de relancer.
    _ouvrir(page, serveur, "C1-ConvRelance", {"cr-un": ("Un CR", "")}, "Un CR")
    _envoyer(page, "[lent 60] travaille longtemps")
    page.get_by_role("button", name="Arrêter").click()
    expect(page.locator(".d-une .etat.interrompu")).to_have_attribute("data-main", "humain")  # pastille « Action humaine nécessaire » (renvoyer)
    page.get_by_role("button", name="Relancer").click()
    page.wait_for_selector("text=en bonne voie", timeout=10000)  # le tour repris a rendu sa fiche
    expect(page.get_by_role("button", name="Relancer")).to_have_count(0)
    expect(page.locator(".d-une .etat.interrompu")).to_have_count(0)  # plus rien d'interrompu
    assert not page.erreurs, page.erreurs
