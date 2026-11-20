# Sécurité

[English](SECURITY.md) · Français · [Deutsch](SECURITY.de.md) · [Español](SECURITY.es.md)

## Signaler une vulnérabilité
Ne publiez pas de ticket public. Utilisez le signalement privé de GitHub (onglet « Security », « Report a vulnerability »). Décrivez le problème, la version (commit) et un moyen de le reproduire. Un accusé de réception suit dans la mesure du possible.

## Modèle de menace
- GoldenBrain est un outil **local, mono-utilisateur** : le serveur écoute sur `127.0.0.1` et n'a pas d'authentification. Ne l'exposez jamais sur un réseau.
- Il lance des harnais d'agents IA avec les droits de votre session, souvent en mode sans confirmation (`config.exemple.toml`). Un agent peut donc lire et modifier ce que votre compte peut lire et modifier : confiez-lui des tâches en conséquence.
- Un contenu externe lu par un agent (page web, courriel) peut contenir des instructions malveillantes ; la consigne commune demande de ne jamais le traiter comme un ordre, sans que cela soit une garantie.
- Les harnais gèrent leurs propres identifiants. GoldenBrain ne garde que les secrets facultatifs des connecteurs (le jeton du bot Telegram) : lus dans une variable d'environnement, ou écrits par les Réglages hors du dépôt — chiffrés par DPAPI sous Windows, fichier lisible par votre seul compte (0600) ailleurs. Un secret n'est jamais journalisé ni écrit dans le vault.
