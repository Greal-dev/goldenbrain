// Rôle : service worker de l'application installable (enregistré par telephone.js, portée /).
// Frontières : ne répond qu'aux GET de fichiers statiques de la même origine ; tout le reste (API, flux d'événements,
//        pages d'autres modules) passe au réseau sans qu'il s'en mêle.
// INV-PWA-1 : aucune donnée de l'API n'entre dans le cache ; réseau d'abord, le cache ne sert que hors ligne,
//        donc une nouvelle version s'applique au premier chargement en ligne, sans rester bloqué sur l'ancienne.
const CACHE = 'gb-statique-2';
const STATIQUE = /(?:\/|\.(?:html|js|css|svg|png|json))$/;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(
  caches.keys().then((cles) => Promise.all(cles.filter((c) => c !== CACHE).map((c) => caches.delete(c)))).then(() => self.clients.claim())));

self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin || u.pathname.startsWith('/api/') || !STATIQUE.test(u.pathname)) return;
  // Réseau d'abord, mais une connexion qui rame ne bloque pas l'appareil : après 3 s, repli sur le cache s'il a la page.
  const repli = () => caches.match(e.request, { ignoreSearch: true });
  const lent = new Promise((ok) => setTimeout(() => repli().then(ok), 3000)).then((r) => r || new Promise(() => {}));
  e.respondWith(Promise.race([fetch(e.request), lent]).then((r) => {
    if (r.ok) { const copie = r.clone(); e.waitUntil(caches.open(CACHE).then((c) => c.put(e.request, copie))); }
    return r;
  }).catch(() => repli().then((r) => r || Response.error())));
});
