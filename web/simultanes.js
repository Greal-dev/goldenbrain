// Rôle : section « Agents simultanés » de la page Réglages — trois modes exclusifs (nombre fixe, optimiser l'usage, plafond de RAM),
// état mesuré du poste et des pauses. INV-SIMULT-1.
// Frontières : GET/PUT /api/simultanes ; le serveur valide et reste maître des valeurs effectives.
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { erreur, emit } from './store.js';
import { t, tn, LOCALE } from './langues.js';

const GO = 1024 ** 3;
const go = (o) => (o / GO).toLocaleString(LOCALE, { maximumFractionDigits: 1 });
const MODES = [
  ['fixe', t('simultanes.mode_fixe'), t('simultanes.mode_fixe_phrase')],
  ['optimiser', t('simultanes.mode_optimiser'), t('simultanes.mode_optimiser_phrase')],
  ['plafond', t('simultanes.mode_plafond'), t('simultanes.mode_plafond_phrase')],
];

let zone = null;

async function regler(corps) {
  try { remplir(await api('/simultanes', { methode: 'PUT', corps })); } catch (e) { erreur(e.message); recharger(); }
}

const nombre = (id, valeur, min, max, cle, lib) => h('label', { class: 'rg-champ' }, lib,
  h('input', { type: 'number', 'data-id': id, min, max, step: cle === 'plafond' ? '0.5' : '1', value: valeur,
    onchange: (e) => regler({ [cle]: Number(e.target.value) }) }));

function etat(s) {
  if (!s.mesure_disponible) return h('p', { class: 'note', 'data-id': 'sim-etat' }, t('simultanes.illisible'));
  const r = s.ram;
  return h('p', { class: 'note', 'data-id': 'sim-etat' },
    [t('simultanes.memoire', { occupee: go(r.occupee), total: go(r.total) }),
      r.seuil != null ? t('simultanes.seuil', { seuil: go(r.seuil) }) : null,
      t('simultanes.processeur', { cpu: Math.round(r.cpu) }),
      tn('simultanes.actifs', s.actifs, { limite: s.limite }),
      s.pauses.length ? t('simultanes.pauses', { n: s.pauses.length }) : null].filter(Boolean).join(' · '));
}

// Résumé d'une ligne pour le titre du groupe « Agents et ressources » (reglages.js).
const resume = (s) => ({ fixe: tn('simultanes.resume_fixe', s.simultanes_max),
  optimiser: t('simultanes.resume_optimiser', { marge: s.marge_pct }),
  plafond: s.unite === 'pct' ? t('simultanes.resume_plafond_pct', { plafond: s.plafond }) : t('simultanes.resume_plafond_go', { plafond: s.plafond }) }[s.mode]);

function remplir(s) {
  emit('resume', ['simultanes', resume(s)]);
  if (!zone) return;
  const choix = ([v, lib, phrase]) => h('li', { class: 'rg-fam' },
    h('label', { class: 'case' }, h('input', { type: 'radio', name: 'sim-mode', 'data-id': `sim-${v}`, checked: s.mode === v ? true : null, onchange: () => regler({ mode: v }) }), h('b', null, lib)),
    h('div', { class: 'rg-phrase' }, phrase));
  const reglage = {
    fixe: [nombre('sim-nombre', s.simultanes_max, 1, 64, 'simultanes_max', t('simultanes.nombre'))],
    optimiser: [nombre('sim-marge', s.marge_pct, 1, 99, 'marge_pct', t('simultanes.marge')), nombre('sim-garde', s.garde_max, 1, 64, 'garde_max', t('simultanes.garde'))],
    plafond: [nombre('sim-plafond-valeur', s.plafond, 0.5, s.unite === 'pct' ? 99 : 1024, 'plafond', t('simultanes.ram_max')),
      h('select', { 'data-id': 'sim-unite', 'aria-label': t('simultanes.unite'), onchange: (e) => regler({ unite: e.target.value }) },
        [['go', t('simultanes.unite_go')], ['pct', t('simultanes.unite_pct')]].map(([v, l]) => h('option', { value: v, selected: s.unite === v ? true : null }, l))),
      nombre('sim-garde', s.garde_max, 1, 64, 'garde_max', ' ' + t('simultanes.garde'))],
  }[s.mode];
  remplacer(zone, h('ul', { class: 'rg-liste' }, MODES.map(choix)), h('div', { class: 'rg-sim' }, reglage), etat(s),
    s.mode !== 'fixe' ? h('p', { class: 'note' }, t('simultanes.note')) : null);
}

export function recharger() {
  if (zone?.isConnected) api('/simultanes').then(remplir).catch((e) => erreur(e.message));
}

export function sectionSimultanes() {
  zone = h('div', { 'data-id': 'simultanes' }, h('p', { class: 'note' }, t('simultanes.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('simultanes.titre')), zone];
}
