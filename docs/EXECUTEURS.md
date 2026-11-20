# Exécuteurs distants — GoldenBrain sur plusieurs PC

Un seul GoldenBrain **chef** (le poste qui porte le vault, la file, l'interface et les décisions) ; sur
d'autres PC, un **exécuteur** léger reçoit des tours, fait tourner le harnais chez lui et renvoie les
événements en direct. Le chat et la console ne voient pas la différence. Invariants : INV-DISTANT-1 à
INV-DISTANT-4 (`docs/ARCHITECTURE.md`).

- L'exécuteur **se connecte** au chef (sortant) ; rien n'écoute sur l'exécuteur.
- Le **vault ne quitte jamais le chef** : l'agent distant lit et écrit les tâches par `orch` (API du chef).
- Le **code passe par GitHub** : l'exécuteur clone ou met à jour le dépôt de la tâche, l'agent travaille
  sur une branche `gb/…` et la pousse.
- Une **conversation reste sur le PC où elle est née**. Une tâche peut être épinglée : `executeur: <nom>`
  (ou `executeur: chef`) dans son frontmatter. `vault: intensif`, une tâche sans dépôt git, un tour de rôle
  (revue, persona) ou `ou: codespace` restent au chef.
- Répartition : le chef garde ses tours tant qu'il a un créneau libre (règle des agents simultanés) ;
  au-delà, un tour part vers l'exécuteur connecté qui a une place.

## 1. Réseau : Tailscale (recommandé)

Tailscale relie les PC par un réseau privé chiffré, sans ouvrir de port sur Internet.

1. Installer Tailscale sur le chef et sur chaque exécuteur, se connecter au même compte (tailnet).
2. Sur le chef : `tailscale ip -4` donne son adresse (forme `100.x.y.z`).
3. Facultatif : dans la console Tailscale, une règle d'accès (ACL) qui n'autorise que les exécuteurs à
   joindre le port de GoldenBrain sur le chef.

Ne jamais exposer GoldenBrain sur Internet (pas de redirection de port sur la box, pas de « Funnel »).

## 2. Chef : ouvrir l'écoute et créer un jeton

Dans `config.toml` du chef :

```toml
[executeurs]
ecoute = "100.x.y.z"   # l'adresse Tailscale du chef, jamais 0.0.0.0
```

Redémarrer GoldenBrain. Le chef écoute alors sur `127.0.0.1` **et** sur cette seule adresse ; tout ce qui
arrive par elle exige un jeton d'exécuteur.

**Appairage par code (le plus simple).** Réglages → « PC connectés » : saisir le nom du PC, « Appairer un PC ». Le chef affiche un code court (`ABCD-EFGH`, à usage unique, valable 10 minutes) et la commande à taper sur l'autre PC. Le code ne s'ouvre que depuis le poste du chef ; cinq saisies fausses de suite le verrouillent 60 s. Le jeton n'est jamais affiché : l'exécuteur le reçoit et le garde (voir §3).

Sinon, créer un jeton à la main, depuis Réglages → « PC connectés » (bouton « Créer un jeton »), ou :

```
python orch.py jeton-executeur portable
```

Le jeton n'est montré **qu'une fois** ; seule son empreinte est gardée (`<donnees>/etat/executeurs.json`).
Le révoquer : bouton « Révoquer », ou `python orch.py jeton-executeur portable --revoquer`.

## 3. Exécuteur : installation

**Assistant (recommandé)** : `python orch.py executeur installer [--harnais claude,codex] [--verifier]`, ou Réglages →
« Ajouter ce PC comme exécuteur ». Il vérifie Python 3.12+, git, Tailscale, GitHub CLI (facultatif) et les harnais choisis
(Claude Code, Codex, Copilot, OpenCode, Antigravity), puis leur connexion. Pour chaque étape il affiche
« Ce qui va être fait : <commande> » et ne lance rien sans accord, une étape à la fois (défaut : non). Sans droits
administrateur, il donne les instructions à copier dans un terminal administrateur. Les connexions (`claude auth login`,
`codex login --device-auth`, `gh auth login`…) se font dans l'outil officiel : GoldenBrain n'en voit jamais les identifiants.
Une connexion qui dialogue se lance dans un terminal (l'interface l'indique). L'étape finale propose l'appairage (adresse du
chef + code court). Python embarqué : il se désigne par `python.local` (voir le README), l'assistant ne l'installe pas.
Les commandes d'état et de connexion de chaque outil (`claude auth status`, `codex login status`, identifiants winget) sont
à confirmer à l'essai réel sur un second PC.

**État par PC et « Réparer »** : un exécuteur lancé par `orch executeur` annonce au chef, au plus une fois par minute, l'état de
ses étapes (fait, manquant, à connecter…). Réglages → PC connectés les affiche sous chaque PC. Sur une étape manquante ou à
connecter d'un PC connecté, « Réparer » demande confirmation (« Sur <PC>, lancer : <commande> ») puis fait relancer cette seule
étape par l'exécuteur, qui ne lance que la commande de son propre catalogue. Une étape qui dialogue (connexion) ou demande les
droits administrateur rend ses instructions, à faire sur ce PC ; le résultat s'affiche sous le PC.

Prérequis : Python 3.12 avec les dépendances du dépôt, `git`, le harnais voulu installé **et connecté**
(`claude`, `codex`…), et l'accès GitHub aux dépôts des tâches (`gh auth login` ou clé SSH).

```
git clone <url du dépôt GoldenBrain> goldenbrain
cd goldenbrain
python orch.py executeur --serveur http://100.x.y.z:8300 --code ABCD-EFGH
```

Avec `--code`, l'exécuteur échange le code contre son jeton et le range dans `~/.goldenbrain-executeur.json` (dossier personnel, hors dépôt) avec l'adresse du chef. Les fois suivantes, `python orch.py executeur` seul suffit ; pour un autre chef, refaire l'appairage. Variante sans appairage : `--jeton <jeton>`.

Options : `--depots <dossier>` (clones des dépôts, défaut `~/goldenbrain-depots`), `--places N` (tours
simultanés acceptés, défaut 1). Le jeton peut venir de la variable `ORCH_JETON_EXECUTEUR` plutôt que de
la ligne de commande. Laisser la fenêtre ouverte : elle affiche les harnais trouvés et les incidents.

## 4. Codespace GitHub comme exécuteur

Un codespace se rejoint au tailnet comme un PC : installer Tailscale dans le codespace
(`curl -fsSL https://tailscale.com/install.sh | sh`, puis `sudo tailscaled --tun=userspace-networking &`
et `sudo tailscale up`), installer le harnais, puis lancer la même commande `orch executeur`. Le
codespace se met en veille : ses tours passent alors « en attente de l'exécuteur » et reprennent quand il
revient.

## 5. Pannes

- **Exécuteur perdu** (veille, coupure, changement de réseau) : après 45 s sans signe de vie, ses tours
  passent « en attente de l'exécuteur » (Réglages → « PC connectés ») ; rien n'est tué. Au retour, les
  événements retenus sont renvoyés ; un tour perdu par un redémarrage de l'exécuteur est relancé une
  fois dans la même conversation, avec le message de reprise.
- **Chef redémarré** : l'exécuteur abandonne les tours que le chef ne connaît plus ; la reprise du chef
  les relance sur le même exécuteur.
- **Jeton refusé** : `orch executeur` s'arrête avec « jeton refusé par le chef ».

## 6. Essai sur un second PC

1. Chef : Tailscale, `[executeurs] ecoute`, redémarrage, code d'appairage pour le nom « essai » ouvert dans Réglages (« Appairer un PC »).
2. Second PC : Tailscale, `python orch.py executeur --serveur http://<ip-chef>:8300 --code <code affiché>`.
3. Réglages du chef : « essai — connecté · N / M Go libres · 0/1 tour ».
4. Une tâche d'un projet qui a un dépôt GitHub, frontmatter `executeur: essai` ; lui écrire « liste les
   fichiers du dépôt puis lis ta tâche par orch lire ». Attendu : le chat se remplit en direct, la
   réponse cite des fichiers du clone (dans `~/goldenbrain-depots` du second PC) et la fiche de la tâche.
5. Pendant un tour, fermer la fenêtre de l’exécuteur : au bout de 45 s, « en attente de l’exécuteur » ; la
   relancer : le tour reprend dans la même conversation (message de reprise) et se termine.
