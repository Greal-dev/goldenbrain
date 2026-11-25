// Rôle : volet gauche — arbre repliable, filtres, clavier, glisser-déposer.
// Frontières : lit S.arbre ; les déplacements passent par l'API puis demandent un rechargement.
import { t, tn } from './langues.js';
import { h, $, remplacer, ajouter, nomLisible } from './dom.js';
import { S, on, emit, ouvrir, ouvrirVue, fixerToutes, chemin, cleNoeud } from './store.js';
import { brancher, actionsLigne } from './glisser.js';
import { repereIA, compteIA, surOccupees } from './verrou.js';
import { rendreChangeable } from './statut.js';
import { pastilleMoi } from './executant.js';
import { pastilleNature, compteLignes } from './lignes.js';
import { pastilleRetard } from './integration.js';
import { appliquer, actif as filtreActif, badgeStatut, libelleCourt, compteur, initFiltres } from './filtres.js';

const CLE = 'orch.arbre.ouverts';
let ouverts = (() => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch { return {}; } })();
let visibles = [];
let cleFocus = null;
let cont;

const cle = cleNoeud;
const norm = (s) => (s || '').normalize('NFD').replace(/\p{M}/g, '').toLowerCase();
const forcer = () => filtreActif() || !!S.recherche.trim();
const estOuvert = (n) => forcer() || (cle(n) in ouverts ? ouverts[cle(n)] : n.type === 'casquette' || n.type === 'operation' || n.type === 'groupe');

function filtrer(ns, match, complet) {
  const r = [];
  for (const n of ns) {
    if (complet && match(n)) { r.push(n); continue; }
    const enf = filtrer(n.enfants || [], match, complet);
    if (enf.length || (match(n) && n.type === 'tache')) r.push({ ...n, enfants: enf });
  }
  return r;
}
function arbreFiltre() {
  let a = appliquer(S.arbre);
  const q = norm(S.recherche.trim());
  if (q) a = filtrer(a, (n) => norm(n.titre).includes(q), true);
  return a;
}
function aplatir(ns, niveau, out) {
  for (const n of ns) {
    out.push({ n, niveau });
    if ((n.enfants || []).length && estOuvert(n)) aplatir(n.enfants, niveau + 1, out);
  }
  return out;
}
const compterTaches = (ns) => ns.reduce((k, n) => k + (n.type === 'tache' ? 1 : 0) + compterTaches(n.enfants || []), 0);
const sauver = () => localStorage.setItem(CLE, JSON.stringify(ouverts));

function indicateur(n) {
  if (n.etat_execution === 'en_cours') return h('span', { class: 'tourne', title: t('arbre.seance_titre') });
  if (n.etat_execution === 'en_file') return h('span', { class: 'file', title: t('arbre.file_titre') });
  if (n.etat_execution === 'interrompu') return h('span', { class: 'interrompu', title: t(n.reprise_auto ? 'arbre.reprise_auto_titre' : 'arbre.interrompu_titre') }, '!');
  if (n.etat_execution === 'en_pause') return h('span', { class: 'echec', title: S.etat.pauses?.[n.id] || t('arbre.pause_titre') }, '⏸');
  if (n.echec) return h('span', { class: 'echec', title: t('arbre.echec_titre', { motif: n.echec }) }, '!');
  return null;
}

