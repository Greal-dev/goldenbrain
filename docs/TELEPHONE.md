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

## 4. Ce que le téléphone peut faire

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

## Essai pas à pas

1. Tailscale connecté sur le poste et le téléphone (même compte).
2. `config.toml` : `[executeurs] ecoute` et `[distant] appareils = true` ; redémarrer.
3. Sur le téléphone, ouvrir `http://100.x.y.z:8300` : refus (« appareil non appairé »).
4. Poste : Réglages → Appareils → « Ajouter un téléphone » ; scanner le code QR : l'interface s'ouvre.
5. Poste : « Révoquer » ; recharger sur le téléphone : refus.
