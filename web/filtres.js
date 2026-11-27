// Rôle : filtres, regroupement et tri de l'arbre des tâches (vue de base), dans un déroulant (INV-DEROULANT-1) + libellé court du statut.
// Frontières : calcul pur sur S.arbre (jamais d'écriture, pas d'API) ; l'état est gardé dans le navigateur
// (localStorage). Le classement de l'ordonnancement (INV-ORDO-2) porte sur des tours en file, pas sur
// l'arbre : ici, priorité puis échéance, comme son premier critère, sans le dupliquer.
import { libelleMain, infoMain } from './main.js';
import { t, tn, LOCALE } from './langues.js';
import { h, $, remplacer, pourMoi, groupeStatut, RETOUR } from './dom.js';
import { S, on, emit, cleNoeud, parcourir } from './store.js';
import { rangPriorite, libellePriorite, ecartJours } from './temps.js';
import { NATURES, libelleNature } from './lignes.js';
import { badgeRoutine, libelleRoutine } from './routines.js';
import { deroulant } from './deroulant.js';

const CLE = 'orch.filtres';
const VIDE = { statuts: [], priorite: '', echeance: '', portee: '', harnais: '', executant: '', nature: '', etiquette: '', ia: false, routines: false, amoi: false, groupe: '', tri: 'arbre' };
let F = { ...VIDE, ...(() => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch { return {}; } })() };
F.statuts = Array.isArray(F.statuts) ? F.statuts : [];
// Lien partageable : ?st=a-faire,bloque l'emporte sur la mémoire du poste (volet et vue principale partagent cet état).
const deLien = new URLSearchParams(location.search).get('st');
if (deLien !== null) F.statuts = deLien.split(',').filter(Boolean);
S.filtreAMoi = !!F.amoi;
function sauver() {
  F.amoi = S.filtreAMoi;
  localStorage.setItem(CLE, JSON.stringify(F));
  const u = new URL(location.href);
  if (F.statuts.length) u.searchParams.set('st', F.statuts.join(',')); else u.searchParams.delete('st');
  if (u.href !== location.href) history.replaceState(history.state, '', u);
}

// Statut lisible d'une tâche : clé, libellé court (pastille de la ligne), libellé du filtre.
export const STATUTS_COURTS = [
  ['a-faire', t('filtres.st_a_faire')], ['en-cours', t('filtres.st_en_cours')], ['bloque', t('filtres.st_bloque')], ['a-moi', t('filtres.st_a_moi')],
  ['a-valider', t('filtres.st_a_valider')], ['fait', t('filtres.st_fait')], ['cloture', t('filtres.st_cloture')], ['abandonne', t('filtres.st_abandonne')],
];
export const cleStatut = (n) => (n.statut === RETOUR ? 'a-moi' : n.a_valider ? 'a-valider' : groupeStatut(n.statut));
export const libelleCourt = (n) => n.routine ? libelleRoutine(n) : STATUTS_COURTS.find(([k]) => k === cleStatut(n))?.[1] || n.statut || '—';
export const badgeStatut = (n) => n.routine ? badgeRoutine(n) : n.main ? h('span', { class: `badge-st bs-${cleStatut(n)} bm-${n.main.cle}`, 'data-statut': cleStatut(n), 'data-main': n.main.cle, title: `${libelleMain(n.main)} — ${infoMain(n.main)}` }, t(`main.court.${['veille', 'groupe'].includes(n.main.motif) ? n.main.motif : n.main.cle}`)) : h('span', { class: `badge-st bs-${cleStatut(n)}`, 'data-statut': cleStatut(n) }, libelleCourt(n)); // INV-MAIN-1

const ECHEANCES = [['', t('filtres.toutes')], ['retard', t('filtres.en_retard')], ['semaine', t('filtres.cette_semaine')]];
const GROUPES = [['', t('filtres.g_arbre')], ['statut', t('filtres.g_statut')], ['priorite', t('filtres.g_priorite')], ['projet', t('filtres.g_projet')], ['echeance', t('filtres.g_echeance')], ['etiquette', t('filtres.g_etiquette')]];
const TRIS = [['arbre', t('filtres.tri_arbre')], ['priorite', t('filtres.tri_priorite')]];

