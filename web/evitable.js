// Rôle : section « Pastille « évitable ? » » de la page Réglages — activée ou non, seuil en % des critères remplis. INV-EVITABLE-1.
// Frontières : GET/PUT /api/decisions/evitable ; le serveur valide et reste maître des valeurs ; la pastille se lit sur la page Décisions.
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

let zone = null;

async function regler(corps) {
  try { remplir(await api('/decisions/evitable', { methode: 'PUT', corps })); } catch (e) { erreur(e.message); recharger(); }
}

function remplir(s) {
  if (!zone) return;
  remplacer(zone,
    h('label', { class: 'case' },
      h('input', { type: 'checkbox', 'data-id': 'ev-actif', checked: s.actif ? true : null, onchange: (e) => regler({ actif: e.target.checked }) }),
      h('b', null, t('evitable.actif'))),
    h('div', { class: 'rg-sim' },
      h('label', { class: 'rg-champ' }, t('evitable.seuil'),
        h('input', { type: 'number', 'data-id': 'ev-seuil', min: 25, max: 100, step: 5, value: s.seuil, disabled: s.actif ? null : true,
          onchange: (e) => regler({ seuil: Number(e.target.value) }) }))),
    h('p', { class: 'note' }, t('evitable.note')));
}

export function recharger() {
  if (zone?.isConnected) api('/decisions/evitable').then(remplir).catch((e) => erreur(e.message));
}

export function sectionEvitable() {
  zone = h('div', { 'data-id': 'evitable' }, h('p', { class: 'note' }, t('evitable.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('evitable.titre')), zone];
}
