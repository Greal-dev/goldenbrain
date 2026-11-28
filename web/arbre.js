// Rôle : volet gauche — arbre repliable, filtres, clavier, glisser-déposer.
// Pied de liste : « ＋ Nouveau projet » (casquette, projet) et « ＋ Nouvelle tâche » (projet, tâche-groupe), INV-ARBRE-3.
// Frontières : lit S.arbre (plus les projets neufs encore vides) ; les déplacements et créations passent par l'API, appelée au clic
// seulement (aucune requête au premier affichage) ; la tâche passe par le dialogue « Nouvelle tâche » (bandeau.js, évènement `nouvelle`).
// Invariants portés : INV-ARBRE-2, INV-ARBRE-3.
import { t, tn } from './langues.js';
import { h, $, remplacer, ajouter, nomLisible } from './dom.js';
import { S, on, emit, ouvrir, ouvrirVue, fixerToutes, chemin, cleNoeud, erreur, parcourir } from './store.js';
import { brancher, actionsLigne } from './glisser.js';
import { repereIA, compteIA, surOccupees } from './verrou.js';
import { rendreChangeable } from './statut.js';
import { pastilleMoi } from './executant.js';
import { pastilleNature, compteLignes } from './lignes.js';
import { pastilleRetard } from './integration.js';
import { appliquer, actif as filtreActif, badgeStatut, libelleCourt, compteur, initFiltres } from './filtres.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';

// Les deux premières étiquettes en puces, le reste en « +n » : arbre et listes.
function puces(mots, max = 2) {
  if (!mots?.length) return null;
  const reste = mots.slice(max);
  return h('span', { class: 'etiq-puces' }, mots.slice(0, max).map((m) => h('span', { class: 'etiq', 'data-etiquette': m, title: t('vue_etiquette.puce_titre', { mot: m }) }, `#${m}`)),
    reste.length ? h('span', { class: 'etiq plus', title: reste.map((m) => `#${m}`).join(' ') }, `+${reste.length}`) : null);
}