const semaine = (n) => { if (!n.echeance) return false; const e = ecartJours(n.echeance); return e >= 0 && e <= 7; };
const filtresActifs = () => F.statuts.length + ['priorite', 'echeance', 'portee', 'harnais', 'executant', 'nature', 'etiquette'].filter((k) => F[k]).length + (F.ia ? 1 : 0) + (F.routines ? 1 : 0) + (S.filtreAMoi ? 1 : 0);
// État de statut partagé par le volet, la vue principale et Aujourd'hui.
export const statutsActifs = () => F.statuts;
export const passeStatut = (n) => !F.statuts.length || F.statuts.includes(cleStatut(n));
export const basculerStatut = (k) => changer({ statuts: F.statuts.includes(k) ? F.statuts.filter((x) => x !== k) : [...F.statuts, k] });
export const effacerStatuts = () => changer({ statuts: [] });
export function comptesStatut(ns) {
  const c = {};
  for (const n of parcourir(ns)) if (n.type === 'tache') { const k = cleStatut(n); c[k] = (c[k] || 0) + 1; }
  return c;
}
export const actif = () => filtresActifs() > 0 || !!F.groupe || F.tri !== 'arbre';

function passe(n, chem) {
  if (S.filtreAMoi && !pourMoi(n)) return false;
  if (F.statuts.length && !F.statuts.includes(cleStatut(n))) return false;
  if (F.priorite && (n.priorite || 'aucune') !== F.priorite) return false;
  if (F.echeance === 'retard' && !n.retard) return false;
  if (F.echeance === 'semaine' && !semaine(n)) return false;
  if (F.portee && !chem.includes(F.portee)) return false;
  if (F.harnais && n.harnais !== F.harnais) return false;
  if (F.executant && (n.executant || 'ia') !== F.executant) return false; // INV-EXECUTANT-1
  if (F.nature && n.genre !== F.nature) return false; // INV-NATURE-1
  if (F.etiquette && !(n.etiquettes || []).includes(F.etiquette)) return false; // INV-ETIQUETTE-1
  if (F.ia && !(S.etat.occupees || {})[n.id]) return false;
  if (F.routines && !n.routine) return false; // INV-ROUTINE-5
  return true;
}
// Tâche de rang : priorité (haute d'abord), puis échéance (sans échéance en dernier).
const cmp = (a, b) => rangPriorite(a.priorite) - rangPriorite(b.priorite) || (a.echeance || '9999').localeCompare(b.echeance || '9999');
const trier = (ns) => (F.tri === 'priorite' ? [...ns.filter((x) => x.type !== 'tache'), ...ns.filter((x) => x.type === 'tache').sort(cmp)] : ns);

