# Épreuve du réel — validation confiée à un persona (14/11/2026)

Montage : `python scripts/epreuve_persona.py <dépôt> <dossier-temporaire>` — serveur réel (port libre), vault temporaire,
harnais `claude` modèle `haiku`, `[validation] mode = "persona"`, persona `valideur` (haiku) dont le mandat exige une ligne
« Source: » que la consigne de la tâche ne mentionne pas. Rien n'est envoyé ni publié ; le vrai vault n'est pas touché.

## Boucle nominale (boucles_max = 2) — observée
| t (s) | statut | renvois | avis |
|---|---|---|---|
| 0 | en-cours | 0 | — |
| 36 | fait | 0 | valideur en cours |
| 61 | en-cours | 1 | valideur **reserves** (aucune ligne « Source: ») → renvoi `[Validation de Valideur : réserves]` |
| 91 | fait | 1 | valideur en cours (même session reprise) |
| 115 | **cloture** | 0 | valideur **ok** ; compteur remis à zéro |

Vérifié : session du persona mémorisée et reprise (`etat/revues.json`) ; deux journaux `<tache>@valideur-HHMMSS.jsonl` ;
message de renvoi conforme au contrat ; frontmatter de la tâche intact ; `etat/tours.json` vide à la fin.

## Variante limite (boucles_max = 1, critère insatisfaisable)
Réserve → renvoi → l'agent constate la contradiction et rend la main (`retour-humain`) ; compteur conservé (1).
Le plafond `boucles_max` lui-même n'est pas atteint par cette voie (l'agent s'est arrêté avant) : il reste couvert par
`tests/test_revues.py::test_revue_avec_reserves_renvoie_puis_rend_la_main_a_boucles_max`.

## Défauts révélés
Aucun dans le code de l'équipe et de la validation : pas de correction, donc pas de test ajouté. Les seuls incidents
(403 `X-Orchestrateur` absent, conteneur inconnu car identifié par son chemin `Projets/<nom>`) venaient du script d'essai,
le code se comportant comme le contrat l'exige (INV-API-1, `Vault.conteneur`).
