# Backlog

## Prochaines US (ordre proposé)
1. **Gabarit de tâche conforme à l'ontologie** : sections « Pourquoi moi » et « Critère de délégation », clé `tags`, `projet: transverse` pour le conteneur d'arrivée — le tout paramétrable.
2. **Second harnais (Codex)** : un adaptateur + une entrée de registre ; choix du harnais par tâche dans l'interface.
3. **Rattacher une session existante** depuis l'interface (les sessions Claude agents déjà ouvertes).
4. **Le temps** : échéance et priorité visibles et triables dans l'arbre.
5. **Routeur Telegram** : message adressé à la bonne tâche ; scan classé et transformé en tâche.
6. **Relevés de mails** (deux par jour) et **récurrences** (tâche permanente réveillée à échéance).
7. **Inscrire dans l'ontologie du vault** les clés `harnais`, `session`, `alimente`, `voir_aussi`.
8. **Propagation plus fine** : ne prévenir les tâches alimentées que si la fiche de la source a réellement changé (économie de crédits).

## Console GoldenBrain : fonctions natives à reprendre (après la version minimale du 15/11)
Faisabilité par harnais, vue depuis GoldenBrain, qui lance chaque tour en mode non interactif (`claude -p`, `codex exec --json`, `opencode run`, `agy`).

| Fonction | Claude Code | Codex | OpenCode | Antigravity (agy) |
|---|---|---|---|---|
| Interruption par Échap (tour coupé, conversation gardée) | oui : Échap → `POST /arret`, le tour suivant reprend la session (`--resume`) | oui, même voie (`exec resume`) | oui, même voie (`-s`) | oui, même voie (`--conversation`) |
| Aperçu des modifications (diff des fichiers touchés) | partiel : outils `Edit`/`Write` du flux JSON portent l'ancien et le nouveau texte | partiel : événements `file_change` du flux, diff à recalculer par `git diff` | partiel : événements d'outil ; `git diff` du dossier de travail | inconnu : flux pauvre ; `git diff` seulement |
| Changement de modèle | oui : `POST /moteur` existe déjà (commande `/modele <nom>`) | oui (`modèle@effort`) | oui | oui (catalogue agy) |
| Compactage de la conversation | oui : envoyer `/compact` en message (commande native reconnue par `claude -p`) [hypothèse à vérifier] | non natif en `exec` : session neuve + résumé injecté par GoldenBrain | inconnu | non |
| Mode plan (réfléchir sans modifier) | oui : `--permission-mode plan` par tour, à exposer comme option d'envoi | partiel : `--sandbox read-only` | partiel : agent « plan » d'OpenCode (`--agent plan`) | inconnu |
| Collage d'image | oui : image enregistrée dans un fichier, chemin cité dans le message (Claude lit l'image) | oui : `codex exec -i <image>` | partiel : chemin cité, selon le modèle | inconnu |

Prérequis commun : saisie ligne à ligne remplacée par un éditeur de ligne (stdlib `msvcrt` sous Windows) pour Échap, le multi-ligne et le collage.

## Reporté de la revue adversariale du 12/11 (non bloquant)
- Jeton d'agent par tour : aujourd'hui INV-EXEC-5 et INV-MSG-1 ne sont tenus que par la commande `orch` ; un agent qui appelle l'API directement peut les contourner (il a déjà les pleins droits : contournement, pas escalade). Compteur de sauts côté serveur.
- Tour muet : délai d'inactivité paramétrable (aucun événement depuis N minutes).
- Dérivation « avec fil » : origine gardée en mémoire seulement (perdue au redémarrage) ; la persister.
- Clé de frontmatter dupliquée ou citée ; commentaire de fin de ligne perdu sur une clé gérée.
- Contrôle de date de modification avant écriture (sauvegarde Obsidian concurrente).
- Courses autour de l'arrêt (arrêt avant le lancement du processus ; message soumis pendant l'arrêt).
- Bornes sur les abonnés SSE et les files ; versions des dépendances épinglées.
- Titre et fil d'Ariane du vault injectés dans la consigne système : les délimiter et les plafonner.
- Tests manquants : saturation de la simultanéité, `duree_max_s`, sauts de bout en bout, reconnexion SSE.
