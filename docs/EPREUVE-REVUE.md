# Épreuve du réel — revue planifiée (2026-11-14)

Commande : `python scripts/epreuve_revue.py <dépôt> <dossier-temporaire>` (serveur réel sur port libre, vault temporaire, claude modèle haiku ; jamais le vrai vault).

## Ce qui a tourné
- Rythme `quotidien`, heure = maintenant + 2 min, dernière revue = maintenant : rien avant l'échéance.
- Déclenchement à 19:41:55 pour une échéance à 19:41 (pas de vérification : 60 s). Tâche permanente créée, tour réel de 4 min 40.
- Résultat enregistré : fiche de la tâche renseignée, proposition déposée (doublon repéré entre deux tâches jumelles), `etat/jardinage.json` à jour (`tache`, `derniere`), pas de seconde revue.

## Ce qui a cassé
- La tâche permanente n'était mémorisée qu'après la soumission : une soumission en échec recréait une tâche de revue à chaque vérification (une par minute). Corrigé (`jardinage.py`), test `test_echec_de_soumission_ne_cree_pas_une_tache_par_minute`.

## Constats sans correction
- Le script d'épreuve laisse un processus claude orphelin si on tue le serveur en plein tour (le produit, lui, arrête l'arbre de processus) : propre au script.
- La revue tourne sur le modèle par défaut du harnais : aucun réglage de modèle pour le jardinage. Fonctionnalité éventuelle, hors périmètre.
