// Rôle : état « interface » (mode simple / avancé, familles débrayées, politique des propositions) et ses applications à l'écran.
// Frontières : GET/PUT /api/interface seulement ; le serveur reste maître (INV-INTERFACE-1 : une famille fermée répond 409),
// ces fonctions évitent les appels voués à l'échec et masquent ce qui n'a plus lieu d'être. Aucun HTML (INV-WEB-1).
import { S, emit } from './store.js';
import { api } from './api.js';
import { $, reglerRetour } from './dom.js';
import { t, etatInterfaceInitial } from './langues.js';

export const FAMILLES = ['equipe', 'liens', 'alignement', 'jardinage', 'moteurs', 'notes', 'transformations', 'conseil'];

// Tant que l'état n'est pas lu (ou si la lecture échoue), tout est ouvert : le serveur tranche par 409.
export const ouvert = (f) => S.interface?.familles?.[f] !== false;
export const simple = () => S.interface?.mode === 'simple';
export const montrerPropositions = () => (S.interface?.propositions ?? 'montrer') === 'montrer';

// En simple, « conteneur » et « opération » se disent « projet » (un seul vocabulaire : projet, tâche).
export const mot = (type) => (type === 'tache' ? t('interface.mot_tache') : type === 'casquette' ? t('interface.mot_casquette')
  : simple() ? t('interface.mot_projet') : type === 'operation' ? t('interface.mot_operation') : t('interface.mot_projet'));

// En simple, les opérations disparaissent de l'arbre affiché : leurs enfants remontent au niveau de la casquette.
export function sansOperations(noeuds) {
  if (!simple()) return noeuds;
  return noeuds.flatMap((n) => (n.type === 'operation' ? sansOperations(n.enfants || [])
    : [n.enfants ? { ...n, enfants: sansOperations(n.enfants) } : n]));
}
S.vueArbre = (n) => sansOperations(n);
export const filVisible = (fil) => (simple() ? fil.filter((s) => s.type !== 'operation') : fil);

// Classes sur <body> : le CSS fait le reste (`.sans-<famille> .f-<famille> { display: none }`).
function poser() {
  const c = document.body.classList;
  c.toggle('mode-simple', simple());
  c.toggle('mode-avance', !simple());
  for (const f of FAMILLES) c.toggle(`sans-${f}`, !ouvert(f));
  c.toggle('sans-propositions', !montrerPropositions());
  document.getElementById('arbre')?.setAttribute('aria-label', simple() ? t('interface.arbre_simple') : t('interface.arbre_avance'));
}

function adopter(etat) {
  if (!etat || JSON.stringify(etat) === JSON.stringify(S.interface)) return false;
  reglerRetour(etat.statut_retour);  // INV-STATUT-1
  S.interface = etat;
  S.invaliderArbre();
  poser();
  emit('interface', etat);
  return true;
}

export async function chargerInterface() { adopter(etatInterfaceInitial() || await api('/interface')); }
export async function changerInterface(corps) { adopter(await api('/interface', { methode: 'PUT', corps })); }

// --- Barre haute : la barre haute ne déborde jamais de la fenêtre (INV-BARRE-1). Quand elle est trop large, elle se replie par niveaux
// successifs, dans un ordre fixe : 1 pastilles secondaires en icône + nombre ; 2 pastilles « À moi » en icône + nombre ;
// 3 repère « Intelligent » masqué ; 4 recherche resserrée ; 5 marque en logo seul et « Nouvelle tâche » en « + » ; 6 pastilles
// secondaires masquées. « Nouvelle tâche » et « Menu » restent toujours visibles. Les libellés complets reviennent d'eux-mêmes
// quand la place revient (le calcul repart du niveau 0 à chaque changement ; niveaux cumulatifs posés en attributs `data-r1` … `data-r6`).
// Frontières : DOM seul ; la mise en page des niveaux est dans barre.css (`.b-haut[data-r1…r6]`). Aucune requête.
const MAX = 6;
// Pastilles repliables en icône : elles gardent leur compte ; l'infobulle (title) reprend leur libellé.
const PASTILLES = '#btn-aujourdhui, #btn-decisions, #btn-avalider, #btn-questions, #btn-afaire, #btn-props, #btn-incidents, #btn-etat, #btn-travaux';

function libelles(barre, replie) {
  for (const b of barre.querySelectorAll(PASTILLES)) {
    if (!replie) { if (b.dataset.avant !== undefined) { b.title = b.dataset.avant; delete b.dataset.avant; } b.removeAttribute('aria-label'); continue; }
    const lib = b.querySelector(':scope > span:not(.n)')?.textContent.trim();
    if (!lib || b.dataset.avant !== undefined) continue;
    b.dataset.avant = b.title;
    b.title = b.title ? `${lib} — ${b.title}` : lib;
    b.setAttribute('aria-label', `${lib} ${b.querySelector('.n')?.textContent ?? ''}`.trim());
  }
}

// Trop large : le contenu dépasse la barre, ou un élément de la rangée dépasse la fenêtre (la barre peut elle-même être plus large qu'elle).
function deborde(barre) {
  const fenetre = document.documentElement.clientWidth;
  if (barre.scrollWidth > barre.clientWidth || barre.getBoundingClientRect().right > fenetre) return true;
  return [...barre.querySelectorAll(':scope > *, :scope > .rel > button, :scope > .b-menu-zone > button')].some((e) => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && (r.right > fenetre + 0.5 || r.left < -0.5);
  });
}

export function ajuster() {
  const barre = $('.b-haut');
  if (!barre) return;
  const niveau = (n) => { for (let k = 1; k <= MAX; k++) barre.toggleAttribute(`data-r${k}`, k <= n); };
  niveau(0);
  libelles(barre, false);
  let n = 0;
  while (deborde(barre) && n < MAX) niveau(++n);
  if (n) libelles(barre, true);
}

export function initBarre() {
  const barre = $('.b-haut');
  let attente = 0;
  const planifier = () => { cancelAnimationFrame(attente); attente = requestAnimationFrame(ajuster); };
  new ResizeObserver(planifier).observe(barre);
  new MutationObserver(planifier).observe(barre, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['hidden'] });
  new MutationObserver(planifier).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  addEventListener('resize', planifier);
  document.fonts?.ready.then(planifier);
  planifier();
}
