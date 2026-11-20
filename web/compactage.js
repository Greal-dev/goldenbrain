// Rôle : section « Compactage automatique » de la page Réglages — seuil général (% de la fenêtre, plafond en jetons facultatif),
// mécanisme par harnais, et vue de mesure par harnais et tranche de contexte. INV-COMPACT-1.
// Frontières : GET/PUT /api/compactage ; le serveur valide et reste maître des valeurs.
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { erreur } from './store.js';
import { t, LOCALE } from './langues.js';

let zone = null;

async function regler(corps) {
  try { remplir(await api('/compactage', { methode: 'PUT', corps })); } catch (e) { erreur(e.message); recharger(); }
}

const nombre = (id, valeur, min, max, cle, lib, pas = '1') => h('label', { class: 'rg-champ' }, lib,
  h('input', { type: 'number', 'data-id': id, min, max, step: pas, value: valeur,
    onchange: (e) => regler({ [cle]: Number(e.target.value) }) }));

const pct = (x) => `${(x * 100).toLocaleString(LOCALE, { maximumFractionDigits: 1 })} %`;

function mesure(lignes) {
  if (!lignes.length) return h('p', { class: 'note', 'data-id': 'cp-mesure' }, t('compactage.aucune_mesure'));
  const ligne = (m) => h('tr', null, h('td', null, m.harnais), h('td', null, m.tranche), h('td', null, String(m.tours)),
    h('td', null, m.duree_moyenne_s == null ? '—' : `${m.duree_moyenne_s.toLocaleString(LOCALE)} s`), h('td', null, pct(m.taux_echec)),
    h('td', null, String(m.apres_compactage)), h('td', null, String(m.compactages)));
  return h('table', { class: 'rg-table', 'data-id': 'cp-mesure' },
    h('thead', null, h('tr', null, [t('compactage.col_assistant'), t('compactage.col_memoire'), t('compactage.col_seances'), t('compactage.col_duree'), t('compactage.col_echecs'), t('compactage.col_apres'), t('compactage.col_ordres')].map((x) => h('th', null, x)))),
    h('tbody', null, lignes.map(ligne)));
}

function remplir(s) {
  if (!zone) return;
  const harnais = Object.entries(s.harnais).map(([nom, f]) => h('li', null,
    h('b', null, nom), f.natif ? t('compactage.natif') : (f.ordre ? t('compactage.repli_ordre', { ordre: f.ordre }) : t('compactage.repli_sans_ordre'))));
  remplacer(zone,
    h('div', { class: 'rg-sim' },
      nombre('cp-pct', s.pct, 1, 100, 'pct', t('compactage.seuil'), '0.5'),
      nombre('cp-plafond', s.plafond, 0, 100000000, 'plafond', t('compactage.plafond'), '1000')),
    h('p', { class: 'note' }, t('compactage.note')),
    h('ul', { class: 'rg-liste', 'data-id': 'cp-harnais' }, harnais),
    h('h4', null, t('compactage.mesure')), mesure(s.mesure));
}

export function recharger() {
  if (zone?.isConnected) api('/compactage').then(remplir).catch((e) => erreur(e.message));
}

export function sectionCompactage() {
  zone = h('div', { 'data-id': 'compactage' }, h('p', { class: 'note' }, t('compactage.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('compactage.titre')), zone];
}
