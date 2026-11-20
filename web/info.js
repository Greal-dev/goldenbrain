// Rôle : ligne d'information flottante (#info-geste) partagée par les gestes d'arbre, la promotion et la réduction.
// Frontières : aucune E/S ; les boutons d'action rappellent le code de l'appelant. INV-WEB-1 : tout passe par h().
import { h, remplacer } from './dom.js';
import { t } from './langues.js';

let zone = null, minuteur = 0;
// `texte` : chaîne ou nœuds ; `actions` : [{libelle, action}] ; `duree` : ms, 0 = jusqu'au prochain message ou clic sur « × ».
export function info(texte, actions = [], duree) {
  if (!zone) { zone = h('div', { id: 'info-geste', role: 'status', 'aria-live': 'polite' }); document.body.append(zone); }
  clearTimeout(minuteur);
  const masquer = () => remplacer(zone);
  remplacer(zone, h('span', null, texte),
    actions.map((a) => h('button', { type: 'button', class: 'lien-annuler', onclick: () => { masquer(); a.action(); } }, a.libelle)),
    duree === 0 ? h('button', { type: 'button', class: 'lien-annuler discret', 'aria-label': t('info.masquer'), onclick: masquer }, '×') : null);
  const d = duree ?? (actions.length ? 10000 : 4000);
  if (d > 0) minuteur = setTimeout(masquer, d);
}

export const effacerInfo = () => { if (zone) remplacer(zone); };