function ligne({ n, niveau }) {
  const enfants = (n.enfants || []).length > 0;
  const ouvert = enfants && estOuvert(n);
  const k = cle(n);
  const sel = n.type === 'tache' ? n.id === S.selection : (!S.selection && S.vue === 'cascade' && S.portee === k);
  const nl = n.type === 'tache' ? n.liens || 0 : 0;
  const lib = tn('arbre.liens', nl);
  const etiquette = n.type === 'tache' ? (nl ? t('arbre.etiquette_tache_liens', { titre: n.titre, statut: libelleCourt(n), liens: lib }) : t('arbre.etiquette_tache', { titre: n.titre, statut: libelleCourt(n) }))
    : n.type === 'conteneur' ? t(n.logique ? 'arbre.etiquette_projet_logique' : 'arbre.etiquette_projet', { titre: n.titre }) : n.titre;
  return h('div', {
    class: `ligne t-${n.type}${sel ? ' sel' : ''}${k === S.marque ? ' marque' : ''}`, role: 'treeitem', 'data-cle': k, 'data-niveau': niveau,
    'aria-level': niveau + 1, 'aria-selected': sel ? 'true' : 'false', 'aria-expanded': enfants ? String(ouvert) : null,
    'aria-label': etiquette, tabindex: k === cleFocus ? '0' : '-1', style: `padding-left:${6 + niveau * 14}px`,
    draggable: n.deplacable ? 'true' : null,
  },
  h('span', { class: `chev${enfants ? (ouvert ? ' ouvert' : '') : ' vide'}`, 'aria-hidden': 'true' }),
  n.type === 'tache' ? (n.routine ? badgeStatut(n) : rendreChangeable(badgeStatut(n), n)) : null, // la pastille d'une routine montre son échéance, pas un statut
  n.type === 'conteneur' ? h('span', { class: 'ico-projet', 'aria-hidden': 'true', title: t('arbre.projet') }) : null,
  h('span', { class: 'titre', title: nomLisible(n.titre) }, nomLisible(n.titre)),
  n.type === 'tache' ? pastilleRetard(n) : null,
  nl ? h('span', { class: 'repere-liens', title: lib, 'aria-hidden': 'true' }, '⇄') : null,
  // INV-ARBRE-2 : placé par sa clé parent:, pas par son dossier (écart à aligner, ou dossier non déplaçable).
  n.logique ? h('span', { class: 'repere-liens', title: t('arbre.logique_titre') }, '⛓') : null,
  indicateur(n),
  n.type === 'tache' ? repereIA(n.id) : null,
  n.type === 'tache' ? pastilleMoi(n) : null, // INV-EXECUTANT-1
  n.type === 'tache' ? pastilleNature(n) : null, // INV-NATURE-1
  n.type === 'tache' ? compteLignes(n) : null, // INV-LIGNES-1
  compteIA(n),
  (enfants || n.type !== 'tache') && n.ouvertes > 0 ? h('span', { class: 'compte', title: t('arbre.ouvertes_titre', { n: n.ouvertes }) }, n.ouvertes) : null,
  n.type === 'groupe' ? null : actionsLigne(n));
}

export function dessiner() {
  const top = cont.scrollTop;
  const actif = cont.contains(document.activeElement) ? document.activeElement.dataset.cle : null;
  const vu = arbreFiltre();
  compteur(compterTaches(vu));
  visibles = aplatir(vu, 0, []);
  if (!visibles.some((v) => cle(v.n) === cleFocus)) {
    cleFocus = (visibles.find((v) => v.n.type === 'tache' && v.n.id === S.selection) || visibles[0])?.n;
    cleFocus = cleFocus ? cle(cleFocus) : null;
  }
  remplacer(cont, visibles.map(ligne));
  if (!visibles.length) ajouter(cont, h('p', { class: 'vide' }, S.recherche || filtreActif() ? t('arbre.aucun_resultat') : t('arbre.aucune_tache')));
  cont.scrollTop = top;
  if (actif) cont.querySelector(`[data-cle="${CSS.escape(actif)}"]`)?.focus({ preventScroll: true });
  $('#arbre-titre').textContent = S.filtreAMoi ? t('arbre.titre_a_moi') : S.toutes ? t('arbre.titre_toutes') : t('arbre.titre_ouvertes');
  $('#chip-filtre').hidden = !S.filtreAMoi;
}

function basculer(n) {
  if (forcer()) return;
  ouverts[cle(n)] = !estOuvert(n);
  sauver();
  dessiner();
}
function noeudDe(el) { const v = visibles.find((x) => cle(x.n) === el?.dataset.cle); return v?.n; }

