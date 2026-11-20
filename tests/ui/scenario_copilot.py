"""Scénario du sélecteur de moteur : GitHub Copilot CLI est proposé, grisé avec son motif tant que
`copilot` n'est pas installé (INV-MOTEUR-1) ; l'API et la liste affichée disent la même chose."""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet


def test_selecteur_de_moteur_propose_copilot(page, serveur):
    projet(serveur, "C1-Copilot", {"cop-tache": ("Tâche copilot", "")})
    charger(page)
    ligne(page, "Tâche copilot").click()
    page.wait_for_selector(".moteur select[aria-label='Assistant IA']")
    options = page.locator(".moteur select[aria-label='Assistant IA'] option")
    textes = options.all_inner_texts()
    copilot = next(t for t in textes if t.startswith("copilot"))
    api = next(x for x in page.request.get(serveur.url + "/api/harnais").json() if x["nom"] == "copilot")
    if api["disponible"]:
        assert copilot == "copilot"
    else:
        assert copilot.startswith("copilot — indisponible : ") and api["motif"] in copilot
        assert options.filter(has_text="copilot").first.is_disabled()
    assert not page.erreurs, page.erreurs
