// Rôle : « Signaler un problème / Proposer une idée » (Réglages → Installation et version) — liens vers les formulaires
//        de ticket du dépôt public, pré-remplis par le serveur avec la version, le canal et le système.
// Frontières : GET /api/signaler seulement ; rien n'est envoyé d'ici : le navigateur ouvre GitHub, l'utilisateur relit
//        et envoie. INV-SIGNAL-1 (docs/ARCHITECTURE.md).
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { t } from './langues.js';

const lien = (id, href, texte, primaire) => h('a', { class: `btn petit${primaire ? ' primaire' : ''}`, 'data-id': id, href,
  target: '_blank', rel: 'noopener noreferrer' }, texte);

export function sectionSignaler() {
  const zone = h('div', { 'data-id': 'signaler' }, h('p', { class: 'note' }, t('signaler.lecture')));
  api('/signaler').then((a) => remplacer(zone,
    h('p', { class: 'rg-ligne' }, lien('signaler-anomalie', a.anomalie, t('signaler.anomalie'), true), ' ',
      lien('signaler-idee', a.idee, t('signaler.idee')), ' ', lien('signaler-question', a.discussions, t('signaler.question'))),
    h('p', { class: 'note' }, t('signaler.note', { version: a.champs.version, systeme: a.champs.systeme }))))
    .catch(() => remplacer(zone, h('p', { class: 'note' }, t('signaler.indisponible'))));
  return zone;
}
