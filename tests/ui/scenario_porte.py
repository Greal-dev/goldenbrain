"""Scénario de la porte elle-même : un serveur qui journalise abondamment reste joignable.

Régression du 15/11 : la sortie d'erreur du serveur d'essai partait dans un tuyau que personne ne vidait ;
au-delà de 4 Ko (une seule trace d'exception en fait ~10), l'écriture suivante bloquait la boucle du
serveur et tous les scénarios suivants expiraient sur `page.goto`. Ici, le tour factice « [bavard] »
écrit 64 Ko sur la sortie d'erreur ; le tour doit aboutir et l'interface se recharger.
"""

from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from aides_arbre import charger, ligne, projet


def test_serveur_reste_joignable_apres_un_journal_abondant(page, serveur):
    projet(serveur, "C1-PorteJournal", {"pj-un": ("Un PJ", "")})
    charger(page)
    ligne(page, "Un PJ").click()
    page.fill(".composer textarea", "[bavard] journalise")
    page.press(".composer textarea", "Control+Enter")
    page.wait_for_selector("text=en bonne voie", timeout=10000)  # la boucle du serveur n'a pas été bloquée
    page.goto(page.url_serveur + "/", timeout=10000)
    page.wait_for_selector(".ligne", timeout=10000)
    assert not page.erreurs, page.erreurs
