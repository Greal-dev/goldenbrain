# Accès depuis le téléphone — réseau privé, appairage par code QR, révocation

GoldenBrain reste un service du poste. Le téléphone l'atteint par un **réseau privé chiffré**
(Tailscale), jamais par Internet : aucun port de la box ne s'ouvre, aucun tunnel public.
Chaque téléphone est **appairé** par un code QR à usage unique, puis peut être **révoqué** d'un clic.
Invariants : INV-DISTANT-5 à INV-DISTANT-8 (`docs/ARCHITECTURE.md`).

## 1. Tailscale sur le poste et sur le téléphone

1. Poste : Réglages → « Ajouter ce PC comme exécuteur » installe Tailscale (étape du catalogue), ou
   l'installer à la main ; puis `tailscale up` et se connecter.
2. Téléphone : Réglages → Appareils → « Installer Tailscale sur le téléphone » montre un code QR vers
   la page de téléchargement ; installer l'application, se connecter **au même compte**.
3. Noter l'adresse Tailscale du poste : `tailscale ip -4` (de la forme `100.x.y.z`).

À ne jamais faire : `tailscale funnel` (expose sur Internet) ni `tailscale serve` vers le port de
GoldenBrain (les requêtes du téléphone arriveraient par la boucle locale et passeraient pour locales).

## 2. Configuration (`config.toml`)

```toml
[executeurs]
ecoute = "100.x.y.z"     # l'adresse Tailscale du poste — jamais 0.0.0.0

[distant]
appareils = true          # désactivé par défaut
hors_ligne = false      # true : le compagnon peut garder un aperçu léger sur le téléphone
gestes = "interdire"      # ou "confirmer" : arrêt, redémarrage, suppression depuis le téléphone
```

Redémarrer GoldenBrain. Il écoute alors sur `127.0.0.1` **et** sur cette seule adresse.

### HTTPS (recommandé)

Activer « HTTPS certificates » dans la console Tailscale (DNS), puis sur le poste :
`sudo tailscale cert <poste>.<tailnet>.ts.net`. Compléter :

```toml
[distant]
nom_hote = "<poste>.<tailnet>.ts.net"
certificat = "/chemin/<poste>.<tailnet>.ts.net.crt"
cle = "/chemin/<poste>.<tailnet>.ts.net.key"
```

L'adresse distante passe en HTTPS (le cookie de l'appareil devient `Secure`) ; la boucle locale reste
en HTTP. Sans certificat, Réglages → Appareils l'avertit : le trafic reste chiffré par Tailscale, mais
le cookie n'est pas marqué `Secure`. Le certificat expire après 90 jours : relancer `tailscale cert`.
Le HTTPS conditionne aussi l'application installable et l'usage hors ligne : en `http://100.x.y.z`, le
navigateur du téléphone refuse le service worker (script qui gère le hors-ligne) et l'installation.

## 3. Appairer un téléphone

1. Sur le poste : Réglages → Appareils → nom de l'appareil → « Ajouter un téléphone ».
2. Un code QR s'affiche, valable **deux minutes**, utilisable **une fois**.
3. Le téléphone (Tailscale connecté) le scanne avec l'appareil photo : la page d'appairage s'ouvre,
   échange le code contre un jeton d'appareil (cookie), puis ouvre GoldenBrain.

Cinq codes faux d'affilée verrouillent l'appairage une minute.

