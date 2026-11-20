// Rôle : accès à la conversation d'un conteneur (chat de projet) depuis sa vue en cascade.
// Frontières : la conversation elle-même est le panneau d'une tâche (detail.js), ouverte par store.ouvrir ;
// ce module ne fait que la trouver, ou la faire créer au premier message (INV-PILOTAGE-1).
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { ouvrir, erreur } from './store.js';
import { t } from './langues.js';

let noeud = null, tache = null;

export function boutonConversation(zone) {
  const b = h('button', { class: 'btn petit', type: 'button', hidden: true, 'data-pilotage': '' }, t('pilotage.conversation'));
  b.onclick = () => { if (tache) ouvrir(tache); else { zone.hidden = !zone.hidden; if (!zone.hidden) zone.querySelector('textarea')?.focus(); } };
  return b;
}

function composer(zone, cible) {
  const ta = h('textarea', { rows: 2, 'aria-label': t('pilotage.message_aria'), placeholder: t('pilotage.message_invite') });
  const envoyer = async (e) => {
    e?.preventDefault();
    const texte = ta.value.trim();
    if (!texte) return;
    try {
      const r = await post('/pilotage', { noeud: cible, texte });
      tache = r.tache; ta.value = ''; ouvrir(r.tache);
    } catch (x) { erreur(x.message); }
  };
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.ctrlKey) envoyer(e); });
  remplacer(zone, h('form', { class: 'composer', onsubmit: envoyer },
    h('div', { class: 'c-ligne' }, ta, h('div', { class: 'c-col' }, h('button', { class: 'btn', type: 'submit' }, t('pilotage.envoyer'))))));
}

export async function majConversation(bouton, zone, cont) {
  const cible = cont ? cont.id : null;
  bouton.hidden = !cible;
  if (cible === noeud) return; // la vue se redessine souvent : on ne recherche qu'au changement de nœud
  noeud = cible; tache = null; zone.hidden = true; remplacer(zone);
  if (!cible) return;
  composer(zone, cible);
  try {
    const r = await api(`/pilotage?noeud=${encodeURIComponent(cible)}`);
    if (noeud === cible) tache = r.tache;
  } catch (x) { erreur(x.message); }
  bouton.title = tache ? t('pilotage.ouvrir_titre') : t('pilotage.ecrire_titre');
}
