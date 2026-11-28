// Rôle : fil d'une réponse donnée sur la page « Décisions » — écho du message, « l'agent répond… », puis sa réponse.
// Frontières : aucun état serveur ; la fin du tour vient de l'événement `tour_fin` (même flux que la fiche, app.js), la
// réponse se relit par GET /taches/{id}/conversation. INV-DECISIONS-4.
import { h } from './dom.js';
import { api, post } from './api.js';
import { on, ouvrir, erreur } from './store.js';
import { elMsg } from './conversation.js';
import { t } from './langues.js';

const echanges = new Map(); // tâche -> { titre, texte, etat: 'repond' | 'fini', reponse }
let redessin = () => {};
const actif = (x) => x === 'en_cours' || x === 'en_file';

// INV-DECISIONS-4 : la décision quitte la liste dès l'envoi (INV-DECISIONS-2) ; l'échange, lui, reste jusqu'à la réponse.
async function terminer(tache) {
  const e = echanges.get(tache);
  if (!e || e.etat !== 'repond') return;
  try {
    if (actif((await api(`/taches/${encodeURIComponent(tache)}`)).etat_execution)) return; // un tour antérieur vient de finir : le nôtre suit
    const msgs = await api(`/taches/${encodeURIComponent(tache)}/conversation?limite=50`);
    const m = [...msgs].reverse().find((x) => x.role !== 'utilisateur' && x.role !== 'systeme' && x.texte?.trim());
    e.reponse = m ? { ...m, dernier: false, suite: '' } : null;
  } catch (x) { erreur(x.message); e.reponse = null; }
  e.etat = 'fini';
  redessin();
}
on('tour_fin', (ev) => terminer(ev.tache));

// Envoi unique : une seconde pression pendant le tour est ignorée. Renvoie vrai si le message est parti.
export async function repondre(d, texte, redessiner) {
  if (echanges.get(d.tache)?.etat === 'repond') return false;
  redessin = redessiner;
  echanges.set(d.tache, { titre: d.titre, texte, etat: 'repond', reponse: null, horodatage: new Date().toISOString() });
  redessiner();
  try {
    const r = await post(`/taches/${d.tache}/messages`, { texte });
    if (!actif(r.etat_execution)) await terminer(d.tache);
    return true;
  } catch (x) {
    echanges.delete(d.tache);
    erreur(x.message);
    redessiner();
    return false;
  }
}

export const enCours = (tache) => echanges.get(tache)?.etat === 'repond';

export function blocEchanges(redessiner) {
  redessin = redessiner;
  if (!echanges.size) return null;
  return h('section', { class: 'dc-echanges' }, [...echanges].map(([tache, e]) => h('div', { class: 'dc-echange', 'data-tache': tache },
    h('div', { class: 'dc-tete' },
      h('button', { class: 'dc-titre', type: 'button', title: t('decisions.ouvrir_fiche'), onclick: () => ouvrir(tache) }, e.titre),
      e.etat === 'fini' ? h('button', { class: 'btn petit', type: 'button', 'data-fermer': '', onclick: () => { echanges.delete(tache); redessiner(); } }, t('decisions.echange_fermer')) : null),
    elMsg({ role: 'utilisateur', texte: e.texte, outils: [], horodatage: e.horodatage }),
    e.etat === 'repond'
      ? h('div', { class: 'activite', role: 'status' }, h('span', { class: 'tourne' }), h('span', { class: 'act-t' }, t('conversation.travaille')))
      : e.reponse ? elMsg(e.reponse) : h('p', { class: 'dc-essai' }, t('decisions.echange_vide')))));
}
