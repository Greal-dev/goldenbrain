# Devenir testeur

[English](BETA.md) · [Français](BETA.fr.md) · [Deutsch](BETA.de.md) · [Español](BETA.es.md)

Les versions bêta arrivent sur la branche `beta` avant `main`. Les testeurs attrapent ce qui échappe aux tests automatiques : un vrai vault, un vrai harnais d'agent, une vraie machine.

## Rejoindre
1. Installation par git (l'installation habituelle) : ouvrez *Réglages → Installation et version → Mise à jour*, mettez **Canal** sur *Bêta*.
2. Cliquez **Mettre à jour** sur le bandeau : GoldenBrain passe sur la branche `beta` et redémarre. Une modification locale du code bloque la bascule ; rien n'est écrasé. Si la branche `beta` n'existe pas encore, GoldenBrain le dit et le canal repasse sur *Stable* ; rien n'est modifié.
3. Pour revenir, choisissez *Stable* : la bascule se fait à la mise à jour suivante.

Une bascule ne touche jamais votre vault : seul le code de l'application change.

## Scénarios à jouer
Jouez ceux que vous pouvez, sur un vault d'essai ou sur le vôtre (sauvegardé d'abord).
1. **Installer et lancer** sur une machine propre ; l'accueil s'ouvre.
2. **Créer une tâche**, lui donner un conteneur, ouvrir sa fiche.
3. **Faire tourner un agent** avec votre harnais habituel ; la fiche revient remplie.
4. **Valider** une tâche terminée ; elle quitte la liste des tâches ouvertes.
5. **Mettre à jour** : passer du stable au bêta et revenir ; le serveur redémarre à chaque fois.
6. **Notes** : ouvrir le second cerveau, suivre un lien, regarder le graphe.
7. **Signaler** : *Réglages → Signaler un problème* ouvre un formulaire pré-rempli.

## Remonter un résultat
- **Quelque chose cloche** : formulaire *Bug report* (le bouton de l'application remplit la version, avec le canal, et le système). Dites quel scénario, ce que vous avez vu, ce que vous attendiez.
- **Tout va bien** : un court message dans les Discussions, catégorie *Beta*, avec la version essayée.
- Ne collez jamais de donnée personnelle : noms, chemins de votre poste, extraits du vault, jetons.
