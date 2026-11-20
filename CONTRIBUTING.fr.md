# Contribuer

[English](CONTRIBUTING.md) · Français · [Deutsch](CONTRIBUTING.de.md) · [Español](CONTRIBUTING.es.md)

Merci de votre intérêt. Une petite correction peut aller directement en demande de fusion ; pour tout changement plus important, ouvrez d'abord un ticket afin de convenir de l'approche. La [feuille de route](ROADMAP.fr.md) indique où l'aide est la plus bienvenue.

## Avant de commencer
Lire, dans cet ordre :
1. `CLAUDE.md` — le contrat de travail : commandes canoniques, règles, zones dangereuses.
2. `docs/ARCHITECTURE.md` — modules, contrats, et les invariants `INV-*` à ne jamais casser.
3. `docs/CODE_MAP.md` — chaque fichier, son rôle, les invariants qu'il porte et ses tests.

Le code, les identifiants, les libellés de l'interface et les documents de conception sont en français ; tickets et demandes de fusion peuvent être rédigés en anglais, français, allemand ou espagnol.

## Où contribuer
Les points d'extension privilégiés ajoutent une capacité sans toucher au cœur :
- **Adaptateur de harnais** — prendre en charge un nouveau harnais d'agent en ligne de commande : un module dans `src/orchestrateur/harnais/` qui implémente le contrat commun de tour, plus une entrée dans le registre `HARNAIS`. Les adaptateurs existants et leurs données de test enregistrées (`tests/donnees/`) servent de modèles.
- **Connecteurs** — faire entrer des tâches venues d'ailleurs (messagerie, courrier, scanner…) par l'API HTTP locale ou la commande `orch`, jamais en écrivant dans le vault dans le dos de GoldenBrain.
- **Traductions** — les documents d'accueil (README, CONTRIBUTING, SECURITY, ROADMAP) existent en quatre langues et doivent rester alignés ; traduire l'interface est un point de la feuille de route.
- **Gabarits de tâche et de projet** — gabarits de frontmatter (`[vault.gabarit_tache]`) et exemples de `contexte.md` pour des types de projets courants, au contenu fictif.

## Règles
- Aucune dépendance nouvelle ; interface sans étape de build (HTML, CSS, JS natifs).
- Un module ≤ 500 lignes avec son en-tête (rôle, frontières, invariants portés) ; un commentaire dit pourquoi et cite l'invariant concerné.
- Les tests n'écrivent jamais dans un vrai vault (dossier temporaire) et ne lancent jamais un vrai harnais (adaptateur factice).
- Chaque correction apporte son test de régression ; la documentation change dans le même commit que le code.
- **Aucune donnée personnelle** (INV-PUB-1) : ni nom, ni adresse électronique, ni chemin de votre poste, ni extrait d'un vrai vault ou d'une vraie conversation, ni identifiant de session, ni jeton. Données de test fictives seulement. Copiez `.sensible.exemple` en `.sensible` et inscrivez-y vos propres motifs : la porte les refusera.

## Le circuit d'une contribution
1. **D'abord un ticket.** Ouvrez un ticket avec le formulaire qui convient (*Bug report* ou *Feature request*) ; une question va dans les Discussions. Dans l'application, *Réglages → Installation et version → Signaler un problème* ouvre le formulaire avec la version et le système déjà remplis. Étiquettes : `bug`, `évolution`, `à trier`, et `bon premier ticket` ou `aide bienvenue` pour les tickets ouverts aux nouveaux venus.
2. **Une branche.** Dupliquez le dépôt (*fork*) et travaillez sur une branche nommée d'après le ticket (`correctif/123-titre-court`).
3. **Une demande de fusion** vers `main` de ce dépôt, liée au ticket (`Fixes #123`).
4. **Vérifications automatiques** (GitHub Actions) : la porte sous Linux et sous Windows, et la signature DCO. Les deux doivent être vertes.
5. **Revue automatique.** Un relecteur IA lit le diff (sécurité, invariants `INV-*`, tests, périmètre) et commente en P1 (bloquant), P2 (à reprendre), P3 (facultatif). Il n'exécute jamais votre code et ne fusionne jamais : il éclaire un mainteneur, qui décide.
6. **Intégration.** Le projet se développe dans un dépôt des mainteneurs dont celui-ci est le miroir. Une fois acceptée, votre modification y est appliquée par un mainteneur, auteur et signature conservés ; la version verte suivante republie ce dépôt, et votre demande est close avec un lien vers l'enregistrement publié. Elle est donc close plutôt que fusionnée — votre contribution y figure bel et bien.

Les testeurs suivent la branche `beta` : voir [BETA.fr.md](BETA.fr.md).

## Porte
`python scripts/check.py` doit être vert avant l'envoi : tests, contrôles de structure, carte du code, garde de publication. L'intégration continue joue la même porte sous Linux et sous Windows sur chaque demande de fusion. Les scénarios d'interface (`python scripts/check_ui.py`, Playwright) se jouent en local seulement.

## Signer ses commits (DCO)
Les contributions sont acceptées sous le [Developer Certificate of Origin](https://developercertificate.org/) : en signant, vous certifiez avoir écrit la modification ou avoir le droit de la soumettre sous la licence du projet. Ajoutez la signature à chaque commit avec `git commit -s`, qui ajoute une ligne `Signed-off-by: Votre Nom <votre@adresse>`. Aucun accord de licence de contributeur (CLA) n'est demandé. L'intégration continue refuse une demande de fusion qui contient un commit non signé.

Une demande de fusion = un sujet ; message de commit à l'impératif. Une évolution visible ajoute au message une ligne `Nouveauté: <ce qui change pour l'utilisateur, sans jargon>` : elle paraît dans `CHANGELOG.md` et la note de version.

## Licence
GoldenBrain est publié sous la licence Apache 2.0 (`LICENSE`). Vos contributions le sont aux mêmes conditions.