**Sans passer devant le PC** : dans la discussion Telegram autorisée, écrire `/appairer` (ou `/appairer Tablette` pour nommer l'appareil). Le serveur répond par un code QR et le lien d'appairage (valables 2 min, un seul usage) ; ouvrir le lien sur l'appareil, connecté à Tailscale. Trois demandes au plus par 10 min ; chacune figure au journal (Réglages → Appareils). INV-APPAIRAGE-2.

## 4. Ce que le téléphone peut faire

- **Accueil** (bouton de la barre basse, `#compagnon`) : à décider, en cours, arbre allégé, en lecture seule, sauf « Valider » / « Renvoyer » sur une tâche terminée par son agent (en ligne, après confirmation) ; la PWA installée s'ouvre sur cet Accueil (`start_url` du manifeste), et le raccourci « Décisions » de l'icône mène à `#decisions`.
  Option hors ligne : `[distant] hors_ligne = true` puis case à cocher sur l'appareil ; titres, statuts et
  décisions seulement, 7 jours, effacés à la révocation (INV-PWA-2).
- **Travail en cours** (`#travail`, bouton de l'Accueil) : étoile ★ sur une tâche pour l'épingler sur CE téléphone ; la vue ne liste que les tâches épinglées, chacune ouvre son chat (conversation + envoi d'un message à l'agent, comme `orch dire`). Réglage de l'appareil, rien d'écrit sur le poste (INV-COMPAGNON-2).
- Tout l'usage courant : arbre, tâches, conversations, décisions, notes.
- Réservé au poste : la gestion des appareils, l'installation, les jetons et l'appairage des
  exécuteurs, les terminaux.
- Gestes à risque (arrêt d'un tour, redémarrage, mise à jour, toute suppression) : refusés
  (`gestes = "interdire"`) ou soumis à une confirmation sur le téléphone (`"confirmer"`).

## 5. Révoquer, surveiller

- Réglages → Appareils liste chaque appareil avec sa dernière connexion et son adresse ;
  « Révoquer » coupe l'accès immédiatement, y compris le flux d'événements ouvert.
- Le journal des connexions distantes (même section) montre appairages, connexions, refus et
  révocations.
- Un téléphone perdu : le révoquer, et le retirer aussi du réseau Tailscale (console Tailscale).

## Résumé du résultat (facultatif)

Par défaut, la carte d'une tâche à valider ne montre que son titre et sa question. `[distant] resume = true` y ajoute un résumé de 140 caractères au plus de ce que l'agent déclare avoir fait : ce texte **quitte le poste** (vers le téléphone appairé, par le réseau privé). Il n'est servi qu'en `no-store`, n'entre ni dans le cache du service worker ni dans l'aperçu hors ligne, et l'option est éteinte dans toute instance de test.

## 6. Mise en place pas à pas sur un poste Linux (Debian/Ubuntu)

Chaque commande est lancée **par vous**, dans un terminal. `sudo` demande votre mot de passe à l'écran ;
GoldenBrain ne le voit jamais (INV-INSTALL-2). La connexion au compte Tailscale se fait dans le navigateur,
par vous.

1. **Installer Tailscale** (script officiel, droits administrateur) :
   `curl -fsSL https://tailscale.com/install.sh | sh`
   Alternative sans script : ajouter le dépôt de paquets décrit sur https://tailscale.com/kb/1031/install-linux
   puis `sudo apt-get install -y tailscale`.
2. **Se connecter au réseau privé** : `sudo tailscale up`. Un lien s'affiche : l'ouvrir, se connecter au
   compte Tailscale, accepter. Ne pas ajouter `--shields-up` (il bloquerait les connexions du téléphone) ;
   ne jamais lancer `tailscale funnel` ni `tailscale serve`.
3. **Console Tailscale** (https://login.tailscale.com/admin/dns) : vérifier que MagicDNS est actif, puis
   activer « HTTPS Certificates ».
4. **Relever les deux noms** : `tailscale ip -4` (adresse `100.x.y.z`) et
   `tailscale status --json | python3 -c "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))"`
   (nom `<poste>.<tailnet>.ts.net`).
5. **Obtenir le certificat**, dans un dossier lisible par vous seul :
   `mkdir -p ~/.config/goldenbrain/tls && chmod 700 ~/.config/goldenbrain/tls`
   `sudo tailscale set --operator=$USER` (une fois : permet les commandes suivantes sans `sudo`)
   `tailscale cert --cert-file ~/.config/goldenbrain/tls/poste.crt --key-file ~/.config/goldenbrain/tls/poste.key <poste>.<tailnet>.ts.net`
   `chmod 600 ~/.config/goldenbrain/tls/poste.key`
6. **`config.toml`** (chemins absolus) :
   ```toml
   [executeurs]
   ecoute = "100.x.y.z"
   [distant]
   appareils = true
   nom_hote = "<poste>.<tailnet>.ts.net"
   certificat = "/home/<vous>/.config/goldenbrain/tls/poste.crt"
   cle = "/home/<vous>/.config/goldenbrain/tls/poste.key"
   hors_ligne = false   # true seulement si vous voulez l'aperçu hors ligne
   ```
   Redémarrer GoldenBrain.
7. **Vérifier qu'aucune porte n'est ouverte au monde** : `ss -tlnp | grep 8300` ne doit montrer que
   `127.0.0.1:8300` et `100.x.y.z:8300`, jamais `0.0.0.0` ni `*`. Aucune redirection de port sur la box.
   Depuis le poste : `curl -sk -o /dev/null -w "%{http_code}\n" https://<poste>.<tailnet>.ts.net:8300/api/arbre`
   doit répondre `401` (appareil non appairé).
8. **Téléphone** : installer Tailscale (Play Store), se connecter au même compte ; ouvrir
   `https://<poste>.<tailnet>.ts.net:8300` (refus attendu) ; puis appairer (§ 3) ; enfin, dans Chrome,
   menu ⋮ → « Installer l'application » (disponible grâce au HTTPS).
9. **Renouvellement** : le certificat dure 90 jours ; relancer la commande de l'étape 5 puis redémarrer
   GoldenBrain. Retrait complet : `sudo tailscale down`, retirer les lignes `[distant]`/`[executeurs]`.

## Essai pas à pas

1. Tailscale connecté sur le poste et le téléphone (même compte).
2. `config.toml` : `[executeurs] ecoute` et `[distant] appareils = true` ; redémarrer.
3. Sur le téléphone, ouvrir `http://100.x.y.z:8300` : refus (« appareil non appairé »).
4. Poste : Réglages → Appareils → « Ajouter un téléphone » ; scanner le code QR : l'interface s'ouvre.
5. Poste : « Révoquer » ; recharger sur le téléphone : refus.
