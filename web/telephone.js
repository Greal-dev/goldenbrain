// Rôle : usage au téléphone — barre basse (Tâches, Décisions, Recherche, Réglages), un seul écran à la fois
//        (liste ou détail, `body[data-ecran]`), manifeste et service worker de l'application installable.
// Frontières : navigue seulement par store.js (ouvrir, ouvrirVue) ; la mise en page vit dans telephone.css (≤ 480 px),
//        sans effet visible au-delà. INV-PWA-1 : le cache du service worker est l'affaire de sw.js seul.
import { S, on, ouvrir, ouvrirVue } from './store.js';
import { $ } from './dom.js';

// Écran « liste » = l'arbre ; tout le reste (tâche, projet, Décisions, Réglages, note, résultats) occupe l'écran entier.
const ecran = () => (S.selection || S.vue !== 'cascade' || S.portee ? 'detail' : 'liste');
const ACTIONS = {
  taches: () => ouvrir(null),
  decisions: () => ouvrirVue('decisions'),
  recherche: () => $('#recherche').focus(), // les résultats se déroulent sous le champ, au-dessus de l'écran courant
  reglages: () => ouvrirVue('reglages'),
};

function maj() {
  const e = ecran();
  document.body.dataset.ecran = e;
  const courant = S.selection ? null : e === 'liste' ? 'taches' : S.vue in ACTIONS ? S.vue : null;
  for (const b of document.querySelectorAll('#barre-basse [data-tel]')) {
    if (b.dataset.tel === courant) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
}

// Manifeste et service worker attendent le premier arbre affiché : liés dans la page, le manifeste et ses icônes
// retardaient l'arbre de ~370 ms en 4G lente (mesure 18/11).
let installe = false;
function installable() {
  if (installe) return;
  installe = true;
  document.head.append(Object.assign(document.createElement('link'), { rel: 'manifest', href: 'manifest.json', crossOrigin: 'use-credentials' }));
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => { /* hors contexte sécurisé ou refus : l'interface marche sans */ });
}

export function initTelephone() {
  const barre = $('#barre-basse');
  barre.addEventListener('click', (e) => { const b = e.target.closest('[data-tel]'); if (b) ACTIONS[b.dataset.tel](); });
  // Le compte des décisions suit celui du bandeau, qui reste la seule source (bandeau.js).
  const n = $('#n-decisions'), copie = $('#n-decisions-bas');
  const recopier = () => { copie.textContent = n.textContent; copie.hidden = !n.textContent || n.textContent === '0'; };
  new MutationObserver(recopier).observe(n, { childList: true, characterData: true, subtree: true });
  recopier();
  // La barre basse s'efface pendant la saisie (telephone.css) : sans ceci, toucher « Envoyer » ôterait le focus,
  // la barre reviendrait et décalerait le bouton sous le doigt avant le clic.
  document.addEventListener('mousedown', (e) => { if (e.target.closest('.composer button, .dc-reponse button')) e.preventDefault(); });
  on('selection', maj);
  maj();
  on('arbre', () => setTimeout(installable));
}
