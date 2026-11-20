# Tests d'interface (Playwright)

Commande unique, hors de la porte rapide (`scripts/check.py` ne l'appelle pas) :

    python scripts/check_ui.py              # tous les scénarios
    python scripts/check_ui.py -k fumee     # arguments transmis à pytest

Elle lance le VRAI serveur (`tests/ui/serveur.py` → `orchestrateur.__main__`) sur un port libre, avec un
vault temporaire (`univers.py`) et le harnais factice « faux » (`harnais_factice.py`), puis supprime tout.
Le journal du serveur (sorties standard et d'erreur) va dans `serveur.log` du dossier temporaire de la session,
jamais dans un tuyau : non lu, un tuyau se remplit à 4 Ko et fige le serveur (`scenario_porte.py`).
Prérequis : Playwright et son Chromium déjà installés dans le Python embarqué (rien n'est installé).

## Écrire un scénario

1. Créer `tests/ui/scenario_<famille>.py` (le préfixe `scenario_` le distingue des tests de la porte rapide).
2. Une fonction `test_…(page)` : `page` est une page Playwright neuve (viewport 1366×768) ;
   `page.url_serveur` donne l'adresse ; `page.erreurs` collecte erreurs et avertissements console.
3. Besoin du disque (vault) : fixture `serveur` → `serveur.vault` ; ajouter des fichiers avec
   `univers.ecrire(serveur.vault, "Projets/…/taches/x.md", univers.tache("Titre"))` AVANT d'agir
   (le serveur est partagé par la session : donner à ses fichiers des noms propres au scénario).
4. Comportement de l'agent : le harnais factice rejoue un seul tour (texte, outil, fiche « en bonne voie ») ;
   mots-clés du message : « [lent N] », « [echec] », « [bavard] » (voir `harnais_factice.py`).
   Pour un autre tour, étendre `HarnaisFactice` (jamais un faux serveur) ; la conversation relue vient de `transcript`.
5. Attendre un état (`wait_for_selector`, `expect`), jamais `wait_for_timeout` ; finir par `assert not page.erreurs`.
6. L'arbre se redessine à chaque dépliage : relire le localisateur à chaque clic (voir `scenario_fumee.py`).

Modèle : `scenario_fumee.py`.