const CLE = 'orch.arbre.ouverts';
let ouverts = (() => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch { return {}; } })();
let visibles = [];
const peres = new Map(); // clé d'un nœud → clé de la liste qui le porte (null : casquette)
let liste = null; // INV-ARBRE-3 : liste survolée ou focalisée, dont le pied se montre
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
  let a = appliquer(greffer(S.arbre));
  const q = norm(S.recherche.trim());
  if (q) a = filtrer(a, (n) => norm(`${n.titre} ${(n.etiquettes || []).map((m) => `#${m}`).join(' ')}`).includes(q), true);
  return a;
}
// INV-ARBRE-3 : le pied d'une liste est une ligne à part (`pied`), hors des nœuds (navigation, compteurs, glisser).
function aplatir(ns, niveau, out, pere = null) {
  for (const n of ns) {
    out.push({ n, niveau });
    peres.set(cle(n), pere);
    if ((n.enfants || []).length && estOuvert(n)) {
      aplatir(n.enfants, niveau + 1, out, cle(n));
      if (!forcer()) out.push({ n, niveau: niveau + 1, pied: true }); // filtre ou recherche : pas de pied
    }
  }
  return out;
}
function montrerPied(el) {
  const p = el?.closest?.('.pied');
  const r = el?.closest?.('.ligne');
  const k = p ? p.dataset.pour : r ? (peres.get(r.dataset.cle) ?? r.dataset.cle) : null;
  if (k === liste) return;
  liste = k;
  cont.querySelector('.pied.vu')?.classList.remove('vu');
  if (k) cont.querySelector(`.pied[data-pour="${CSS.escape(k)}"]`)?.classList.add('vu');
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
  n.type === 'tache' ? puces(n.etiquettes) : null, // INV-ETIQUETTE-1 : les deux premières, le reste en « +n »
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

const GESTES = { casquette: ['projet'], conteneur: ['projet', 'tache'], tache: ['tache'] };
const neufs = new Map(); // clé du parent → projets créés ici, vides donc absents de l'arbre du serveur

// INV-ARBRE-3 : l'arbre du serveur omet un conteneur sans tâche ; le projet neuf reste visible jusqu'à sa première tâche.
function greffer(arbre) {
  if (!neufs.size) return arbre;
  const vus = new Set([...parcourir(arbre)].map(cleNoeud));
  for (const [k, l] of neufs) {
    const reste = l.filter((n) => !vus.has(cleNoeud(n)));
    if (reste.length) neufs.set(k, reste); else neufs.delete(k);
  }
  const g = (ns) => ns.map((n) => {
    const plus = neufs.get(cleNoeud(n));
    return plus || n.enfants?.length ? { ...n, enfants: [...g(n.enfants || []), ...(plus || [])] } : n;
  });
  return g(arbre);
}

const estNeuf = (n) => !!n?.neuf;

function pied(n, niveau, vu) {
  const gestes = GESTES[n.type];
  if (!gestes || n.neuf) return null;
  return h('div', { class: `pied${vu ? ' vu' : ''}`, 'data-pour': cleNoeud(n), style: `padding-left:${26 + niveau * 14}px` },
    gestes.map((g) => h('button', { type: 'button', class: 'btn-pied', 'data-ajout': g,
      onclick: () => (g === 'projet' ? nouveauProjet(n) : nouvelleTache(n)) }, t(`arbre.ajout_${g}`))));
}

function nouvelleTache(n) {
  emit('nouvelle', n.type === 'tache' ? { parent: { id: n.id, titre: nomLisible(n.titre) } } : { conteneur: n.id });
}

// Où naît un projet de casquette : là où vivent déjà ses voisins. Rend le corps `{dans, prefixe?}` de POST /conteneurs.
// ponytail: dossier le plus fréquent ; sans aucun projet nulle part, le dossier propre de la casquette s'il est un conteneur.
async function lieuCasquette(n) {
  const code = n.id.replace(/^casquette:/, '');
  const conts = await api('/conteneurs');
  const ids = new Set(conts.map((c) => c.id));
  const siens = conts.filter((c) => c.casquette === code);
  const plus = (m) => [...m].sort((x, y) => y[1] - x[1])[0]?.[0];
  const sous = new Map(), racine = new Map();
  for (const c of siens) {
    const s = c.id.split('/');
    const d = s.slice(0, 2).join('/');
    if (s.length > 2 && !ids.has(d)) sous.set(d, (sous.get(d) || 0) + 1); // « Casquettes/<dossier non-conteneur>/<projet> »
    else if (s.length === 2 && !c.id.startsWith('Casquettes/') && s[1].startsWith(`${code}-`) && !ids.has(s[0])) racine.set(s[0], (racine.get(s[0]) || 0) + 1); // « Projets/C5-<projet> »
  }
  if (plus(sous)) return { dans: plus(sous) };
  if (plus(racine)) return { dans: plus(racine), prefixe: code };
  const propre = siens.find((c) => c.id.split('/').length === 2 && c.id.startsWith('Casquettes/'))?.id;
  if (!propre) throw new Error(t('arbre.casquette_sans_dossier'));
  return { dans: propre };
}

async function nouveauProjet(n) {
  const v = await formulaire({ titre: t('arbre.projet_titre', { lieu: nomLisible(n.titre) }), valider: t('bandeau.creer'),
    champs: [{ nom: 'nom', label: t('bandeau.groupe_nom'), requis: true }] });
  const nom = v?.nom.trim();
  if (!nom) return;
  try {
    const { id } = await post('/conteneurs', { nom, ...(n.type === 'casquette' ? await lieuCasquette(n) : { dans: n.id }) });
    const k = cleNoeud(n);
    neufs.set(k, [...(neufs.get(k) || []), { id, type: 'conteneur', titre: nom, enfants: [], ouvertes: 0, neuf: true }]);
    emit('deplier', k);
  } catch (e) { erreur(e.message); }
}

export function dessiner() {
  const top = cont.scrollTop;
  const actif = cont.contains(document.activeElement) ? document.activeElement.dataset.cle : null;
  const vu = arbreFiltre();
  compteur(compterTaches(vu));
  peres.clear();
  const rangs = aplatir(vu, 0, []);
  visibles = rangs.filter((r) => !r.pied);
  if (!visibles.some((v) => cle(v.n) === cleFocus)) {
    cleFocus = (visibles.find((v) => v.n.type === 'tache' && v.n.id === S.selection) || visibles[0])?.n;
    cleFocus = cleFocus ? cle(cleFocus) : null;
  }
  remplacer(cont, rangs.map((r) => (r.pied ? pied(r.n, r.niveau, cle(r.n) === liste) : ligne(r))));
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
      if (estNeuf(n)) nouvelleTache(n); else if (n.type === 'tache') ouvrir(n.id); else if (e.key === 'Enter' && n.mot) ouvrirVue('etiquette', n.mot); else if (e.key === 'Enter' && n.type !== 'groupe') ouvrirVue('cascade', cle(n)); else basculer(n);
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
  cont.addEventListener('focusin', (e) => montrerPied(e.target));
  cont.addEventListener('mouseover', (e) => { if (!e.buttons) montrerPied(e.target); }); // bouton enfoncé : un glisser, la mise en page ne bouge pas
  cont.addEventListener('mouseleave', () => montrerPied(cont.contains(document.activeElement) ? document.activeElement : null));
  cont.addEventListener('click', (e) => {
    const row = e.target.closest('.ligne');
    const n = noeudDe(row);
    if (!n || e.target.closest('.st-chg, .st-refus')) return;
    cleFocus = cle(n);
    const puce = e.target.closest('.etiq[data-etiquette]'); // INV-ETIQUETTE-4 : clic sur une puce = vue de l'étiquette
    if (puce) { ouvrirVue('etiquette', puce.dataset.etiquette); return; }
    if (estNeuf(n)) nouvelleTache(n); else if (e.target.classList.contains('chev')) basculer(n); else if (n.type === 'tache') ouvrir(n.id); else if (n.mot) ouvrirVue('etiquette', n.mot); else if (n.type === 'groupe') basculer(n); else ouvrirVue('cascade', cle(n));
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
