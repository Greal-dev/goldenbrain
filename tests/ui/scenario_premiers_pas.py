"""Premiers pas et modèles de tâches (INV-PREMIERS-PAS-1, INV-MODELES-1) : la liste des assistants IA dit
comment installer celui qui manque, la démonstration crée une tâche qui aboutit, un modèle pré-remplit
« Nouvelle tâche » sans rien créer.
Captures dans `GB_CAPTURES` si posé (fiche de la tâche), sinon dans le dossier temporaire du test.
"""

import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect


def fichiers(racine):
    return {p.relative_to(racine).as_posix() for p in racine.rglob("*") if p.is_file()}


@pytest.fixture(autouse=True)
def rendre_le_serveur(serveur):
    """Le serveur est partagé : le scénario retire la tâche de démonstration et l'état des premiers pas."""
    avant = fichiers(serveur.vault)
    yield
    for f in fichiers(serveur.vault) - avant:
        (serveur.vault / f).unlink()
    (serveur.dossier / "donnees" / "etat" / "premiers-pas.json").unlink(missing_ok=True)


@pytest.fixture
def captures(tmp_path):
    return Path(os.environ.get("GB_CAPTURES") or tmp_path)


def test_premiers_pas_puis_demonstration(page, serveur, captures):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(page.url_serveur + "/#reglages/premiers-pas")
    page.click('[data-id="revoir-premiers-pas"]')
    page.wait_for_selector('[data-id="pp-liste"]')
    # Claude Code absent du poste factice : commande à copier et page officielle ; « faux » est prêt.
    claude = page.locator('[data-id="pp-claude"]')
    expect(claude).to_have_attribute("data-etat", "absent")
    claude.locator("summary").click()
    assert page.locator('[data-id="pp-commande-claude"]').inner_text().strip()
    assert page.locator('[data-id="pp-lien-claude"]').get_attribute("href").startswith("https://")
    expect(page.locator('[data-id="pp-faux"]')).to_have_attribute("data-etat", "pret")
    page.screenshot(path=str(captures / "premiers-pas-1-assistants.png"))
    page.click('[data-id="pp-continuer"]')
    expect(page.locator('[data-id="pp-choix"]')).to_have_value("faux")
    page.screenshot(path=str(captures / "premiers-pas-2-demonstration.png"))
    with page.expect_response(lambda r: r.url.endswith("/api/taches") and r.request.method == "POST") as rep:
        page.click('[data-id="pp-lancer"]')
    assert rep.value.status == 201
    ident = rep.value.json()["id"]
    expect(page.locator('[data-id="premiers-pas"]')).to_have_count(0)
    expect(page.locator(".d-titre")).to_have_text("Faire connaissance avec mon assistant IA")
    fin = time.time() + 20
    while time.time() < fin:  # la démonstration aboutit : fiche rendue, tâche terminée
        t = page.evaluate(f"fetch('/api/taches/{ident}').then(r => r.json())")
        if t.get("statut") in ("fait", "terminee"):
            break
        time.sleep(0.3)
    assert t.get("statut") in ("fait", "terminee"), t
    page.screenshot(path=str(captures / "premiers-pas-3-tache.png"))
    etat = page.evaluate("fetch('/api/accueil/premiers-pas').then(r => r.json())")
    assert etat == {"propose": False, "etat": "fait"}
    assert not page.erreurs, page.erreurs


def test_modele_pre_remplit_nouvelle_tache(page, serveur, captures):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(page.url_serveur + "/")
    avant = fichiers(serveur.vault)
    page.wait_for_selector(".ligne")  # interface prête (dictionnaire chargé, boutons branchés)
    page.click("#btn-nouvelle")
    page.wait_for_selector('[data-id="modeles"]')
    page.click('[data-id="modele-creer-un-petit-site"]')
    expect(page.locator("input[name=titre]")).to_have_value("Créer un petit site")
    assert "[à compléter" in page.locator("[name=description]").input_value()
    expect(page.locator('[data-id="modele-creer-un-petit-site"]')).to_have_class("modele choisi")
    page.screenshot(path=str(captures / "modeles-nouvelle-tache.png"))
    assert fichiers(serveur.vault) == avant  # un modèle ne crée rien : la création reste le geste de l'utilisateur
    assert not page.erreurs, page.erreurs
