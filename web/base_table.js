// Rôle : page « Base » du volet droit (#base=<dossier>) — un dossier du vault en tableau : une note par ligne, ses propriétés pour colonnes ;
// tri par en-tête, filtre par colonne, regroupement avec sous-totaux, calcul en pied choisi par colonne, colonnes visibles.
// Frontières : lit GET /bases/table (filtre, tri, groupes et agrégats calculés par le serveur, INV-BASES-1 : rien n'est écrit dans le vault) ;
// les réglages de vue vivent dans localStorage, par dossier ; ouvre une note par store.ouvrirNote, un wikilink par ponts.ouvrirLien.
// Chargé à la demande (app.js, INV-REACTIVITE-1).
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { ouvrirNote, erreur } from './store.js';
import { ouvrirLien } from './ponts.js';
import { t, LOCALE } from './langues.js';

const CLE = 'orch.base.', RECENTS = 'orch.bases.recents', WIKI = /^\[\[([^\]|#]+)[^\]|]*(?:\|([^\]]+))?\]\]$/;
let coque = null, dossier = '', reglages = null, donnees = null, version = 0, minuteur = 0;

const lireJson = (cle, defaut) => { try { return JSON.parse(localStorage.getItem(cle)) ?? defaut; } catch { return defaut; } };
const vierge = () => ({ tri: '', filtres: {}, groupe: '', agregats: {}, cachees: [] });
const sauver = () => localStorage.setItem(CLE + dossier, JSON.stringify(reglages));
const recents = () => lireJson(RECENTS, []);
function noterRecent(d) { localStorage.setItem(RECENTS, JSON.stringify([d, ...recents().filter((x) => x !== d)].slice(0, 8))); }

// Réglages d'interface → filtres du serveur (un champ vide ne filtre pas).
const OPS = { contient: 'contient', min: '>=', max: '<=', a: 'a' };
function filtresServeur() {
  const out = [];
  for (const [colonne, f] of Object.entries(reglages.filtres)) {
    for (const [k, op] of Object.entries(OPS)) if (f[k] !== undefined && f[k] !== '') out.push({ colonne, op, valeur: f[k] });
    if (f.est) out.push({ colonne, op: '=', valeur: f.est === 'oui' });
  }
  return out;
}

const nombre = (v) => (typeof v === 'number' ? v.toLocaleString(LOCALE, { maximumFractionDigits: 2 }) : v);
function lien(brut, depuis) {
  const m = WIKI.exec(brut);
  if (!m) return null;
  return h('a', { class: 'base-lien', href: '#', onclick: (e) => { e.preventDefault(); e.stopPropagation(); ouvrirLien(m[1].trim(), depuis); } }, (m[2] || m[1]).trim());
}
function cellule(v, type, depuis) {
  if (v == null || v === '') return null;
  if (type === 'case' || typeof v === 'boolean') return h('span', { class: `base-case${v === true ? ' coche' : ''}`, role: 'img', 'aria-label': t(v === true ? 'base.oui' : 'base.non') });
  if (Array.isArray(v)) return v.map((x) => h('span', { class: 'base-puce' }, typeof x === 'string' && lien(x, depuis) || String(x)));
  if (typeof v === 'string') return lien(v, depuis) || v;
  return typeof v === 'object' ? JSON.stringify(v) : String(nombre(v));
}

function changer(fn, immediat = true) {
  fn(); sauver();
  clearTimeout(minuteur);
  minuteur = setTimeout(charger, immediat ? 0 : 300);
}
const filtre = (col) => (reglages.filtres[col] ||= {});
function champ(col, cle, attrs) {
  const f = filtre(col);
  return h('input', { ...attrs, class: 'base-filtre', 'data-f': `${col}:${cle}`, value: f[cle] ?? '', 'aria-label': t('base.filtre_aria', { colonne: col }),
    oninput: (e) => changer(() => { f[cle] = e.target.value; }, false) });
}
function controleFiltre(c) {
  const f = filtre(c.nom);
  if (c.type === 'nombre') return [champ(c.nom, 'min', { type: 'number', step: 'any', placeholder: t('base.min') }), champ(c.nom, 'max', { type: 'number', step: 'any', placeholder: t('base.max') })];
  if (c.type === 'date') return [champ(c.nom, 'min', { type: 'date' }), champ(c.nom, 'max', { type: 'date' })];
  if (c.type === 'case' || c.type === 'liste') {
    const cle = c.type === 'case' ? 'est' : 'a', choix = c.type === 'case' ? [['oui', t('base.oui')], ['non', t('base.non')]] : (c.valeurs || []).map((x) => [x, x]);
    return h('select', { class: 'base-filtre', 'data-f': `${c.nom}:${cle}`, 'aria-label': t('base.filtre_aria', { colonne: c.nom }), onchange: (e) => changer(() => { f[cle] = e.target.value; }) },
      h('option', { value: '' }, t('base.tous')), choix.map(([v, l]) => h('option', { value: v, selected: f[cle] === v }, l)));
  }
  return champ(c.nom, 'contient', { type: 'search' });
}

function enTete(nom, libelle) {
  const sens = reglages.tri === nom ? 'ascending' : reglages.tri === `-${nom}` ? 'descending' : 'none';
  return h('th', { scope: 'col', 'aria-sort': sens }, h('button', { class: 'base-tri', type: 'button', 'data-col': nom,
    onclick: () => changer(() => { reglages.tri = reglages.tri === nom ? `-${nom}` : nom; }) }, libelle));
}
const valeurAgregat = (c, a) => { const fn = reglages.agregats[c.nom] ?? (c.type === 'nombre' ? 'somme' : ''); return fn ? nombre(a?.[c.nom]?.[fn]) ?? '—' : ''; };
function rangeeAgregats(cols, a, classe, premier) {
  return h('tr', { class: classe }, h('td', null, premier), cols.map((c) => h('td', { class: `base-agg t-${c.type}`, 'data-col': c.nom }, String(valeurAgregat(c, a)))));
}
function pied(cols) {
  return h('tfoot', null, h('tr', null, h('td', null, String(donnees.filtrees)), cols.map((c) => {
    const actuel = reglages.agregats[c.nom] ?? (c.type === 'nombre' ? 'somme' : '');
    return h('td', { class: `base-agg t-${c.type}`, 'data-col': c.nom },
      h('select', { class: 'base-choix-agg', 'aria-label': t('base.agregat_aria', { colonne: c.nom }), onchange: (e) => { reglages.agregats[c.nom] = e.target.value; sauver(); dessiner(); } },
        h('option', { value: '' }, t('base.agg.aucun')), c.agregats.map((fn) => h('option', { value: fn, selected: fn === actuel }, t(`base.agg.${fn}`)))),
      h('span', { class: 'base-valeur' }, String(valeurAgregat(c, donnees.agregats))));
  })));
}
function ligne(l, cols) {
  return h('tr', { class: 'base-ligne', tabindex: '0', 'data-chemin': l.chemin, onclick: () => ouvrirNote(l.chemin), onkeydown: (e) => { if (e.key === 'Enter') ouvrirNote(l.chemin); } },
    h('th', { scope: 'row' }, l.titre), cols.map((c) => h('td', { class: `t-${c.type}` }, cellule(l.valeurs[c.nom], c.type, l.chemin))));
}
function corps(cols) {
  if (!donnees.lignes.length) return h('tbody', null, h('tr', null, h('td', { colspan: cols.length + 1, class: 'vide' }, t('base.vide'))));
  if (!donnees.groupes) return h('tbody', null, donnees.lignes.map((l) => ligne(l, cols)));
  const typeGroupe = donnees.colonnes.find((c) => c.nom === reglages.groupe)?.type;
  return donnees.groupes.map((g) => h('tbody', { class: 'base-groupe' },
    h('tr', { class: 'base-groupe-titre' }, h('th', { colspan: cols.length + 1, scope: 'rowgroup' }, cellule(g.valeur, typeGroupe, '') ?? t('base.sans_valeur'), h('span', { class: 'n' }, g.lignes.length))),
    g.lignes.map((i) => ligne(donnees.lignes[i], cols)),
    rangeeAgregats(cols, g.agregats, 'base-sous-total', '')));
}

function outils() {
  const cols = donnees.colonnes;
  return h('div', { class: 'base-outils' },
    h('label', null, t('base.regrouper'), ' ', h('select', { 'data-id': 'base-groupe', onchange: (e) => changer(() => { reglages.groupe = e.target.value; }) },
      h('option', { value: '' }, t('base.aucun')), cols.map((c) => h('option', { value: c.nom, selected: c.nom === reglages.groupe }, c.nom)))),
    h('details', { class: 'base-colonnes' }, h('summary', null, t('base.colonnes')), cols.map((c) => h('label', null,
      h('input', { type: 'checkbox', checked: !reglages.cachees.includes(c.nom), 'data-col': c.nom,
        onchange: (e) => { reglages.cachees = e.target.checked ? reglages.cachees.filter((x) => x !== c.nom) : [...reglages.cachees, c.nom]; sauver(); dessiner(); } }), ' ', c.nom))),
    h('button', { class: 'btn-discret', type: 'button', onclick: () => changer(() => { reglages.filtres = {}; }) }, t('base.effacer')));
}

function dessiner() {
  if (!coque?.isConnected || !donnees) return;
  const actif = document.activeElement?.dataset?.f, ouvert = coque.querySelector('.base-colonnes')?.open;
  const cols = donnees.colonnes.filter((c) => !reglages.cachees.includes(c.nom));
  remplacer(coque, h('h2', { class: 'casc-titre' }, t('base.titre', { dossier: dossier || t('base.racine') })),
    h('p', { class: 'base-info' }, t('base.compte', { n: donnees.filtrees, total: donnees.total }), donnees.tronque ? ` ${t('base.tronque', { plafond: donnees.plafond })}` : ''),
    outils(),
    h('div', { class: 'base-defile' }, h('table', { class: 'base-table' },
      h('thead', null, h('tr', null, enTete('titre', t('base.col_titre')), cols.map((c) => enTete(c.nom, c.nom))),
        h('tr', { class: 'base-filtres' }, h('td'), cols.map((c) => h('td', null, controleFiltre(c))))),
      corps(cols), pied(cols))));
  if (ouvert) coque.querySelector('.base-colonnes').open = true;
  if (actif) { const el = coque.querySelector(`[data-f="${CSS.escape(actif)}"]`); el?.focus(); if (el?.type === 'search') el.setSelectionRange(el.value.length, el.value.length); }
}

async function charger() {
  const moi = ++version, pour = dossier;
  const q = new URLSearchParams({ dossier, filtres: JSON.stringify(filtresServeur()), tri: reglages.tri, groupe: reglages.groupe });
  try {
    const d = await api(`/bases/table?${q}`);
    if (moi === version && pour === dossier) { donnees = d; dessiner(); }
  } catch (e) {
    // Réglages mémorisés devenus caducs (colonne disparue) : on repart d'une vue vierge plutôt que de rester bloqué.
    if (moi === version && (reglages.groupe || filtresServeur().length)) { reglages = vierge(); sauver(); charger(); } else erreur(e.message);
  }
}

export function dessinerBase(zone, d) {
  if (!coque || coque.parentNode !== zone || d !== dossier) {
    dossier = d ?? ''; donnees = null;
    reglages = { ...vierge(), ...lireJson(CLE + dossier, {}) };
    coque = h('div', { class: 'base', 'data-id': 'base' }, h('p', { class: 'vide' }, t('base.chargement')));
    remplacer(zone, coque);
  }
  noterRecent(dossier);
  charger();
}
