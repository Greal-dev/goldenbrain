// Rôle : pastille « intégration en retard » d'une tâche terminée (arbre) et section « Intégration » des Réglages.
// Frontières : le serveur décide (n.integration_retard, GET/PUT /api/integration) ; ce module ne fait que le montrer. INV-INTEG-1.
import { h } from './dom.js';
import { api } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

export const pastilleRetard = (n) => n.integration_retard ? h('span', { class: 'pastille-retard', 'data-id': 'integration-retard',
  title: t('integration.pastille_titre', { branche: n.integration_retard.branche, heures: n.integration_retard.heures }) },
  t('integration.pastille', { heures: n.integration_retard.heures })) : null;

let zone = null;

const regler = async (corps) => {
  try { remplir(await api('/integration', { methode: 'PUT', corps })); } catch (e) { erreur(e.message); recharger(); }
};

function remplir(s) {
  if (!zone) return;
  zone.replaceChildren(
    h('div', { class: 'rg-sim' },
      h('label', { class: 'rg-champ' }, t('integration.branche'),
        h('input', { type: 'text', 'data-id': 'ig-branche', value: s.branche, onchange: (e) => regler({ branche: e.target.value.trim() }) })),
      h('label', { class: 'rg-champ' }, t('integration.retard'),
        h('input', { type: 'number', 'data-id': 'ig-retard', min: '0.1', step: '0.5', value: s.retard_h, onchange: (e) => regler({ retard_h: Number(e.target.value) }) }))),
    h('p', { class: 'note' }, t('integration.note')));
}

export function recharger() {
  if (zone?.isConnected) api('/integration').then(remplir).catch((e) => erreur(e.message));
}

export function sectionIntegration() {
  zone = h('div', { 'data-id': 'integration' }, h('p', { class: 'note' }, t('integration.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('integration.titre')), zone];
}