function elaguer(ns, chem) {
  const r = [];
  for (const n of ns) {
    const c = [...chem, cleNoeud(n)];
    const enf = elaguer(n.enfants || [], c);
    if (n.type === 'tache' ? passe(n, chem) || enf.length : enf.length) r.push({ ...n, enfants: trier(enf) });
  }
  return trier(r);
}
const nomProjet = (chem, arbre) => {
  const k = [...chem].reverse().find((c) => c.startsWith('conteneur:')) || chem[0];
  for (const x of parcourir(arbre)) if (cleNoeud(x) === k) return x.titre;
  return t('filtres.sans_projet');
};
const GROUPEURS = {
  statut: (n) => [STATUTS_COURTS.findIndex(([c]) => c === cleStatut(n)), libelleCourt(n)],
  priorite: (n) => [rangPriorite(n.priorite), n.priorite ? libellePriorite(n.priorite) : t('filtres.sans_priorite')],
  echeance: (n) => (n.retard ? [0, t('filtres.en_retard')] : !n.echeance ? [4, t('filtres.sans_echeance')] : ecartJours(n.echeance) === 0 ? [1, t('filtres.aujourdhui')] : semaine(n) ? [2, t('filtres.cette_semaine')] : [3, t('filtres.plus_tard')]),
};
function grouper(arbre) {
  const taches = [];
  (function aller(ns, chem) {
    for (const n of ns) {
      const c = [...chem, cleNoeud(n)];
      if (n.type === 'tache') taches.push({ n: { ...n, enfants: [] }, chem });
      aller(n.enfants || [], c);
    }
  })(arbre, []);
  const groupes = new Map();
  const poser = (ordre, titre, n, mot = null) => {
    if (!groupes.has(titre)) groupes.set(titre, { ordre, noeud: { id: `${F.groupe}:${titre}`, type: 'groupe', titre, mot, enfants: [], ouvertes: 0 } });
    groupes.get(titre).noeud.enfants.push(n);
  };
  for (const { n, chem } of taches) {
    // INV-ETIQUETTE-4 : chaque étiquette a son groupe (une tâche paraît sous chacune) ; `mot` : un clic ouvre sa vue.
    if (F.groupe === 'etiquette') {
      if (n.etiquettes?.length) for (const m of n.etiquettes) poser(0, `#${m}`, n, m);
      else poser(1, t('filtres.sans_etiquette'), n);
    } else poser(...(F.groupe === 'projet' ? [0, nomProjet(chem, S.arbre)] : GROUPEURS[F.groupe](n)), n);
  }
  return [...groupes.values()].sort((a, b) => a.ordre - b.ordre || a.noeud.titre.localeCompare(b.noeud.titre, LOCALE))
    .map(({ noeud }) => ({ ...noeud, enfants: noeud.enfants.sort(F.tri === 'priorite' ? cmp : () => 0), ouvertes: noeud.enfants.length }));
}

export const compter = (ns) => { let k = 0; for (const x of parcourir(ns)) if (x.type === 'tache') k += 1; return k; };
// Arbre tel que le volet le montre : filtré, puis groupé ou trié.
export function appliquer(arbre) {
  const a = actif() ? elaguer(arbre, []) : arbre;
  return F.groupe ? grouper(a) : a;
}

function liste(id, libelle, options, val, quand) {
  const sel = h('select', { id, onchange: () => quand(sel.value) }, options.map(([k, l]) => h('option', { value: k, ...(k === val ? { selected: '' } : {}) }, l)));
  return h('label', { class: 'f-champ', for: id }, h('span', null, libelle), sel);
}
function coche(id, libelle, val, quand) {
  const c = h('input', { type: 'checkbox', id, ...(val ? { checked: '' } : {}), onchange: () => quand(c.checked) });
  return h('label', { class: 'f-coche', for: id }, c, h('span', null, libelle));
}
const changer = (patch) => { Object.assign(F, patch); sauver(); emit('filtre'); };

