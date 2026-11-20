"""Accueil d'un nouvel arrivant : parcours en 3 écrans, rien d'écrit avant la validation, relance sans écrasement."""

import json
import os
import shutil
import time

import pytest


def historique(home, session, dossier, messages):
    d = home / ".claude" / "projects" / "x"
    d.mkdir(parents=True, exist_ok=True)
    lignes = []
    for m in messages:
        lignes.append({"type": "user", "cwd": str(dossier), "timestamp": "2026-11-03T10:00:00Z", "message": {"role": "user", "content": m}})
        lignes.append({"type": "assistant", "timestamp": "2026-11-03T10:01:00Z", "message": {"role": "assistant"}})
    f = d / f"{session}.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    vieux = time.time() - 3 * 86400
    os.utime(f, (vieux, vieux))


def fichiers(racine):
    return {p.relative_to(racine).as_posix() for p in racine.rglob("*") if p.is_file()}


@pytest.fixture(autouse=True)
def rendre_le_serveur(serveur):
    """Le serveur est partagé : le scénario retire ce qu'il a écrit pour ne rien laisser aux autres."""
    avant = fichiers(serveur.vault)
    yield
    for f in fichiers(serveur.vault) - avant:
        (serveur.vault / f).unlink()
    for d in sorted((p for p in serveur.vault.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    shutil.rmtree(serveur.home / ".claude", ignore_errors=True)
    serveur_etat = serveur.dossier / "donnees" / "etat" / "accueil.json"
    serveur_etat.unlink(missing_ok=True)


def test_parcours_en_trois_ecrans(page, serveur):
    for nom in ("zeta", "omega"):
        (serveur.dossier / "travaux" / nom / ".git").mkdir(parents=True, exist_ok=True)
    historique(serveur.home, "sess-zeta-01", serveur.dossier / "travaux" / "zeta", ["Monter le site zeta", "Ajoute une page"])
    historique(serveur.home, "sess-omega-01", serveur.dossier / "travaux" / "omega", ["Écrire le moteur omega", "Et des tests"])
    avant = fichiers(serveur.vault)
    page.goto(page.url_serveur + "/#reglages/accueil")
    page.click('[data-id="relancer-accueil"]')
    page.wait_for_selector('[data-id="accueil"]')
    # Écran 1 : chaque source est désactivée au départ ; rien n'est proposé sans case cochée.
    assert page.locator('[data-id="actif-conversations"]').is_checked() is False
    page.click('[data-id="actif-conversations"]')
    page.click('[data-id="actif-questions"]')
    page.fill('[data-id="q-roles"]', "Pro, Famille")
    page.click('[data-id="accueil-proposer"]')
    # Écran 2 : le plan nomme la source de chaque élément ; renommer et glisser corrigent le plan.
    page.wait_for_selector('[data-id="accueil-plan"]')
    assert page.locator('[data-id="accueil-confidentialite"]').inner_text().strip()
    assert page.locator(".ac-projet", has_text="").count() >= 2
    assert page.locator(".ac-src", has_text="conversations").count() >= 2
    page.locator('[data-id^="nom-p"]').first.fill("Projet renommé")
    page.locator('[data-id^="nom-p"]').first.dispatch_event("change")
    tache = page.locator(".ac-tache").first
    projet = page.locator(".ac-projet").nth(1)
    tache.drag_to(projet)
    assert fichiers(serveur.vault) == avant  # aucune écriture avant la validation
    page.click('[data-id="accueil-suite"]')
    # Écran 3 : récapitulatif, puis un seul geste.
    page.wait_for_selector('[data-id="accueil-recap"]')
    assert fichiers(serveur.vault) == avant
    page.click('[data-id="accueil-valider"]')
    try:
        page.wait_for_selector('[data-id="accueil-bilan"]', timeout=5000)
    except Exception:
        raise AssertionError(page.locator('body').inner_text()[:1500])
    assert "créés" in page.locator('[data-id="accueil-bilan"]').inner_text()
    ecrits = fichiers(serveur.vault) - avant
    assert any(f.endswith("contexte.md") for f in ecrits) and any("/taches/" in f for f in ecrits)
    assert not any(f in ecrits for f in avant)
    page.click('[data-id="accueil-fermer"]')
    # Relance : ce qui existe est reconnu, rien n'est récrit.
    apres = {f: (serveur.vault / f).read_bytes() for f in fichiers(serveur.vault)}
    page.click('[data-id="relancer-accueil"]')
    page.click('[data-id="actif-conversations"]')
    page.click('[data-id="accueil-proposer"]')
    page.wait_for_selector('[data-id="accueil-plan"]')
    assert page.locator(".ac-tache").count() == 0
    assert {f: (serveur.vault / f).read_bytes() for f in fichiers(serveur.vault)} == apres
    assert not page.erreurs, page.erreurs
