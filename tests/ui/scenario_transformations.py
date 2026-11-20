"""Scénarios de promotion (tâche → projet) et de réduction (projet → tâche), contre le vrai serveur.

Le conseil est désactivé dans la config de test : l'avis revient « indisponible » et ne bloque jamais.
Le découpage est décoché à la promotion (aucun tour d'agent) ; la réduction lance, elle, le tour de
contraction du harnais factice.
"""

import subprocess
import sys
import time
import urllib.request

import pytest

import univers
from conftest import SERVEUR, port_libre


@pytest.fixture(scope="module")
def serveur(tmp_path_factory):
    """Serveur propre à ce fichier : la config de test ne couvre qu'un niveau de `taches/`, or un projet
    promu naît sous son conteneur (Projets/<X>/<Nouveau>/taches). On élargit donc les motifs ici,
    sans toucher au socle."""
    dossier = tmp_path_factory.mktemp("ui-transfo")
    port = port_libre()
    config = univers.construire(dossier, port)
    texte = config.read_text(encoding="utf-8")
    config.write_text(texte.replace('taches = ["Projets/*/taches/*.md",',
                                    'taches = ["Projets/*/taches/*.md", "Projets/*/*/taches/*.md",'),
                      encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(SERVEUR), str(config)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail(f"le serveur s'est arrêté : {proc.stderr.read().decode('utf-8', 'replace')}")
            try:
                urllib.request.urlopen(f"{url}/api/arbre", timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("le serveur ne répond pas")
        yield type("Serveur", (), {"url": url, "vault": dossier / "vault"})
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc.stderr.close()


def _attendre_index(page, dossier, total):
    """L'index des notes se rafraîchit en arrière-plan (ttl) : attendre qu'il voie les fichiers écrits."""
    def compte():
        d = page.request.get(f"{page.url_serveur}/api/vault/dossier?chemin={dossier}").json()
        return len(d["notes"]) + sum(x["notes"] for x in d["dossiers"])
    for _ in range(60):
        if compte() == total:
            return
        page.wait_for_timeout(500)
    raise AssertionError(f"l'index des notes ne voit pas {total} notes sous {dossier}")


def _ouvrir_arbre(page):
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")


def _deplier_tout(page):
    fermes = page.locator(".ligne .chev:not(.ouvert):not(.vide)")
    for _ in range(20):  # l'arbre se redessine à chaque dépliage : relire le premier chevron fermé
        if not fermes.count():
            break
        fermes.first.click()


def test_promotion_tache_en_projet(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Alpha/taches/promo-ui.md", univers.tache("Promo UI"))
    _ouvrir_arbre(page)
    _deplier_tout(page)
    page.click(".ligne.t-tache >> text=Promo UI")
    page.click("button:has-text('Promouvoir en projet')")
    # Avis de l'agent (conseil désactivé → indisponible), puis le formulaire.
    dlg = page.locator("dialog[aria-label='Promouvoir en projet']")
    dlg.wait_for(timeout=10000)
    assert dlg.locator("input[name=nom]").input_value() == "Promo UI"
    dlg.locator("input[name=nom]").fill("Projet issu de promo")
    dlg.locator("input[name=decouper]").uncheck()
    dlg.locator("button[type=submit]").click()
    page.wait_for_selector("#info-geste >> text=Projet issu de promo est maintenant un projet")
    # Le projet existe sur le disque, la tâche en est le premier ticket ; l'arbre le montre.
    contextes = list(serveur.vault.glob("Projets/**/Projet issu de promo/contexte.md")) \
        or list(serveur.vault.glob("Projets/**/*romo*/contexte.md"))
    assert contextes, "le dossier du nouveau projet est introuvable"
    page.wait_for_selector(".ligne.t-conteneur >> text=Projet issu de promo")
    assert page.locator(".ligne.t-tache >> text=Promo UI").count() == 1
    assert not page.erreurs, page.erreurs


def test_promotion_annulee_ne_change_rien(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Alpha/taches/promo-annulee.md", univers.tache("Promo annulée"))
    _ouvrir_arbre(page)
    _deplier_tout(page)
    page.click(".ligne.t-tache >> text=Promo annulée")
    page.click("button:has-text('Promouvoir en projet')")
    dlg = page.locator("dialog[aria-label='Promouvoir en projet']")
    dlg.wait_for(timeout=10000)
    dlg.locator("button[data-refus]").click()
    dlg.wait_for(state="detached")
    assert not list(serveur.vault.glob("Projets/**/Promo annulée/contexte.md"))
    assert (serveur.vault / "Projets/C1-Alpha/taches/promo-annulee.md").exists()
    assert not page.erreurs, page.erreurs


def test_reduction_projet_en_tache(page, serveur):
    base = "Projets/C1-Reduit"
    univers.ecrire(serveur.vault, f"{base}/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Reduit\n---\n")
    univers.ecrire(serveur.vault, f"{base}/taches/r1.md", univers.tache("Réduit un"))
    univers.ecrire(serveur.vault, f"{base}/taches/r2.md", univers.tache("Réduit deux", statut="fait"))
    univers.ecrire(serveur.vault, f"{base}/annexe.md", "---\ntype: ressource\n---\n\n# Annexe\n")
    _attendre_index(page, "Projets/C1-Reduit", 4)
    _ouvrir_arbre(page)
    page.click("#onglet-notes")
    for dossier in ("Projets", "C1-Reduit"):
        page.click(f".ligne.t-dossier >> text={dossier}")
    page.click(".ligne.t-note >> text=contexte")
    page.click("button:has-text('Réduire en tâche')")
    dlg = page.locator("dialog[aria-label^='Réduire']")
    dlg.wait_for(timeout=10000)
    # Le bilan annonce ce qui sera archivé : 1 ouverte, 1 fermée, 1 autre note.
    bilan = dlg.locator(".rappel-archive").inner_text()
    assert "1 tâche ouverte" in bilan and "1 fermée" in bilan and "1 autre note" in bilan, bilan
    dlg.locator("input[name=point_git]").uncheck()  # le vault de test n'est pas un dépôt git
    dlg.locator("button[type=submit]").click()
    page.wait_for_selector("#info-geste >> text=est maintenant une tâche", timeout=15000)
    assert not (serveur.vault / base).exists(), "le dossier du projet aurait dû être archivé"
    archives = list(serveur.vault.glob("Archives/C1-Reduit-ARCHIVE-*"))
    assert archives and (archives[0] / "annexe.md").exists()
    page.wait_for_selector(".d-titre")  # la nouvelle tâche s'ouvre
    assert not page.erreurs, page.erreurs


def test_reduction_refusee_sans_depot_git(page, serveur):
    base = "Projets/C1-Reduit-refus"
    univers.ecrire(serveur.vault, f"{base}/contexte.md",
                   "---\ntype: contexte\ncasquette: C1-Pro\nnom: Reduit refus\n---\n")
    univers.ecrire(serveur.vault, f"{base}/taches/rr1.md", univers.tache("Refus un"))
    _ouvrir_arbre(page)
    page.click("#onglet-notes")
    for dossier in ("Projets", "C1-Reduit-refus"):
        page.click(f".ligne.t-dossier >> text={dossier}")
    page.click(".ligne.t-note >> text=contexte")
    page.click("button:has-text('Réduire en tâche')")
    dlg = page.locator("dialog[aria-label^='Réduire']")
    dlg.wait_for(timeout=10000)
    dlg.locator("button[type=submit]").click()  # point de restauration git coché par défaut
    page.wait_for_selector("#banniere >> text=point de restauration impossible", timeout=10000)
    # Tout ou rien : le dossier du projet n'a pas bougé.
    assert (serveur.vault / base / "contexte.md").exists()
    assert not list(serveur.vault.glob("Archives/C1-Reduit-refus-ARCHIVE-*"))
