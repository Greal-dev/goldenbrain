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

// --- Barre haute : elle ne déborde jamais de la fenêtre et rien n'y chevauche rien (INV-BARRE-1). Chaque pastille est insécable
// (libellé + compteur d'un bloc, jamais rétrécie) ; quand la rangée est trop large, elle se replie par niveaux cumulatifs, dans cet ordre :
// 1 pastilles secondaires (Aujourd'hui, Décisions, Propositions, Incidents, « dossier à aligner », Infos) en icône + compteur + infobulle ;
// 2 repère « Intelligent » masqué ; 3 pastilles secondaires rangées dans « Menu » ; 4 recherche réduite à une loupe ; 5 pastilles « À moi »
// en icône + compteur + infobulle ; 6 marque en logo seul et « Nouvelle tâche » en « + ». « Menu » reste toujours entier. Les libellés et
// les pastilles reviennent d'eux-mêmes quand la place revient (le calcul repart du niveau 0 ; niveaux posés en `data-r1` … `data-r6`).
// Frontières : DOM seul ; la mise en page des niveaux est dans barre.css (`.b-haut[data-r1…r6]`). Aucune requête.
const MAX = 6;
const SECOND = '#btn-aujourdhui, #btn-decisions, #btn-props, #btn-incidents, #btn-align, #btn-etat';
const A_MOI = '#btn-avalider, #btn-questions, #btn-afaire';

// Une pastille en icône garde son compte ; l'infobulle (title) et l'étiquette d'accessibilité reprennent son libellé.
function libelles(barre, n) {
  const replies = new Set([...(n >= 1 && n < 3 ? barre.querySelectorAll(SECOND) : []), ...(n >= 5 ? barre.querySelectorAll(A_MOI) : [])]);
  for (const b of barre.querySelectorAll(`${SECOND}, ${A_MOI}`)) {
    if (!replies.has(b)) { if (b.dataset.avant !== undefined) { b.title = b.dataset.avant; delete b.dataset.avant; } b.removeAttribute('aria-label'); continue; }
    const lib = b.querySelector(':scope > span:not(.n)')?.textContent.trim();
    if (!lib || b.dataset.avant !== undefined) continue;
    b.dataset.avant = b.title;
    b.title = b.title ? `${lib} — ${b.title}` : lib;
    b.setAttribute('aria-label', `${lib} ${b.querySelector('.n')?.textContent ?? ''}`.trim());
  }
}

// Niveau 3 : les pastilles secondaires passent dans « Menu » (un repère les ramène à leur place), niveaux inférieurs : elles reviennent.
function ranger(barre, dans) {
  const menu = barre.querySelector('#b-menu');
  const rels = [...new Set([...barre.querySelectorAll(SECOND)].map((b) => b.closest('.rel')).filter(Boolean))];
  if (!menu) return;
  if (dans) {
    for (const rel of rels) if (!rel._repere) { rel._repere = document.createComment('rel'); rel.before(rel._repere); rel.classList.add('en-menu'); }
    menu.prepend(...rels);
  } else for (const rel of rels) if (rel._repere) { rel._repere.replaceWith(rel); rel._repere = null; rel.classList.remove('en-menu'); }
}

// Trop large : le contenu dépasse la barre, un élément sort de la fenêtre, ou deux éléments de la rangée se recouvrent.
function deborde(barre) {
  const fenetre = document.documentElement.clientWidth;
  if (barre.scrollWidth > barre.clientWidth || barre.getBoundingClientRect().right > fenetre) return true;
  const rangee = [...barre.querySelectorAll(':scope > :not(.rel, .b-menu-zone, .rech-zone), :scope > .rel > button, .b-menu-zone button, .b-menu > .rel > button, .rech-zone > input')]
    .map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
  return rangee.some((a, i) => a.right > fenetre + 0.5 || a.left < -0.5 || rangee.slice(i + 1).some((b) =>
    a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
}

export function ajuster() {
  const barre = $('.b-haut');
  if (!barre) return;
  const niveau = (n) => { for (let k = 1; k <= MAX; k++) barre.toggleAttribute(`data-r${k}`, k <= n); ranger(barre, n >= 3); };
  niveau(0);
  libelles(barre, 0);
  let n = 0;
  while (deborde(barre) && n < MAX) niveau(++n);
  libelles(barre, n);
}

export function initBarre() {
  const barre = $('.b-haut');
  let attente = 0;
  const planifier = () => { cancelAnimationFrame(attente); attente = requestAnimationFrame(() => { ajuster(); observateurs.slice(1).forEach((o) => o.takeRecords()); }); };
  const observateurs = [new ResizeObserver(planifier),
    new MutationObserver(planifier), new MutationObserver(planifier)];
  observateurs[0].observe(barre);
  observateurs[1].observe(barre, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['hidden'] });
  observateurs[2].observe(document.body, { attributes: true, attributeFilter: ['class'] });
  addEventListener('resize', planifier);
  // Recherche ouverte (focus) : elle reprend sa largeur, le reste se replie en conséquence.
  barre.addEventListener('focusin', (e) => { if (e.target.id === 'recherche') { barre.dataset.focus = '1'; planifier(); } });
  barre.addEventListener('focusout', (e) => { if (e.target.id === 'recherche') { delete barre.dataset.focus; planifier(); } });
  document.fonts?.ready.then(planifier);
  planifier();
}
