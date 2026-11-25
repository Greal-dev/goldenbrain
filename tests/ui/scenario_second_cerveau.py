"""Accueil sur un vault vide (INV-ACCUEIL-5) : rôles et projets saisis, « Classement de départ » proposé,
rien d'écrit avant la validation, puis dossiers du second cerveau, « Lisez-moi » et fiches `contexte.md`.
Serveur dédié : son vault est vidé avant le scénario, sans toucher le serveur partagé des autres scénarios.
Captures dans `GB_CAPTURES` si posé, sinon dans le dossier temporaire du test."""

import os
import shutil
from pathlib import Path

import pytest

from conftest import demarrer


@pytest.fixture(scope="module")
def poste(tmp_path_factory):
    yield from demarrer(tmp_path_factory.mktemp("ui-second-cerveau"))


def test_vault_vide_recoit_un_classement_de_depart(navigateur, poste, tmp_path):
    for p in list(poste.vault.iterdir()):
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    captures = Path(os.environ.get("GB_CAPTURES") or tmp_path)
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768})
    erreurs = []
    try:
        page = ctx.new_page()
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        # Vault vide : les premiers pas se proposeraient avant l'accueil ; ce scénario porte sur l'accueil seul.
        page.request.post(poste.url + "/api/accueil/premiers-pas/fait", headers={"X-Orchestrateur": "1"}, data={})
        page.goto(poste.url + "/#reglages/accueil")
        # Vault vide : l'accueil se propose seul, juste après le premier affichage ; sinon on le relance depuis les Réglages.
        try:
            page.wait_for_selector('[data-id="accueil-vide"]', timeout=4000)
        except Exception:
            page.click('[data-id="relancer-accueil"]')
            page.wait_for_selector('[data-id="accueil-vide"]')
        assert page.locator('[data-id="actif-questions"]').is_checked()
        assert page.locator('[data-id="accueil-guide"]').get_attribute("href").endswith(
            "#guide=organiser-votre-second-cerveau")
        page.fill('[data-id="q-roles"]', "Travail, Famille")
        page.fill('[data-id="q-projets"]', "Déménagement, Site du cabinet")
        page.screenshot(path=str(captures / "second-cerveau-1-questions.png"))
        page.click('[data-id="accueil-proposer"]')
        page.wait_for_selector('[data-id="accueil-depart"]')
        assert page.locator('[data-id="garde-squelette"]').is_checked()
        assert "Lisez-moi" in page.locator('[data-id="accueil-depart"]').inner_text()
        page.screenshot(path=str(captures / "second-cerveau-2-relire.png"), full_page=True)
        assert not any(poste.vault.rglob("*.md"))  # rien d'écrit avant la validation
        page.click('[data-id="accueil-suite"]')
        page.wait_for_selector('[data-id="accueil-recap"]')
        page.click('[data-id="accueil-valider"]')
        page.wait_for_selector('[data-id="accueil-bilan"]')
        page.screenshot(path=str(captures / "second-cerveau-3-bilan.png"))
        for d in ("Inbox", "Ressources", "Archives"):
            assert (poste.vault / d).is_dir()
        assert "Rôles → projets → tâches" in (poste.vault / "Lisez-moi.md").read_text(encoding="utf-8")
        contextes = [p.read_text(encoding="utf-8") for p in poste.vault.rglob("contexte.md")]
        assert any("## Consignes pour l'IA" in c for c in contextes)
        assert any("Déménagement" in c for c in contextes)
    finally:
        ctx.close()
    assert not erreurs, erreurs
