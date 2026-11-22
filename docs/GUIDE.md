# Guide de GoldenBrain

Mis à jour le 2026-11-22.

GoldenBrain est un poste de pilotage : vous confiez des tâches à des agents IA (Claude Code, Codex, OpenCode, Copilot, Antigravity), chacune rangée à sa place dans votre vault (un dossier de notes Markdown). GoldenBrain organise et supervise ; l'agent travaille dans sa propre conversation, que vous pouvez reprendre à tout moment.

Ce guide se lit dans l'application (bouton « ? » en haut à droite), dans le dossier du code (`docs/GUIDE.md`) ou par un agent (`python orch.py guide`). Chaque section répond à trois questions : à quoi ça sert, comment faire, à savoir. Dans l'application, le champ « Chercher dans le guide » ne garde que les sections qui contiennent le mot ; le « ? » à côté du titre de Réglages, Équipe et Décisions ouvre directement leur section ; une section se partage par son lien (`#guide=reglages`).

## Installer

Deux voies : **en un clic** (sans invite de commandes ni Python à installer : tout est fourni), ou **à la main** depuis le code (Linux, Windows ci-dessous). Dans les deux cas il faut ensuite un vault (un dossier de notes Markdown, Obsidian ou non ; GoldenBrain démarre sans) et au moins un assistant IA (voir « Connecter les assistants IA »).

### En un clic

À quoi ça sert : installer GoldenBrain comme une application ordinaire. Python, ses composants et (sous Windows) Git sont embarqués ; rien d'autre n'est modifié sur l'ordinateur et aucun droit administrateur n'est demandé (sauf le paquet .deb, installé par la logithèque).

- **Windows** : télécharger `GoldenBrain-installation.exe` (page des versions de GoldenBrain sur GitHub), double-cliquer, suivre les trois écrans. GoldenBrain se lance à la fin, puis depuis le menu Démarrer. Windows peut avertir « éditeur inconnu » (installateur non signé) : « Informations complémentaires » puis « Exécuter quand même ».
- **Linux (Debian, Ubuntu)** : télécharger `goldenbrain_<version>_amd64.deb`, double-cliquer (logithèque) ou `sudo apt install ./goldenbrain_*.deb`. GoldenBrain apparaît dans le menu des applications et se lance aussi par la commande `goldenbrain`.
- **Linux (autres) et macOS** : copier-coller dans une invite de commandes (Terminal sur macOS), une seule fois :
  `curl -fsSL https://github.com/Greal-dev/goldenbrain/raw/main/installation/installer.sh | bash`
  L'installation dure deux à trois minutes, crée l'entrée de menu (Linux) ou `GoldenBrain` dans le dossier Applications de votre compte (macOS), puis lance GoldenBrain. Git est requis : sur macOS, accepter les outils proposés par le système, puis relancer la commande.
- **macOS, sans invite de commandes** : télécharger `GoldenBrain-macos-arm64.zip` (Mac récents ; `x86_64` pour les Mac Intel), l'ouvrir, glisser GoldenBrain dans Applications. L'application n'étant pas signée, le premier lancement se fait par clic droit → Ouvrir (ou Réglages Système → Confidentialité et sécurité → « Ouvrir quand même »).

Comment ça marche : chaque lancement ouvre le navigateur sur GoldenBrain, en démarrant GoldenBrain sur cet ordinateur s'il ne tourne pas encore (un second clic n'en démarre pas un second). Au premier lancement, l'application est recopiée dans votre dossier personnel (`~/.local/share/goldenbrain/app`, `~/Library/Application Support/GoldenBrain/app` ou `%LOCALAPPDATA%\GoldenBrain\app`) : c'est cette copie que la « Mise à jour d'un clic » fait avancer, et elle garde vos réglages (`config.toml`).

À savoir : l'installation parle la langue du système (français, anglais, allemand ou espagnol ; anglais pour toute autre langue) et, au premier lancement, la reporte dans `config.toml` (`[interface] langue`) pour que GoldenBrain s'ouvre dans la même langue ; un `config.toml` existant n'est jamais modifié. Réinstaller ou désinstaller ne touche jamais cette copie ni le vault. Le journal du démarrage est `lancement.log` dans le dossier de données (Linux, macOS). Pour construire soi-même les installateurs : `python scripts/construire_deb.py`, `construire_windows.py` (Inno Setup sous wine), `construire_macos.py` ; chaque composant téléchargé est vérifié par son empreinte (`installation/versions.txt`). Chaque version publiée sur la page des versions porte les quatre installateurs, reconstruits à chaque fois, et une note en anglais, français, espagnol et allemand (`python scripts/publier_version.py`, lancé par la publication).

### Linux

À la main, depuis le code (développeurs). Il faut Git et Python 3.12 ou plus récent.


1. Prérequis (Debian, Ubuntu) : `sudo apt install git python3 python3-venv`
2. Récupérer le code : `git clone https://github.com/Greal-dev/goldenbrain.git ~/goldenbrain && cd ~/goldenbrain`
3. Python dédié : `python3 -m venv ~/.venvs/goldenbrain`
4. Dépendances : `~/.venvs/goldenbrain/bin/pip install fastapi uvicorn pyyaml`
5. Désigner ce Python : `echo ~/.venvs/goldenbrain/bin/python > python.local`
6. Premier lancement : `./lancer.sh`, puis ouvrir http://127.0.0.1:8300

Le premier lancement crée `config.toml`, qui ne contient que vos écarts (tout le reste vient de `config.exemple.toml`).

### Windows

À la main, depuis le code (développeurs).

1. Installer Git et Python 3.12 (python.org) ; noter le chemin de `python.exe`.
2. Récupérer le code : `git clone https://github.com/Greal-dev/goldenbrain.git goldenbrain`
3. Dépendances : `python -m pip install fastapi uvicorn pyyaml`
4. Si `python` du PATH n'est pas le bon interpréteur, écrire son chemin complet sur la première ligne d'un fichier `python.local` à la racine du dossier.
5. Premier lancement : double-clic sur `lancer.cmd`. La page http://127.0.0.1:8300 s'ouvre.

### Où est le vault

Par défaut : `~/Documents/Vault`. Ailleurs, l'écrire dans `config.toml` :

```toml
[vault]
racine = "~/chemin/vers/mon-vault"
```

Un vault Obsidian existant convient tel quel : y pointer `racine` (voir « Organiser votre second cerveau »). Un dossier vide ou absent reçoit, à l'accueil et après validation, un classement de départ.

Port occupé : `[serveur]` puis `port = 8301`. Relancer après chaque changement de `config.toml`.

### Service au démarrage (Linux)

GoldenBrain démarre seul avec la session, et redémarre après une mise à jour.

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/goldenbrain.service <<'FIN'
[Unit]
Description=GoldenBrain

