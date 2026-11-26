"""Scénario « routines programmées » : création depuis le bandeau, horloge et prochaine exécution dans
l'arbre à la place du statut, « Exécuter maintenant » avec issue et historique, pause, filtre « Routines »
(INV-ROUTINE-5)."""

import aides_arbre
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne
from playwright.sync_api import expect


def test_routine_creee_visible_executee_mise_en_pause_et_filtree(page, serveur):
    aides_arbre.projet(serveur, "C1-Routines", {"rt-ordinaire": ("Ordinaire Rt", "")})
    charger(page)
    assert ligne(page, "Routines").locator('.act-ligne[data-act="routine"]').count() == 1

    page.locator("#btn-routine").click()
    dlg = page.locator("dialog")
    dlg.locator("[name=titre]").fill("Veille Rt")
    dlg.locator("[name=consigne]").fill("Relis les nouvelles.")
    dlg.locator("[name=programme]").fill("chaque jour 08:00")
    dlg.locator("select[name=conteneur]").select_option(label="Routines")
    dlg.locator("button[type=submit]").click()

    bloc = page.locator(".routine-bloc")
    expect(bloc).to_contain_text("Prochaine exécution")
    badge = ligne(page, "Veille Rt").locator(".badge-st")
    expect(badge).to_have_class("badge-st bs-routine")
    expect(badge).to_contain_text("⏰")

    bloc.get_by_role("button", name="Exécuter maintenant").click()
    expect(ligne(page, "Veille Rt").locator(".issue.i-reussie")).to_have_count(1, timeout=15000)
    expect(page.locator(".routine-bloc .r-hist summary")).to_have_text("Historique (1)")

    page.locator(".routine-bloc").get_by_role("button", name="Mettre en pause").click()
    expect(ligne(page, "Veille Rt").locator(".badge-st")).to_contain_text("routine en pause")
    expect(page.locator(".routine-bloc")).to_contain_text("Routine en pause")

    page.click("#btn-filtres")
    page.locator("#f-routines").check()
    titres = page.locator("#arbre .ligne.t-tache .titre").all_inner_texts()
    assert "Veille Rt" in titres and "Ordinaire Rt" not in titres
    page.locator("#f-raz").click()
    assert not page.erreurs
