"""Scénario de l'encart « Où en est-on » : fait, attendu de vous, prochaine étape en tête de tâche."""

import pytest
import univers
from aides_arbre import _ECRITS, nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

BLOC = ("\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : {fait}\n- **Résultat** : {res}\n"
        "- **Essai** : lancer\n- **Situation** : \n- **Reste à faire** : \n- **Prochain pas** : {pas}\n"
        "<!-- orchestrateur:fin -->\n")


def _ouvrir(page, serveur, nom):
    page.goto(f"{serveur.url}/#t={nom}")
    page.wait_for_selector(".d-une")


@pytest.fixture(autouse=True)
def _ranger(serveur):
    _ECRITS.append(serveur.vault / "Projets" / "C1-Encart")  # retiré en sortie (nettoyer_vault) : rien ne fuit vers les filtres d'autres scénarios
    univers.ecrire(serveur.vault, "Projets/C1-Encart/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: Encart\n---\n")


def test_encart_trois_lignes_avec_question_attendue(page, serveur):
    texte = univers.tache("Encart Trois", statut="retour-humain", extra='commentaire: "Quelle option : A ou B ?"\n')
    univers.ecrire(serveur.vault, "Projets/C1-Encart/taches/en-trois.md",
                   texte + BLOC.format(fait="x", res="La page est livrée. Le reste suit.", pas="Brancher le paiement. Puis tester."))
    _ouvrir(page, serveur, "en-trois")
    encart = page.locator("[data-id=encart-etat]")
    expect(encart.locator("[data-ligne=fait] .encart-txt")).to_have_text("La page est livrée.")
    expect(encart.locator("[data-ligne=attendu] .encart-txt")).to_contain_text("Quelle option : A ou B ?")
    expect(encart.locator("[data-ligne=prochaine] .encart-txt")).to_have_text("Brancher le paiement.")
    assert encart.bounding_box()["height"] <= 70
    assert not page.erreurs


def test_encart_absent_sans_fiche(page, serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Encart/taches/en-muette.md", univers.tache("Encart Muette", statut="en-cours"))
    _ouvrir(page, serveur, "en-muette")
    expect(page.locator(".d-une")).to_be_visible()
    expect(page.locator("[data-id=encart-etat]")).to_have_count(0)
    assert not page.erreurs


def test_encart_texte_long_tronque_titre_complet(page, serveur):
    long = "mot " * 80
    univers.ecrire(serveur.vault, "Projets/C1-Encart/taches/en-long.md",
                   univers.tache("Encart Long", statut="en-cours") + BLOC.format(fait="x", res=long.strip(), pas=""))
    _ouvrir(page, serveur, "en-long")
    ligne = page.locator("[data-ligne=fait]")
    txt = ligne.locator(".encart-txt").inner_text()
    assert len(txt) <= 160 and txt.endswith("…")
    expect(ligne).to_have_attribute("title", long.strip())
    assert not page.erreurs