[Service]
WorkingDirectory=%h/goldenbrain
ExecStart=/bin/bash lancer.sh
Restart=on-failure

[Install]
WantedBy=default.target
FIN
systemctl --user daemon-reload
systemctl --user enable --now goldenbrain
```

- Démarrer même sans ouverture de session : `loginctl enable-linger "$USER"`.
- Journal : `journalctl --user -u goldenbrain -f`. Arrêt : `systemctl --user stop goldenbrain`.
- `WorkingDirectory` doit désigner le dossier du code (`%h` = votre dossier personnel).

### Connecter les assistants IA {#connecter-les-harnais}

Un assistant IA est le programme, utilisé depuis une invite de commandes, qui fait travailler l'agent. GoldenBrain le cherche dans le PATH ; il en faut au moins un, installé **et connecté**.

| Assistant IA | Installer | Se connecter |
|---|---|---|
| Claude Code | `npm install -g @anthropic-ai/claude-code` | `claude`, puis `/login` |
| Codex | `npm install -g @openai/codex` | `codex login` |
| GitHub Copilot CLI | `npm install -g @github/copilot` | `copilot login` |
| OpenCode | voir sa documentation (opencode.ai) | voir sa documentation |

À savoir : un assistant IA absent apparaît « indisponible », avec la raison, dans le choix du « Moteur » d'une tâche. Son chemin ou ses arguments se règlent dans `config.toml`, section `[harnais.<nom>]` (modèle : `config.exemple.toml`).

## Premiers pas

Dix minutes, sans rien configurer de plus.

0. **Au tout premier lancement**, une fenêtre « Bienvenue dans GoldenBrain » s'ouvre en deux étapes. *Votre assistant IA* : la liste des assistants IA reconnus (Claude Code, Codex, Copilot, OpenCode, Antigravity), chacun « prêt », « installé, connexion à faire » ou « pas installé ». Pour un assistant absent, « Comment l'installer » donne la page officielle et la commande à copier dans une invite de commandes (bouton « Copier ») ; installez-le, puis « Vérifier à nouveau ». GoldenBrain n'installe rien lui-même. *Première tâche* : « Lancer la démonstration » crée et lance une petite tâche (l'assistant se présente et propose trois idées, sans rien modifier sur le poste) ; la réponse arrive en général en une ou deux minutes. Dessous, « Réflexes de l'agent » propose d'ajouter aux consignes de vos assistants les réflexes GoldenBrain (voir Réglages), avec aperçu et accord. « Passer » ou « Plus tard » ferme la fenêtre et ouvre l'accueil. Pour la revoir : Réglages → « Installation et version » → « Revoir les premiers pas ».
1. **Créer une tâche** : « Nouvelle tâche » (en haut). Un titre suffit ; la description aide l'agent. En tête du formulaire, des **modèles prêts à l'emploi** (créer un petit site, analyser un tableau Excel ou CSV, rédiger un courrier, automatiser une tâche répétitive, résumer des documents, apprendre une notion) : un clic remplit le titre et la description, qu'il reste à compléter aux endroits marqués « [à compléter] » ; rien n'est créé avant « Créer ». Ajouter un modèle : déposer un fichier `.md` dans le dossier `modeles/` de GoldenBrain (en-tête `titre`, `resume`, `ordre` ; le texte dessous est la mission). Pour adapter un modèle livré, copiez-le sous un autre nom : une mise à jour peut remplacer les fichiers livrés. Projet : laisser « Arrivée (par défaut) » si vous ne savez pas où la ranger. Pendant la saisie, les tâches ouvertes proches s'affichent : « Compléter celle-ci » y ajoute votre demande au lieu d'en créer une autre ; si une tâche très proche existe, la création est refusée doucement et « Créer quand même » passe outre.
2. **La lancer** : cocher « Lancer tout de suite » à la création, ou écrire un premier message en bas de la tâche (Ctrl+Entrée envoie).
3. **Suivre la conversation** : la tâche s'ouvre à droite ; les réponses de l'agent s'affichent en direct. Le bandeau du haut liste les séances de travail en cours et en file.
4. **Répondre ou corriger** : écrire en bas ; la même conversation continue.
5. **Valider** : quand l'agent se déclare « Terminée », la tâche attend votre « Valider » ou « Renvoyer… » (avec un motif rendu à l'agent).
6. **Décisions** : le bouton « Décisions » (en haut) rassemble tout ce qui attend votre geste : tâches à valider, questions des agents, propositions de rangement et de liens, dont celles du jardinier (la revue de cohérence : elle ne fait que proposer, jamais d'écriture d'office ; `plafond` dans `[jardinage]` borne leur nombre par passage, 7 par défaut).

À savoir : l'installation neuve est en mode **Simple** (projets, tâches, conversation, statut, valider). Réglages → « Avancé » montre tout le reste.

## Organiser votre second cerveau

Le vault est votre **second cerveau** : des notes ordinaires (fichiers Markdown) que GoldenBrain, vous et l'IA lisez et enrichissez. Il se range en trois étages : **rôles → projets → tâches**.

- **Rôles (« casquettes »)** : vos grands domaines de vie, peu nombreux et durables. Exemple : « Travail », « Famille », « Association du quartier ».
- **Projets** : un résultat à obtenir dans un rôle, avec une fin. Exemple : sous « Famille », « Déménagement » ; sous « Travail », « Site du cabinet ». Plusieurs projets d'un même rôle se regroupent au besoin dans une **opération** (« Rentrée 2027 »).
- **Tâches** : une action précise dans un projet, confiée à l'IA ou à vous-même. Exemple : « Comparer trois devis de déménageurs ». Une tâche qui grossit devient un projet.

**Les dossiers du vault de départ** (créés par l'accueil si le vault est vide, après votre validation ; la tâche de démonstration des premiers pas, rangée dans `_meta/`, ne compte pas) : `Casquettes/` (les rôles et leurs projets), `Projets/` (projets nés d'une tâche), `Inbox/` (la boîte d'arrivée), `Ressources/` (ce qui sert à plusieurs projets : fiches pratiques, modèles, contacts), `Archives/` (ce qui est fini ou en sommeil), et la note `Lisez-moi.md` qui résume la méthode.

**Comment l'IA s'en sert** :
- **Avant chaque tâche**, l'agent lit la fiche `contexte.md` du projet (objectif, repères, consignes pour l'IA) : quelques lignes justes y valent mieux qu'une longue consigne répétée à chaque tâche.
- Les **notes** du projet (`notes/`) et celles que vous liez par `[[Nom de la note]]` lui donnent le fond du dossier.
- Le **graphe** (onglet « Notes », bouton « Graphe ») montre ce qui est relié et ce qui reste isolé.
- Le **jardinier IA** propose des liens et des rangements ; il n'écrit rien sans votre accord.

**Bonnes pratiques** :
1. **Capturer vite, ranger plus tard** : en cas de doute, tout va dans `Inbox/` ; un tri par semaine suffit.
2. **Une tâche = un résultat attendu** (« Rédiger le courrier à la mairie »), jamais un thème (« Mairie »).
3. **Tenir `contexte.md` à jour** : deux ou trois lignes, relues quand le projet change de cap.
4. **Archiver plutôt que supprimer** : `Archives/` garde l'historique sans encombrer.

**Vous avez déjà un vault Obsidian** : pointez `[vault] racine` dessus (voir « Où est le vault »), puis lancez l'accueil et cochez « Mon vault Markdown existant ». Il est repris en place, tel quel : aucun dossier n'est ajouté, aucune note n'est réécrite, le dossier `.obsidian` est ignoré, et les liens `[[…]]` fonctionnent dans les deux outils.

## Fonctions par écran

### Accueil

- **À quoi ça sert** : au premier lancement, reprendre l'existant (projets, conversations d'agents, vault) au lieu de partir d'un arbre vide.
- **Comment faire** : trois étapes, « Choisir », « Relire », « Valider ». Cocher les sources voulues (quelques questions, un dossier désigné, vos conversations Claude Code ou Codex, votre vault Markdown), puis « Proposer une structure » ; renommer, décocher ou glisser les éléments proposés ; « Valider » écrit, « Ouvrir mon arbre » termine. « Plus tard » ferme sans rien écrire.
- **Vault vide** : les questions sont cochées d'office (« Vos grands rôles », « Vos projets en cours », séparés par des virgules) ; l'étape « Relire » propose en plus un « Classement de départ » (dossiers `Casquettes/`, `Projets/`, `Inbox/`, `Ressources/`, `Archives/` et la note `Lisez-moi.md`), décochable. Chaque projet reçoit une fiche `contexte.md` à compléter (objectif, repères, consignes pour l'IA). Le bouton « ? » ouvre « Organiser votre second cerveau » dans un nouvel onglet.
- **À savoir** : lecture locale seulement, rien ne quitte le poste et aucun modèle n'est appelé. Rien n'est écrasé ; une tâche reprise continue sa conversation d'origine. Réglages → « Relancer l'accueil » ne propose que ce qui manque. Au premier lancement, l'accueil suit les premiers pas (voir « Premiers pas ») ; si vous avez lancé la démonstration, il ne s'ouvre plus de lui-même : « Relancer l'accueil » le rouvre.

### Arbre et listes

- **À quoi ça sert** : voir toutes les tâches à leur place (casquettes, opérations, projets, tâches) et leur état.
- **Comment faire** : volet gauche, onglet « Tâches » ; « Ouvertes » ou « Toutes ». Au centre, la vue d'ensemble en cascade (statut, activité, échéance, priorité) ; un clic sur un compteur de statut filtre. « À moi » ne garde que ce qui attend votre geste. La recherche (touche `/`) trouve tâches et notes.
- **Intégration en retard** : une tâche terminée dont la fiche cite une version `gb/*` pas encore intégrée à la version principale, plusieurs heures après son dernier enregistrement, porte une pastille orange. Version principale et retard toléré : Réglages → « Intégration des versions ».
- **Ranger** : glisser une tâche ou un projet sous un autre élément ; « Monter d'un niveau » (Maj+←) ; touche `m` pour déplacer au clavier ; tout geste s'annule pendant 10 s.
- **À savoir** : le dossier fait foi. Déplacer un projet déplace réellement son dossier, après un plan à approuver (« Appliquer ») et un point de restauration du vault (git).

### Tâche

- **À quoi ça sert** : la conversation d'un agent sur un travail précis, et sa fiche (ce qui est fait, résultat, comment l'essayer, ce qui reste).
- **Comment faire** : en-tête de la tâche : statut, assistant IA et modèle (le prochain message part avec eux), échéance, priorité. En bas, écrire puis Ctrl+Entrée. « Arrêter » interrompt la séance de travail ; « Interface native de l'assistant IA » ouvre la même conversation dans une invite de commandes, avec l'interface propre de l'assistant ; « Console GoldenBrain » la suit depuis une invite de commandes.
- **Renommer** : cliquez sur le titre de la tâche, il devient un champ ; Entrée enregistre, Échap annule. Seul le titre change : l'identifiant, le fichier du vault, les liens et la conversation restent les mêmes, et le nouveau titre apparaît partout (arbre, recherche, Telegram, tableau de bord). Un agent fait de même par `orch renommer <id> "<titre>"`.
- **Moi / IA** : le curseur de l'en-tête dit qui mène la tâche. « 👤 Moi » : aucun agent n'y travaille (conversation grisée, ni revue ni validation automatique) ; la tâche porte une pastille dans l'arbre. « 🤖 IA » : « Confier la suite » rend la main à l'agent, qui reçoit vos notes.
- **Notes** : panneau à côté de la conversation (chacun se replie). Notes datées, en Markdown, ajoutées et modifiées par vous seul ; l'agent les lit sans les écrire. Bouton IA : « Résumer », « Corriger » ou « Synthétiser », proposition à appliquer ou annuler. Au téléphone, les deux panneaux s'empilent.
- **Voir le résultat** : le bouton ouvre ce que l'assistant a produit, avec l'application habituelle de votre ordinateur : fichier cité dans la fiche ou écrit pendant la dernière séance de travail, site (adresse locale citée dans la fiche, ou `index.html` du dossier de travail) ou dossier de travail. Un seul résultat : il s'ouvre aussitôt ; plusieurs : une liste à choisir. Rien de trouvé : un message vous le dit. Disponible sur le poste seulement (refusé depuis un téléphone) ; un programme ou un script n'est jamais lancé : son dossier s'ouvre à la place.
- **Apprendre** : le menu « Apprendre » de l’en-tête fait expliquer (ou non) à l’assistant IA ce qu’il fait, pour cette tâche seulement ; par défaut il suit les Réglages. Les explications apparaissent dans des encadrés bleus de la conversation, et la fiche se termine par « Ce que vous pouvez retenir » (trois points).
- **Lignes** : un travail court (sans livrable ni branche propres, même objectif que la tâche) s'écrit en ligne, pas en tâche. La carte « Lignes » du détail est une liste cochable : texte, date, auteur (Moi ou IA), lien éventuel vers un document. « En tâche » promeut une ligne en tâche fille ; « En ligne » (en-tête) fait d'une tâche une ligne de sa tâche mère (la tâche est close, jamais supprimée). Un agent écrit `orch ligne <id> "<ce qui est fait>"` ; les lignes vivent dans un bloc encadré du fichier de la tâche, que la fiche de l'agent ne réécrit pas.
- **Nature** : développement (code, branche, intégration), opération (mail, compte, routine, démarche) ou pilotage (stratégie, communication, nom, licence, décision). Déduite du titre à la création, modifiable par le sélecteur « Nature » de l'en-tête ; pastille dans l'arbre et filtre « Nature » dans les filtres.
- **Plafond par parent** : au plus 10 tâches ouvertes directement sous un même parent (réglable : Réglages → Agents et ressources → Rangement), et pas de mélange des natures sous un même parent. Au-delà, « Nouvelle tâche » et `orch creer` proposent de ranger : en faire une ligne d'une tâche existante, la ranger sous un sous-groupe, ou créer un regroupement ; « Créer quand même » passe outre. Le jardinier IA signale les parents en excès.
- **Autres gestes** : « Lier… » (prérequis, alimente, voir aussi), « Créer à partir de » (tâche voisine), « Promouvoir en projet », « Solliciter… » (avis d'un expert de l'équipe).
- **À savoir** : statuts : Non commencée → En cours → En attente (il faut un humain) ou Terminée → Validée. « Bloquée » signale l'échec technique d'une séance de travail. Un projet peut exiger une vérification (`controle:` dans son `contexte.md`) avant qu'une tâche passe « Terminée ». Il peut aussi déclarer sa tâche d'intégration (`integration: <identifiant>` dans son `contexte.md`) : toute tâche créée dans ce projet l'alimente d'office, si bien que ses branches terminées sont fusionnées sans qu'on y pense. Dans le vault, « En attente » s'écrit `statut: retour-humain` ; un vault qui emploie un autre nom le déclare dans `config.toml` : `[vault]` puis `statut_retour = "<nom>"`.

### Décisions

- **À quoi ça sert** : un seul endroit pour trancher tout ce qui attend un humain.
- **Comment faire** : bouton « Décisions ». Pour chaque élément : « Valider », « Renvoyer… », répondre à l'agent, reporter (date), « Accepter » ou « Refuser » une proposition. Le jardinier IA (revue de cohérence) et les agents y proposent aussi de **renommer** une tâche dont le titre ne dit pas le fond du sujet (« Renommer « ventes du club » en « API/MCP ventes du club » », avec son motif) : le titre ne change que si vous acceptez. Plusieurs tâches cochées se valident d'un coup. Dès que vous avez répondu (ici, sur la fiche, par Telegram ou au manager), la décision quitte la liste : une mention discrète « Réponse envoyée, l'agent reprend » la remplace le temps que le tour démarre, et elle ne revient que si l'agent, après avoir lu votre réponse, pose une nouvelle question (nouvelle entrée).
- **À savoir** : les clôtures automatiques des 7 derniers jours y figurent sous « Clos automatiquement », chacune avec « Rouvrir ». La pastille « évitable ? » signale une question ou une validation que l'agent aurait pu trancher seul (simple information, rien n'est modifié) ; Réglages → « Pastille « évitable ? » » l'éteint ou règle son seuil.

### Aujourd'hui

- **À quoi ça sert** : savoir quoi faire maintenant.
- **Comment faire** : bouton « Aujourd'hui » (avec le nombre de tâches en retard). Groupes : en retard, dues aujourd'hui, dues sous sept jours, à moi ; chacun trié par priorité.
- **À savoir** : l'échéance (`echeance: AAAA-MM-JJ`) et la priorité (`priorite: haute | moyenne | basse`) se posent dans l'en-tête de la tâche ou à sa création.

### En cours

- **À quoi ça sert** : voir d'un coup d'œil ce que font vos assistants IA en ce moment, et ce qui attend.
- **Comment faire** : cliquer sur « En cours » (suivi du nombre), dans la barre du haut (adresse `#en-cours`). Pour chaque assistant au travail : la tâche et son projet, l'assistant et son modèle, depuis quand, ce qu'il fait (« lance les tests », « écrit build.py », « a modifié 3 fichiers »), l'avancement de sa liste d'étapes quand il en tient une, et les aides qu'il a lancées avec leur état et leur durée. Gestes : « Ouvrir », « Mettre en pause » puis « Reprendre », « Arrêter » (confirmation demandée). Dessous : les tâches en attente et leur raison (mémoire, crédit d’utilisation, prérequis, rang), les routines à venir, les incidents ouverts.
- **À savoir** : l'écran se met à jour seul quand un assistant avance ; rien ne tourne quand il est fermé. Les aides lancées sont suivies pour Claude Code et OpenCode ; l'avancement, pour Claude Code, OpenCode et Codex. Une pause à la main fige l'assistant sans rien perdre ; il ne reprend que sur « Reprendre » (la régulation de mémoire n'y touche pas).

### Compagnon mobile {#compagnon}
- **Travail en cours** : touchez l'étoile ★ d'une tâche (arbre ou « En cours » de l'Accueil) pour l'épingler sur ce téléphone ; le bouton « Travail en cours » de l'Accueil (`#travail`) ne montre que ces tâches, et chacune ouvre son chat : la conversation avec l'agent de la tâche et la saisie d'un message, envoyé comme depuis l'écran complet. L'épinglage est un réglage du téléphone (rien n'est écrit sur le poste) ; le chat exige le poste en ligne. Statut et structure ne changent que par les gestes habituels.

- **À quoi ça sert** : consulter depuis le téléphone, d'un coup d'œil, ce qui attend votre décision, ce qui travaille et l'arbre des projets (consultation ; seul geste : valider ou renvoyer une tâche terminée par son agent, en ligne, après confirmation).
- **Comment faire** : l'accès passe par le réseau privé Tailscale et un téléphone appairé (Réglages → Appareils ; pas à pas : `docs/TELEPHONE.md`). Sur le téléphone, bouton « Accueil » de la barre basse (adresse `#compagnon`) : « À décider » (la question de chaque décision), « En cours » (les assistants au travail), puis « Projets et tâches » (touchez un projet pour l'ouvrir, « ‹ » pour remonter). Toucher une décision ou une tâche l'ouvre dans l'écran habituel. Installée sur l'écran d'accueil, l'application s'ouvre directement sur cet Accueil ; une décision à valider forme une seule carte, avec ses boutons « Valider » et « Renvoyer » dans le même cadre. Si l'appairage échoue faute de réseau, le bouton « Réessayer » de la page le rejoue sans rescanner le code. Facultatif : `resume = true` dans `[distant]` ajoute au téléphone un résumé de 140 caractères du résultat d'une tâche à valider ; ce texte quitte le poste, jamais gardé hors ligne, éteint par défaut. Sur petit écran, l'écran « Décisions » s'empile : titre pleine largeur, boutons plus grands.
- **À savoir** : l'écran se met à jour seul tant qu'il est ouvert, et dit s'il est connecté ou s'il montre les données d'une heure donnée. Le hors-ligne est facultatif et désactivé par défaut : il faut `hors_ligne = true` dans `[distant]` de `config.toml`, puis cocher « Garder un aperçu hors ligne sur cet appareil » ; seuls les titres, statuts et décisions sont gardés, 7 jours, jamais le contenu des fiches ni des conversations. L'aperçu s'efface à la révocation de l'appareil ou par « Effacer les données de cet appareil ». Hors ligne, les gestes sont désactivés : ils exigent le poste. Hors connexion, l'écran le dit (« Hors connexion · données du … ») ; une erreur de geste précise que rien n'a changé.

### Notes

- **À quoi ça sert** : parcourir et modifier tout le vault sans quitter GoldenBrain.
- **Comment faire** : volet gauche, onglet « Notes » (mode Avancé). « Nouvelle note » ; « Modifier » (touche `e`, Ctrl+S enregistre) ; « Renommer / déplacer… » réécrit les liens.
- **À savoir** : si la note a changé ailleurs (Obsidian, un agent), l'enregistrement est refusé et les deux versions vous sont proposées. Les blocs Dataview ne sont pas exécutés.
- **Graphe** : bouton « Graphe » de l'onglet « Notes » (graphe global : notes, tâches, dossiers et leurs liens, filtres par casquette, projet, type, tag, période) ; bouton « Graphe » d'une tâche ou « Graphe local » d'une note (profondeur réglable). Un clic sur un élément ouvre la note ou la tâche.

### Routines

- **À quoi ça sert** : une consigne exécutée par un agent à heure fixe (revue quotidienne, relevé hebdomadaire).
- **Comment faire** : bouton « Routine » (horloge, en haut). Titre, consigne, programme (« chaque jour 08:00 », « en semaine 18:00 », « lundi,jeudi 09:30 », « toutes les 2 h de 8 h à 20 h », ou une expression cron), projet, conversation (la même ou une neuve à chaque exécution), rattrapage d'une échéance manquée. Dans la routine : « Mettre en pause », « Exécuter maintenant », historique des exécutions. Une tâche existante devient routine sur place par « Transformer en routine » (même note, même conversation) ; « Retirer la routine » la rend ordinaire.
- **À savoir** : une routine porte une horloge dans l'arbre ; elle ne s'exécute jamais deux fois en même temps et passe par la même file que les tâches.

### Chaînes

- **À quoi ça sert** : enchaîner plusieurs phases de travail confiées à l'IA sur un même dossier (ex. répondre à un appel d'offres : analyse, proposition de valeur, solution, rédaction, relecture), chaque phase partant du résultat de la précédente.
- **Comment faire** : bouton « Chaînes » (en haut) : liste des modèles, intégrés (« Réponse à un appel d'offres », « Article ou contenu ») et personnels, rangés dans `_meta/chaines/` du vault ; « Nouvelle chaîne » ou « Modifier » : titre, résumé, contexte commun, dossier surveillé et projet (facultatifs), puis les phases (titre, consigne, documents d'entrée, livrable attendu, assistant IA, modèle d'IA, case « Validation humaine après cette phase ») ajoutables, supprimables et réordonnables ; « Retirer » (modèles personnels, avec confirmation). Lancement manuel : « Lancer » dans la liste, ou ⛓ sur un projet : modèle, projet, dossier traité, titre facultatif. Une tâche parente est créée, avec une tâche par phase ; son détail montre les phases numérotées avec leur état, un lien vers chacune, l'état de la chaîne et son erreur éventuelle. « Valider et poursuivre » reprend après une phase à validation humaine ; « Reprendre » relance la phase en échec.
- **À savoir** : les phases se déroulent une à une, jamais en parallèle. Si un dossier surveillé est indiqué, chaque nouveau sous-dossier lance la chaîne, sans rattrapage de ceux qui existaient déjà. L'IA peut adapter les phases à venir au dossier réel (sauter, ajouter, dédoubler, changer une consigne) : chaque ajustement est signalé dans le détail, avec son motif.

### Équipe

- **À quoi ça sert** : des experts (regards spécialisés) qui relisent les tâches terminées.
- **Comment faire** : bouton « Équipe » (mode Avancé), « Nouvel expert » : nom, mandat (ce qu'il examine), focus (ce qu'il vérifie d'abord), déclenchement (toujours, sur filtre, ou à la demande), assistant IA et modèle. Depuis une tâche : « Solliciter… ».
- **À savoir** : un expert donne un avis ; il ne valide pas, sauf réglage `[validation] mode = "persona"`.

### Réglages

- **À quoi ça sert** : régler l'interface et le moteur sans éditer de fichier.
- **Comment faire** : bouton « Réglages ». Six groupes repliables, chacun titré de son état en une ligne : Affichage (langue, niveau de détail, thème, invitation à l'étoile), Fonctions affichées, Agents et ressources (agents en même temps, performance ou économie, résumé des longues conversations, mode Apprendre, assistants IA par rôle), Validation et propositions (propositions des agents, pastilles « évitable ? » et « intégration en retard »), Connexions (Telegram, téléphone et autres appareils, ordinateurs d'appoint), Installation et version (mise à jour : canal et mode automatique, signaler un problème, revoir les premiers pas, relancer l'accueil). Cliquer un titre l'ouvre ou le referme ; les groupes ouverts sont retenus d'une visite à l'autre. Le champ « Chercher un réglage » ouvre le groupe concerné (ex. « mémoire », « Telegram »). Lien direct vers une section : `#reglages/telegram`, `#reglages/simultanes`, `#reglages/economie`, `#reglages/compactage`, `#reglages/appareils`, `#reglages/executeurs`, `#reglages/installation`, `#reglages/premiers-pas`…
- **Langue** : français, English, Deutsch ou español. Au premier lancement, GoldenBrain prend celle du navigateur ; Réglages → Affichage → Langue (ou le premier écran de l'accueil) la change, et la page se recharge. Elle vaut pour les écrans, les messages, l'aide « ? » (guide de la langue choisie) et les réponses des agents ; les noms de dossiers, les statuts du vault et les commandes ne changent pas.
- **Mode Apprendre** : Réglages → Agents et ressources → Mode Apprendre. Activé, l’assistant IA explique en une ou deux phrases simples ce qu’il fait et pourquoi à chaque étape, puis conclut par « Ce que vous pouvez retenir ». Coût : un peu plus de texte à chaque séance de travail, donc un peu plus de crédit d’utilisation consommé. Désactivé, rien ne change.
- **Réflexes de l'agent** : Réglages → Agents et ressources → Réflexes de l'agent (et la fin des premiers pas). GoldenBrain propose d'ajouter aux consignes de chaque assistant IA du poste (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`…) quelques réflexes : rattacher chaque travail à une tâche (reprise d'abord, sinon création), noter dans la fiche les documents créés ou modifiés, lier tâches, documents et notes, consigner le résultat. Pour chaque assistant : l'état (absent, à jour, ancienne version, modifié à la main), « Voir le changement » (les lignes ajoutées ou retirées), puis « Accepter », « Plus tard » ou « Retirer ». Rien n'est écrit sans ce clic ; le bloc est encadré de deux marqueurs, le reste du fichier n'est jamais touché. Après une mise à jour qui change les réflexes, la proposition revient.
- **Rangement** : Réglages → Agents et ressources → Rangement. Plafond de tâches ouvertes sous un même parent (10 par défaut, de 2 à 100) et séparation des natures de travail (développement, opération, pilotage) ; écrits dans `[rangement]` de `config.toml`.
- **Étoile GitHub** : après quelques heures d'usage, et seulement si GoldenBrain est public sur GitHub, une fenêtre unique propose « Mettre une étoile », « Plus tard » ou « Ne plus demander » ; Réglages → Affichage l'éteint.
- **À savoir** : l'interface n'écrit que dans `config.toml`. Les autres clés (vault, assistants IA, consigne des agents) se règlent dans ce fichier, d'après `config.exemple.toml`. Une saisie en cours n'est plus perdue quand un agent travaille en arrière-plan. Les bordures des champs et boutons atteignent un contraste de 3:1 contre le fond dans les deux thèmes (WCAG 1.4.11).

### Mise à jour d'un clic

- **À quoi ça sert** : passer à la dernière version sans invite de commandes.
- **Comment faire** : quand le bandeau « Une mise à jour est disponible » paraît, cliquer « Mettre à jour » ; la page attend le redémarrage puis se recharge. Sans l'interface (Windows) : double-clic sur `mettre-a-jour.cmd`.
- **À savoir** : refusé tant qu'un agent travaille (réessayer après) ou si des fichiers de GoldenBrain ont été modifiés à la main. Le dossier avance seulement, sans jamais mélanger de modifications ; `config.toml`, `etat`, `journal` et `equipe` ne sont jamais touchés. Source : la version principale (`main`) du dossier du code public https://github.com/Greal-dev/goldenbrain (le distant `origin` d'un clone), réglable par `[mise_a_jour] branche` et `distant`.
- **Quoi de neuf** : le bandeau porte « Quoi de neuf ? » ; un clic déplie les nouveautés de la version en attente, en langage courant. Le journal complet de chaque version publiée est `CHANGELOG.md`, à la racine du dossier ; chaque version publique a aussi sa note sur la page « Releases » du dossier du code public (s'y abonner : « Watch » → « Custom » → « Releases », ou le flux https://github.com/Greal-dev/goldenbrain/releases.atom).
- **Canal stable ou bêta** : Réglages → « Installation et version » → « Mise à jour » → « Canal ». « Bêta » suit la version `beta` du dossier du code public (versions en essai, avant `main`) ; le bandeau propose alors « passer au canal bêta » et le bouton « Mettre à jour » change de version puis redémarre GoldenBrain. Revenir à « Stable » se fait de même. Refusé si le code a été modifié à la main, ou depuis une autre version que `main` ou `beta` ; le vault n'est jamais touché. Pour tester et donner votre avis : page « Devenir testeur » (`BETA.md`).
- **Signaler un problème ou proposer une idée** : Réglages → « Installation et version » → « Signaler un problème ou proposer une idée ». Les liens ouvrent, dans le navigateur, le formulaire GitHub du projet public avec la version (empreinte, date, canal) et le système déjà remplis — rien d'autre : ni nom, ni chemin, ni contenu du vault. GoldenBrain n'envoie rien ; vous relisez et envoyez vous-même (compte GitHub requis). « Poser une question » ouvre les Discussions.
- **Mise à jour automatique** : Réglages → « Installation et version » → « Mise à jour » → « Appliquer seule une mise à jour disponible » (désactivée par défaut). Aucune nouvelle séance de travail ne démarre pendant la préparation ; les séances en cours finissent, une séance qui dépasse le délai réglé n'est coupée (puis reprise) qu'à un point de reprise sûr. Plage horaire facultative ; la mise à jour attend aussi que vous ne touchiez plus à l'interface. Un échec s'affiche dans un bandeau, avec le geste à faire.
- **Redémarrer pendant une séance de travail** : « Redémarrer » refusé parce que des séances de travail sont en cours propose « Redémarrer GoldenBrain dès que les séances de travail sont finies » (GoldenBrain seulement, jamais l'ordinateur) ; l'attente s'annule depuis le même bandeau.

### Manager

- **À quoi ça sert** : converser avec un agent général qui pilote toutes les tâches — « Qu'est-ce qui m'attend ? », « Où en est X ? », confier un sujet (il l'oriente vers la tâche ou le projet qui convient, ou en crée une), mettre à jour, relancer, rapprocher deux doublons.
- **Comment faire** : bouton « Manager » du bandeau ; le volet s'ouvre à droite, sur tous les écrans, et le reste d'un rechargement à l'autre. Écrire, puis Entrée (Maj+Entrée : à la ligne). « × » le ferme ; sur téléphone, il occupe l'écran et « ← Retour » le ferme.
- **À savoir** : c'est l'assistant de Telegram, sur le même fil : ce qui est écrit d'un côté se lit de l'autre (mention « via Telegram »), et `/nouveau` ouvre un fil neuf pour les deux. Un changement de statut, d'échéance ou de priorité attend votre « Confirmer » (dans le volet ou sur Telegram, une seule fois) ; une restructuration passe par Décisions. Le volet marche sans Telegram et ne charge rien tant qu'il est fermé. Le fil garde les 200 derniers messages et se relit seul après une coupure ; il ne descend au dernier message que si vous lisiez déjà le bas.

### Telegram

- **À quoi ça sert** : envoyer une idée, une photo ou une note vocale depuis le téléphone ; elle devient une tâche rangée.
- **Comment faire** : Réglages → Connexions → Telegram ; un assistant guide pas à pas. Créer un bot avec @BotFather (« J'ai mon bot et sa clé d'accès ») ; saisir sa clé d'accès (« Saisir la clé d'accès dans une invite de commandes sécurisée », ou dans le navigateur en solution de repli) ; confirmer le nom du bot (« Oui, c'est mon bot ») ; écrire au bot dans Telegram, puis « Me reconnaître » et cocher votre discussion ; « Envoyer le message de test », puis « Oui, terminer et activer Telegram ».
- **À savoir** : la clé d'accès est rangée dans le coffre de l'ordinateur et jamais réaffichée. Un seul programme peut écouter un bot : arrêter tout autre lecteur avant. Répondre au message « Tâche créée : … » écrit à cette tâche. Un ordre qui ressemble à une tâche ouverte fait proposer sa mise à jour plutôt qu'une tâche nouvelle. « Répondre » à un message de l'assistant lui transmet le texte cité (une citation, jamais un ordre) et la tâche dont il parlait.

### Ordinateurs d'appoint {#executeurs-distants}

- **À quoi ça sert** : faire travailler les agents sur d'autres ordinateurs ; le vault et l'interface restent sur l'ordinateur principal.
- **Comment faire** : relier les ordinateurs par Tailscale ; sur l'ordinateur principal, `config.toml` : `[executeurs]` puis `ecoute = "<adresse Tailscale de l'ordinateur principal>"`, redémarrer ; Réglages → Connexions → « Ordinateurs d'appoint » → « Appairer un ordinateur » donne un code court. Sur l'autre ordinateur : `python orch.py executeur --serveur http://<adresse de l'ordinateur principal>:8300 --code <code>`, ou Réglages → « Faire de cet ordinateur un ordinateur d'appoint ».
- **À savoir** : détail, pannes et essai : `docs/EXECUTEURS.md`. Ne jamais exposer GoldenBrain sur Internet.

## Dépannage

| Symptôme | Cause probable | Geste |
|---|---|---|
| La page http://127.0.0.1:8300 ne répond pas | GoldenBrain arrêté | Relancer `./lancer.sh` ou `lancer.cmd` ; sous systemd, `systemctl --user status goldenbrain` |
| `ModuleNotFoundError: fastapi` au lancement | Mauvais Python | Vérifier la première ligne de `python.local`, réinstaller les dépendances avec ce Python |
| « Address already in use » | Port pris | `[serveur] port = 8301` dans `config.toml` |
| L'arbre est vide | Vault introuvable | `[vault] racine` dans `config.toml`, puis relancer |
| Assistant IA « indisponible » | Programme absent du PATH ou non connecté | Installer, se connecter (voir « Connecter les assistants IA ») |
| Incident « Assistant IA non installé » | Un assistant IA de `[credits]` n'est pas installé sur cet ordinateur | Rien d'urgent : la séance de travail est relancée une fois sur l'assistant suivant de `[credits]`, et l'équilibrage ne choisit plus l'absent. Installer l'assistant (voir « Connecter les assistants IA ») ou le retirer de `[credits]` |
| Tâche « Bloquée » | Échec technique de la séance de travail | Lire la cause dans la conversation, puis écrire un message ; une séance interrompue se reprend par « Relancer ». Les messages reçus pendant le blocage (Telegram, autres agents) attendent en file et repartent dans l'ordre dès qu'on écrit, change de moteur ou change le statut (tâche close : ils tombent) |
| Tâche « En attente du poste » | Une épreuve lourde a réservé le poste | Attendre (le rang dans la file s'affiche sur la tâche et dans le bandeau), ou « Libérer » dans le bandeau « Poste réservé » |
| « Une mise à jour est disponible » ne s'applique pas | Agent au travail, ou fichier de GoldenBrain modifié | Réessayer après la séance de travail ; `git status` dans le dossier |
| Bandeau « Redémarrer » | GoldenBrain mis à jour, mais tourne encore sur l'ancienne version | Cliquer « Redémarrer » |
| Un agent Claude Code ne voit pas ses serveurs MCP (navigateur…) | Par défaut, aucun serveur MCP par séance de travail (économie de mémoire) | `mcp: heritage` dans l'en-tête de la note de la tâche, ou `[harnais.claude] mcp = "heritage"` dans `config.toml` |
| « Connexion perdue… » | GoldenBrain redémarré ou arrêté | Attendre quelques secondes ; sinon relancer |

## Pour un agent IA

À lire par tout agent — Claude Code, Codex, OpenCode, Gemini CLI ou autre — qui pilote GoldenBrain ou travaille dans son dépôt. GoldenBrain ne s'appelle pas par une bibliothèque : on lui parle par la commande `python orch.py` (depuis la racine du dépôt, jamais par un `.cmd`) ou par son API locale.

**1. Démarrer et vérifier le serveur**

- Démarrer : `./lancer.sh` (Linux, macOS) ou `lancer.cmd` (Windows), à la racine du dépôt.
- Vérifier : `curl -s http://127.0.0.1:8300/api/etat` répond un objet JSON (tours en cours, file, décisions). Un refus de connexion : le serveur n'est pas lancé.
- Autre adresse (port réglé dans `config.toml`, serveur d'essai) : variable `ORCH_URL`, par exemple `export ORCH_URL=http://127.0.0.1:8301` ; `orch.py` la lit.
- Un agent lancé par GoldenBrain reçoit `ORCH_URL`, `ORCH_TACHE` (sa tâche) et `ORCH_SAUTS` ; `orch.py` s'en sert pour signer ses messages et borner les relais.

**2. Commandes `orch`**

| Commande | Effet |
|---|---|
| `guide` | ce guide |
| `arbre` | arbre des tâches ouvertes |
| `chercher "<mots>"` | tâches connexes |
| `lire <id>` | fiche, chemin, place, statut, exécution d'une tâche |
| `conteneurs` | conteneurs où ranger une tâche |
| `rapprochement ["<titre>"]` | tâches proches d'un titre ; sans titre, créations évitées |
| `tracer <id> "<texte>" [--document <chemin>]…` | consigner dans la fiche (section « Traces ») ce qui a été fait et les documents créés ou modifiés ; un document du vault devient un lien |
| `reflexes [etat\|apercu\|installer\|retirer] [--harnais <id>] [--dossier <projet>] [--langue fr] [--accord]` | réflexes GoldenBrain dans les consignes de l'assistant : état, aperçu (diff) ; écrit seulement avec `--accord`, après l'avoir montré à l'utilisateur |
| `creer "<titre>" --description "<une phrase au moins>"` | créer une tâche (`--conteneur`, `--parent`, `--lancer`, `--mission`) ; refusée si une tâche ouverte très proche existe : la compléter (`dire`) ou forcer (`--nouvelle`) |
| `ligne <id> "<texte>" [--document <chemin>] [--fait] [--cocher N]` | ajouter une ligne à une tâche (un travail court n'est pas une tâche), ou cocher la ligne N ; à la création, un 409 de rangement propose lignes, sous-groupes et regroupements |
| `dire <id> "<message>"` | écrire à la tâche : son agent le reçoit au prochain tour (le lance s'il est libre) |
| `renommer <id> "<titre>"` | changer le titre d'une tâche (identifiant et fichier inchangés) |
| `relancer <id>` | relancer une tâche en échec ou interrompue |
| `arreter <id>` | arrêter le tour en cours |
| `deleguer "<titre>" "<brief>"` | confier un travail à une tâche enfant lancée par GoldenBrain |
| `proposer deplacer\|projet\|operation\|ticket\|tache\|lier\|perimetre\|echeance\|fermer\|renommer …` | proposer un changement de structure (`--motif`, obligatoire pour `renommer`) ; l'humain accepte d'un clic. En mode simple, les propositions sont ignorées (Réglages > Propositions) |
| `solliciter <persona> "<question>"` | avis d'un persona de l'équipe |
| `telegram "<texte>"` | message à l'utilisateur sur Telegram (`--validation`, `--choix`) ; exige le bot configuré |
| `poste reserver "<motif>"` / `poste liberer` | réserver le poste pendant une épreuve lourde ; s'il est pris, attendre son tour (`--attente <min>`, défaut 30) |
| `chaine plan\|sauter\|ajouter\|dedoubler\|consigne …` | adapter la chaîne de la tâche au dossier réel : `plan` la montre ; sauter, ajouter, dédoubler une phase ou changer sa consigne (phase à venir seulement), toujours avec `--motif` : l'ajustement est journalisé et montré à l'utilisateur |
| `feu-vert demander\|accorder\|refuser\|verifier …` | feu vert lié à une version |

`python orch.py <commande> -h` donne les options de chacune.

**3. API REST** (http://127.0.0.1:8300, JSON). Toute écriture porte l'en-tête `X-Orchestrateur: 1` ; sans lui, le serveur répond 403 (garde contre une page web tierce).

| Route | Effet |
|---|---|
| `GET /api/etat` | état du poste : tours en cours, file, décisions, propositions |
| `GET /api/arbre` | arbre des tâches |
| `GET /api/recherche?q=<mots>` | chercher |
| `GET /api/taches/{id}` | une tâche (statut, fiche, notes, exécution) |
| `POST /api/taches` | créer : `titre`, `description`, et au choix `conteneur`, `parent`, `lancer`, `mission`, `harnais`, `modele`, `echeance`, `priorite` |
| `POST /api/taches/{id}/messages` | écrire à la tâche : `texte` (et `de` : l'id de la tâche qui écrit) |
| `POST /api/taches/{id}/traces` | consigner : `texte`, `documents` (chemins absolus) |
| `GET /api/accueil/reflexes` · `POST …/appliquer` · `POST …/plus-tard` | réflexes de l'agent (poste seulement) : état par assistant et aperçu ; `harnais`, `action` (`installer`, `retirer`) |
| `POST /api/taches/{id}/statut` | poser un statut : `statut` — geste humain, voir les règles |
| `POST /api/taches/{id}/notes` | ajouter une note de l'humain : `texte` |
| `POST /api/taches/{id}/executant` | `executant` : `humain` (Moi) ou `ia` |
| `POST /api/taches/{id}/relancer` | relancer |
| `GET /api/propositions` · `POST /api/propositions` | lister · proposer : `type`, `tache`, `valeur`, `motif` |
| `POST /api/propositions/{n}/accepter` · `…/refuser` | trancher — geste humain |
| `GET /api/guide` | ce guide, en texte brut |
| `GET /api/evenements` | flux d'événements (SSE) |

**4. Règles**

- **Rapprocher avant de créer** : `chercher` ou `rapprochement "<titre>"` d'abord ; une tâche proche se complète (`dire`) plutôt que d'être doublée.
- **Réflexes et traçage** : au premier contact, `reflexes` montre si les consignes de l'assistant portent les réflexes GoldenBrain ; sinon, présenter l'aperçu à l'utilisateur et n'écrire (`--accord`) qu'avec son accord. En cours de travail, `tracer` consigne chaque document créé ou modifié, et le résultat en fin de travail.
- **Intégration** : dans un projet qui déclare `integration:`, `creer` et `deleguer` relient d'office la nouvelle tâche à la tâche d'intégration (`alimente`) ; ailleurs, une tâche qui livre une branche propose ce lien (`proposer lier <id> alimente <intégration>`).
- **Jamais de changement de statut sans accord humain** : un agent ne pose pas `fait`, n'accepte pas une proposition, ne valide pas une tâche ; il rend sa fiche et l'humain valide. Les routes `statut`, `valider`, `accepter` sont des gestes de l'interface.
- **Tâches « Moi »** (`executant: humain`) : l'humain la mène ; GoldenBrain y refuse tout tour et toute écriture d'agent (un agent peut la lire et proposer) ; « Confier la suite » est le geste humain qui la rend à l'IA.
- Le vault est la seule base de données ; ne jamais reformater le frontmatter d'une note.
- Ne jamais déplacer un dossier soi-même : proposer (`orch proposer`), l'humain accepte.
- Aucun envoi, publication, paiement ni suppression sans accord écrit de l'utilisateur.
- Un agent lancé par GoldenBrain finit chaque réponse par le bloc `<fiche>` décrit dans la consigne reçue.

**5. Exemples de bout en bout**

Retrouver ou créer une tâche, puis la confier :

```bash
python orch.py rapprochement "Rédiger la note de version"
python orch.py creer "Rédiger la note de version" \
  --description "Résumer les changements de la semaine ; preuve : la note existe dans le vault."
python orch.py lire 2026-11-19-rediger-la-note-de-version
python orch.py dire 2026-11-19-rediger-la-note-de-version "Commence par le journal git de la semaine."
```

La même chose par l'API :

```bash
curl -s http://127.0.0.1:8300/api/etat
curl -s -X POST http://127.0.0.1:8300/api/taches \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' \
  -d '{"titre": "Rédiger la note de version", "description": "Résumer les changements de la semaine ; preuve : la note existe dans le vault."}'
curl -s "http://127.0.0.1:8300/api/recherche?q=note%20de%20version"
curl -s -X POST http://127.0.0.1:8300/api/taches/2026-11-19-rediger-la-note-de-version/notes \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' -d '{"texte": "Garder le ton sobre."}'
```

Proposer un rangement plutôt que le faire :

```bash
python orch.py proposer deplacer 2026-11-19-rediger-la-note-de-version Projets/C1-Site \
  --motif "la note de version relève du site"
```

L'identifiant d'une tâche est rendu par `creer` (et par `arbre`, `chercher`) : date du jour et titre en minuscules.

**Suite** : `docs/ARCHITECTURE.md` (modules, invariants `INV-*`, contrats), `docs/CODE_MAP.md` (carte des fichiers), `CLAUDE.md` (règles du dépôt).