let dernier = 0, der = null;
// INV-DEROULANT-1 : « Filtres et regroupement (n) » est une pastille ; le panneau flotte au-dessus de l'arbre, sans le pousser.
function monter(zone) {
  const bouton = h('button', { type: 'button', class: 'f-pastille', id: 'btn-filtres' });
  const panneau = h('div', { class: 'panneau f-panneau', id: 'panneau-filtres', hidden: true });
  remplacer(zone, bouton, panneau);
  der = deroulant({ bouton, panneau, titre: t('filtres.titre'), remplir: contenu });
}
function contenu(corps) {
  const foc = corps.contains(document.activeElement) ? document.activeElement : null;
  const reperer = foc && (foc.id ? `#${foc.id}` : foc.dataset.statut ? `[data-statut="${foc.dataset.statut}"]` : null);
  const portees = [['', t('filtres.toutes')]];
  for (const x of parcourir(S.arbre)) if (x.type === 'casquette' || x.type === 'conteneur') portees.push([cleNoeud(x), x.titre]);
  const harnais = ['', ...new Set([...parcourir(S.arbre)].filter((x) => x.type === 'tache' && x.harnais).map((x) => x.harnais))].map((k) => [k, k || t('filtres.tous')]);
  const etiqs = ['', ...new Set([...parcourir(S.arbre)].flatMap((x) => (x.type === 'tache' ? x.etiquettes || [] : [])))].sort().map((k) => [k, k ? `#${k}` : t('filtres.toutes')]);
  const comptes = comptesStatut(S.arbre);
  remplacer(corps,
    h('div', { class: 'f-statuts', role: 'group', 'aria-label': t('filtres.statut') }, STATUTS_COURTS.map(([k, l]) => h('button', {
      type: 'button', class: `f-st bs-${k}`, 'aria-pressed': String(F.statuts.includes(k)), 'data-statut': k,
      onclick: () => basculerStatut(k),
    }, l, ' ', h('span', { class: 'n' }, comptes[k] || 0)))),
    F.statuts.length ? h('button', { type: 'button', class: 'btn-discret', id: 'f-st-raz', onclick: effacerStatuts }, t('filtres.effacer_statuts')) : null,
    h('div', { class: 'f-grille' },
      liste('f-priorite', t('filtres.priorite'), [['', t('filtres.toutes')], ['haute', t('filtres.haute')], ['moyenne', t('filtres.moyenne')], ['basse', t('filtres.basse')], ['aucune', t('filtres.sans_priorite')]], F.priorite, (v) => changer({ priorite: v })),
      liste('f-echeance', t('filtres.echeance'), ECHEANCES, F.echeance, (v) => changer({ echeance: v })),
      liste('f-portee', t('filtres.portee'), portees, F.portee, (v) => changer({ portee: v })),
      liste('f-harnais', t('filtres.assistant'), harnais, F.harnais, (v) => changer({ harnais: v })),
      liste('f-executant', t('filtres.executant'), [['', t('filtres.toutes')], ['humain', t('filtres.par_moi')], ['ia', t('filtres.par_ia')]], F.executant, (v) => changer({ executant: v })),
      liste('f-nature', t('lignes.nature'), [['', t('filtres.toutes')], ...NATURES.map((g) => [g, libelleNature(g)])], F.nature, (v) => changer({ nature: v })),
      ...(etiqs.length > 1 || F.etiquette ? [liste('f-etiquette', t('filtres.etiquette'), etiqs, F.etiquette, (v) => changer({ etiquette: v }))] : []),
      liste('f-groupe', t('filtres.grouper'), GROUPES, F.groupe, (v) => changer({ groupe: v })),
      liste('f-tri', t('filtres.trier'), TRIS, F.tri, (v) => changer({ tri: v }))),
    h('div', { class: 'f-pied' },
      coche('f-ia', t('filtres.ia_travail'), F.ia, (v) => changer({ ia: v })),
      coche('f-routines', t('filtres.routines'), F.routines, (v) => changer({ routines: v })),
      coche('f-amoi', t('filtres.a_moi'), S.filtreAMoi, (v) => { S.filtreAMoi = v; sauver(); emit('filtre'); }),
      h('button', { type: 'button', class: 'btn petit', id: 'f-raz', onclick: () => { F = { ...VIDE }; S.filtreAMoi = false; sauver(); emit('filtre'); } }, t('filtres.raz'))));
  if (reperer) corps.querySelector(reperer)?.focus();
}
export function dessinerBarre() {
  const zone = $('#filtres');
  if (!zone) return;
  sauver(); // « À moi » peut aussi être basculé depuis le bandeau
  if (!der || !zone.contains(der.bouton)) monter(zone);
  const n = filtresActifs();
  // Jamais invisible : la pastille dit le nombre de filtres actifs et combien de tâches restent affichées.
  remplacer(der.bouton, h('span', null, t('filtres.titre')), n ? h('span', { class: 'compte', title: tn('filtres.actifs', n) }, n) : null,
    h('span', { class: 'f-compte', id: 'f-compte', role: 'status', 'aria-live': 'polite' }));
  der.bouton.classList.toggle('actif', actif());
  der.redessiner();
  compteur(dernier);
}
export function compteur(k) {
  dernier = k;
  const e = $('#f-compte');
  if (!e) return;
  const total = compter(S.arbre);
  e.textContent = actif() && k !== total ? t('filtres.n_sur_n', { n: k, total }) : tn('filtres.n_taches', k);
}
export function initFiltres() {
  on('filtre', dessinerBarre);
  on('arbre', () => { if (!$('#filtres').contains(document.activeElement)) dessinerBarre(); });
  dessinerBarre();
}