function reveler(k, focus = false) {
  const c = chemin(S.arbre, (n) => cle(n) === k);
  if (!c) return;
  c.slice(0, -1).forEach((n) => { ouverts[cle(n)] = true; });
  sauver();
  cleFocus = k;
  dessiner();
  const row = cont.querySelector(`[data-cle="${CSS.escape(k)}"]`);
  row?.scrollIntoView({ block: 'nearest' });
  if (focus) row?.focus({ preventScroll: true });
}

function surTouche(e) {
  const rows = [...cont.querySelectorAll('.ligne')];
  const i = rows.indexOf(document.activeElement);
  if (i < 0) return;
  const n = noeudDe(rows[i]);
  const niv = +rows[i].dataset.niveau;
  const aller = (j) => { if (rows[j]) { rows[j].focus(); e.preventDefault(); } };
  switch (e.key) {
    case 'ArrowDown': return aller(i + 1);
    case 'ArrowUp': return aller(i - 1);
    case 'Home': return aller(0);
    case 'End': return aller(rows.length - 1);
    case 'ArrowRight':
      e.preventDefault();
      if (n.enfants?.length && !estOuvert(n)) basculer(n); else if (n.enfants?.length) rows[i + 1]?.focus();
      return;
    case 'ArrowLeft':
      e.preventDefault();
      if (n.enfants?.length && estOuvert(n) && !forcer()) basculer(n);
      else for (let j = i - 1; j >= 0; j--) if (+rows[j].dataset.niveau < niv) { rows[j].focus(); break; }
      return;
    case 'Enter': case ' ':
      e.preventDefault();
      if (n.type === 'tache') ouvrir(n.id); else if (e.key === 'Enter' && n.type !== 'groupe') ouvrirVue('cascade', cle(n)); else basculer(n);
  }
}

export function initArbre() {
  cont = $('#arbre');
  cont.addEventListener('keydown', surTouche);
  cont.addEventListener('focusin', (e) => {
    const k = e.target.dataset?.cle;
    if (!k || k === cleFocus) return;
    cont.querySelector('.ligne[tabindex="0"]')?.setAttribute('tabindex', '-1');
    e.target.setAttribute('tabindex', '0');
    cleFocus = k;
  });
  cont.addEventListener('click', (e) => {
    const row = e.target.closest('.ligne');
    const n = noeudDe(row);
    if (!n || e.target.closest('.st-chg, .st-refus')) return;
    cleFocus = cle(n);
    if (e.target.classList.contains('chev')) basculer(n); else if (n.type === 'tache') ouvrir(n.id); else if (n.type === 'groupe') basculer(n); else ouvrirVue('cascade', cle(n));
    row.focus?.();
  });
  brancher(cont, cont);

  for (const [id, val] of [['#vue-ouvertes', false], ['#vue-toutes', true]]) $(id).addEventListener('click', () => fixerToutes(val));
  on('toutes', majBascule);
  $('#chip-filtre').addEventListener('click', () => { S.filtreAMoi = false; emit('filtre'); });
  on('arbre', dessiner);
  surOccupees(dessiner);
  on('filtre', () => { dessiner(); });
  on('selection', (id) => { if (id) reveler(`tache:${id}`); else if (S.portee) reveler(S.portee); else dessiner(); });
  on('deplier', (k) => { ouverts[k] = true; sauver(); dessiner(); });
  on('deplace', ({ cle: k, depuis }) => reveler(k, depuis === cont));
  initFiltres();
  majBascule();
}
export function majBascule() {
  // Bascule partagée : le volet gauche et l'en-tête de la cascade portent les mêmes boutons [data-vue].
  document.querySelectorAll('[data-vue="ouvertes"]').forEach((b) => b.setAttribute('aria-pressed', String(!S.toutes)));
  document.querySelectorAll('[data-vue="toutes"]').forEach((b) => b.setAttribute('aria-pressed', String(S.toutes)));
}
export function focaliser() { (cont.querySelector('.ligne[tabindex="0"]') || cont.querySelector('.ligne'))?.focus(); }
