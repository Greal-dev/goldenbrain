"""Scénario « Modifier un message envoyé » : avertissement, case code, renvoi, version précédente (INV-RETOUR-1, INV-RETOUR-2)."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet
from playwright.sync_api import expect


def _envoyer(page, texte, n):
    page.fill(".composer textarea", texte)
    page.press(".composer textarea", "Control+Enter")
    expect(page.locator(".msg.user")).to_have_count(n, timeout=10000)
    expect(page.locator(".msg.agent.final")).to_have_count(n, timeout=10000)


def test_modifier_un_message_retire_la_suite_et_garde_l_ancienne_version(page, serveur):
    projet(serveur, "C1-Modifier", {"mo-un": ("Un MO", "")})
    charger(page)
    ligne(page, "Un MO").click()
    expect(page.locator(".d-titre")).to_have_text("Un MO")
    _envoyer(page, "Premier envoi [journaux]", 1)
    _envoyer(page, "Second envoi [journaux]", 2)
    page.locator(".msg.user").first.hover()
    page.locator(".msg.user").first.locator(".msg-modifier").click()
    dlg = page.locator("dialog.dlg")
    expect(dlg).to_be_visible()
    expect(dlg.locator(".modif-alerte")).to_contain_text("2 échanges (celui-ci et les suivants) seront retirés")
    expect(dlg).to_contain_text("une nouvelle conversation commence")
    expect(dlg.locator("input[name=code]")).to_be_disabled()  # aucun point de restauration : case grisée
    expect(dlg.get_by_text("Restaurer aussi le code à cet instant")).to_be_visible()
    expect(dlg.locator("textarea[name=texte]")).to_have_value("Premier envoi [journaux]")
    dlg.locator("textarea[name=texte]").fill("Premier envoi corrigé [journaux]")
    dlg.get_by_role("button", name="Renvoyer").click()
    expect(page.locator(".msg.user")).to_have_count(1, timeout=10000)
    expect(page.locator(".msg.user")).to_contain_text("Premier envoi corrigé")
    expect(page.locator(".msg.agent.final")).to_have_count(1, timeout=10000)
    versions = page.locator(".modif-versions")
    expect(versions.locator("summary").first).to_have_text("Versions précédentes (1)")
    versions.locator("summary").first.click()
    versions.locator(".modif-version summary").click()
    expect(versions.locator(".modif-version .msg.user")).to_have_count(2)
    expect(versions.locator(".modif-version")).to_contain_text("Second envoi")
    assert not page.erreurs, page.erreurs


def test_repondre_a_partir_d_une_reponse_de_l_ia(page, serveur):
    projet(serveur, "C1-Repondre", {"re-un": ("Un RE", "")})
    charger(page)
    ligne(page, "Un RE").click()
    expect(page.locator(".d-titre")).to_have_text("Un RE")
    _envoyer(page, "Question A [journaux]", 1)
    _envoyer(page, "Question B [journaux]", 2)
    premiere = page.locator(".msg.agent.final").first
    premiere.hover()
    premiere.locator(".msg-repondre").click()
    dlg = page.locator("dialog.dlg")
    expect(dlg).to_be_visible()
    expect(dlg.locator("h3")).to_have_text("Répondre à partir d’ici")
    expect(dlg.locator(".modif-alerte")).to_contain_text("1 échange (celui qui suit cette réponse) sera retiré")
    expect(dlg.get_by_text("Restaurer aussi le code à cet instant")).to_be_visible()
    expect(dlg.locator("textarea[name=texte]")).to_have_value("")
    dlg.locator("textarea[name=texte]").fill("Question C [journaux]")
    dlg.get_by_role("button", name="Envoyer").click()
    expect(page.locator(".msg.user")).to_have_count(2, timeout=10000)
    expect(page.locator(".msg.user").nth(1)).to_contain_text("Question C")
    expect(page.locator(".conv")).not_to_contain_text("Question B")
    expect(page.locator(".msg.agent.final")).to_have_count(2, timeout=10000)
    # Dernière réponse : le bouton ramène simplement à la saisie, rien n'est retiré.
    derniere = page.locator(".msg.agent.final").last
    derniere.hover()
    derniere.locator(".msg-repondre").click()
    expect(page.locator(".composer textarea")).to_be_focused()
    expect(page.locator("dialog.dlg")).to_have_count(0)
    assert not page.erreurs, page.erreurs
