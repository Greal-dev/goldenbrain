"""Scénario de la validation automatique par périmètre (INV-VALID-2) : réglage « automatique » d'un projet
depuis sa note de contexte (accord tracé), section « Clos automatiquement » de Décisions et « Rouvrir »."""

import json
import re

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

PROJET = "Projets/C1-ValidUI"


def _monde(serveur):
    univers.ecrire(serveur.vault, f"{PROJET}/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: ValidUI\n---\n")
    univers.ecrire(serveur.vault, f"{PROJET}/taches/va-close.md",
                   univers.tache("Close Auto ValidUI", statut="cloture", extra="session: s-va\n"))
    # Le journal de la validation automatique vit à côté de la configuration du serveur d'essai.
    etat = serveur.vault.parent / "etat"
    etat.mkdir(exist_ok=True)
    entree = {"tache": "va-close", "titre": "Close Auto ValidUI", "issue": "cloture", "motif": "",
              "date": "2099-01-01T00:00:00", "controle": {"reference": "gb/x@abc1234"},
              "revue": {"harnais": "autre", "modele": "m", "verdict": "ok", "points": []},
              "auteur": {"harnais": "faux", "modele": ""}}
    (etat / "validation_auto.json").write_text(json.dumps({"compteur": 1, "entrees": [entree]}), "utf-8")


def test_reglage_du_projet_puis_rouvrir_une_cloture_automatique(page, serveur):
    _monde(serveur)

    # Réglage depuis la note de contexte : la confirmation vaut accord, tracé dans le frontmatter.
    page.on("dialog", lambda d: d.accept())
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.click("#onglet-notes")
    for dossier in ("Projets", "C1-ValidUI"):
        page.click(f".ligne.t-dossier >> text={dossier}")
    page.click(".ligne.t-note >> text=contexte")
    page.wait_for_selector(".vue-note .d-titre")
    page.select_option("[data-validation]", "automatique")
    expect(page.locator("label.n-validation")).to_have_attribute("title", re.compile("posé depuis l.interface"))
    texte = (serveur.vault / PROJET / "contexte.md").read_text("utf-8")
    assert "validation: automatique" in texte and "validation_accord:" in texte

    # Décisions : la clôture automatique est listée, « Rouvrir » remet la tâche à valider.
    page.goto(page.url_serveur + "/#decisions")
    section = page.locator(".dc-clos-auto")
    expect(section).to_contain_text("Clos automatiquement")
    ligne = section.locator("li.dc-clos[data-tache='va-close']")
    expect(ligne).to_contain_text("gb/x@abc1234")
    ligne.locator("[data-rouvrir]").click()
    for _ in range(100):
        if page.request.get(serveur.url + "/api/taches/va-close").json()["statut"] == "fait":
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("« Rouvrir » n'a pas remis la tâche à valider")
    expect(page.locator("li.dc-clos[data-tache='va-close']")).to_have_count(0)
    assert not page.erreurs, page.erreurs
