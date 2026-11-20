"""Captures d'écran du README sur un vault de démonstration fictif (INV-PUB-1 : aucune donnée réelle).

Rôle : serveur dédié, vault de démonstration (deux projets, une maison, quelques notes liées), puis deux
captures : l'arbre en cascade, une tâche (conversation et notes).
Frontières : écrit les images dans `GB_CAPTURES` (dossier, posé par `scripts/captures.py`), sinon dans le
dossier temporaire du test ; ne touche jamais le dépôt lors de la porte d'interface.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect

import univers
from aides_arbre import deplier_tout
from conftest import demarrer

TACHES = {
    "Projets/C1-Site-vitrine": ("Site vitrine de l'atelier", "C1-Pro", {
        "accueil": ("Refondre la page d'accueil", "en-cours", "priorite: haute\nharnais: faux\n"),
        "contact": ("Corriger le formulaire de contact", "fait", "harnais: faux\n"),
        "mentions": ("Rédiger les mentions légales", "a-faire", "echeance: 2026-12-04\n"),
        "images": ("Optimiser les images", "a-faire", 'priorite: basse\nprerequis: ["[[accueil]]"]\n'),
    }),
    "Projets/C1-Facturation": ("Outil de facturation", "C1-Pro", {
        "csv": ("Exporter les factures en CSV", "en-cours", "harnais: faux\n"),
        "tests": ("Couvrir l'export par des tests", "a-faire", "priorite: haute\n"),
    }),
    "Projets/C2-Maison": ("Maison", "C2-Perso", {
        "devis": ("Comparer les devis de la cuisine", "a-faire", "executant: humain\necheance: 2026-11-28\n"),
        "chaudiere": ("Planifier l'entretien de la chaudière", "a-faire", "priorite: moyenne\n"),
    }),
}
NOTES = {
    "Ressources/accessibilite.md": ("Accessibilité web", "Contrastes, navigation au clavier. Voir [[typographie]]."),
    "Ressources/typographie.md": ("Typographie", "Deux familles au plus. Utile pour [[Projets/C1-Site-vitrine/taches/accueil|l'accueil]]."),
    "Ressources/devis-cuisine.md": ("Devis de la cuisine", "Trois artisans ; [[Projets/C2-Maison/taches/devis|comparaison]]."),
    "Ressources/format-csv.md": ("Format CSV des factures", "Séparateur point-virgule. Voir [[Projets/C1-Facturation/taches/csv|l'export]]."),
}


def _vault_demo(vault: Path) -> None:
    for d in ("Projets", "_meta"):  # l'univers des autres scénarios n'a rien à faire sur une capture
        shutil.rmtree(vault / d, ignore_errors=True)
    for dossier, (nom, casquette, taches) in TACHES.items():
        univers.ecrire(vault, f"{dossier}/contexte.md", f"---\ntype: contexte\ncasquette: {casquette}\nnom: {nom}\n---\n")
        for f, (titre, statut, extra) in taches.items():
            univers.ecrire(vault, f"{dossier}/taches/{f}.md", univers.tache(titre, statut, extra))
    for rel, (titre, corps) in NOTES.items():
        univers.ecrire(vault, rel, f"---\ntype: ressource\ntags: [demo]\n---\n\n# {titre}\n\n{corps}\n")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    construire = univers.construire

    def construire_demo(dossier, port, telegram_api=""):
        # Vault écrit AVANT le démarrage : les index (tâches, notes, graphe) naissent sur la démonstration.
        config = construire(dossier, port, telegram_api)
        _vault_demo(dossier / "vault")
        # Le harnais factice ne lance aucune commande ; en nommer une qui existe évite « indisponible » à l'écran.
        exe = Path(sys.executable).as_posix()
        config.write_text(config.read_text(encoding="utf-8").replace(
            "[harnais.faux]\n", f'[harnais.faux]\ncommande = "{exe}"\n'), encoding="utf-8")
        return config

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(univers, "construire", construire_demo)
        yield from demarrer(tmp_path_factory.mktemp("ui-captures"))


def _sortie(tmp_path) -> Path:
    d = Path(os.environ.get("GB_CAPTURES") or tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _page(navigateur, srv):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768})
    page = ctx.new_page()
    page.erreurs = []
    page.on("pageerror", lambda e: page.erreurs.append(str(e)))
    return ctx, page


def _cliche(page, chemin: Path) -> None:
    page.mouse.move(1365, 767)  # ni survol ni focus : boutons de ligne et infobulles hors de l'image
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(300)
    page.screenshot(path=str(chemin))


def test_captures_du_readme(navigateur, demo, tmp_path):
    sortie = _sortie(tmp_path)
    ctx, page = _page(navigateur, demo)
    try:
        page.goto(demo.url + "/")
        page.wait_for_selector("#arbre .ligne >> text=Site vitrine de l'atelier", timeout=20000)
        deplier_tout(page)
        expect(page.locator(".casc-corps .c-t", has_text="Refondre la page d'accueil")).to_be_visible()
        _cliche(page, sortie / "arbre.png")

        page.locator("#arbre .ligne .titre", has_text="Refondre la page d'accueil").first.click()
        expect(page.locator(".d-titre")).to_have_text("Refondre la page d'accueil")
        page.fill(".composer textarea", "Propose une structure pour l'en-tête et le pied de page.")
        page.press(".composer textarea", "Control+Enter")
        expect(page.locator(".msg.agent.final")).to_be_visible(timeout=20000)
        ta = page.locator(".notes-ajout textarea")
        ta.fill("Garder le logo actuel ; couleurs de la charte de 2025.")
        ta.press("Control+Enter")
        expect(page.locator(".note-t")).to_contain_text("Garder le logo actuel")
        _cliche(page, sortie / "tache.png")

        assert not page.erreurs, page.erreurs
    finally:
        ctx.close()
