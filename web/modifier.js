// Rôle : « Modifier » un message envoyé (plan à blanc, avertissement, case code, renvoi) et versions précédentes de la conversation.
// Frontières : appels `/taches/{id}/modifier` et `/versions` ; le rendu des messages reste à conversation.js. INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3.
// INV-WEB-1 : tout texte passe par h() (jamais d'innerHTML).
import { h } from './dom.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { rendreConversation } from './conversation.js';
import { t, tn } from './langues.js';

const enc = encodeURIComponent;
const MECANISME = {
  natif: t('modifier.meca_natif'),
  transcription: t('modifier.meca_transcription'),
  neuve: t('modifier.meca_neuve'),
};
const ETAT = { modifie: t('modifier.etat_modifie'), supprime: t('modifier.etat_supprime'), recree: t('modifier.etat_recree') };
const liste = (titre, items, rendu = (x) => x) => (items.length
  ? h('details', { class: 'modif-liste' }, h('summary', null, `${titre} (${items.length})`), h('ul', null, items.map((x) => h('li', null, rendu(x)))))
  : null);

function avertissement(p, repondre) {
  const code = p.code;
  return h('div', { class: 'modif-plan' },
    h('p', { class: 'modif-alerte', role: 'alert' },
      repondre ? tn('modifier.retire_suite', p.retires) : tn('modifier.retire_ici', p.retires)),
    h('p', null, MECANISME[p.mecanisme] || ''),
    liste(t('modifier.vault'), p.vault),
    liste(t('modifier.hors_depot'), p.hors_depot),
    code ? (code.erreur ? h('p', null, t('modifier.code_illisible', { erreur: code.erreur }))
      : liste(t('modifier.code_restaurable', { depot: code.depot }), code.fichiers, (f) => `${f.chemin} : ${ETAT[f.etat] || f.etat}`)
        || h('p', null, t('modifier.code_inchange')))
      : h('p', null, t('modifier.code_aucun')));
}

// Résout avec le résultat du renvoi, ou null si annulé. `repondre` : « Répondre à partir d'ici » sur une réponse de l'IA,
// c.-à-d. modifier le message qui la suit (`tour`) en partant d'une saisie vide — même plan, même avertissement, même case.
export async function modifierMessage(ident, tour, ancien, repondre = false) {
  const p = await api(`/taches/${enc(ident)}/modifier?tour=${enc(tour)}`);
  const restaurable = !!(p.code && !p.code.erreur && p.code.fichiers.length);
  const v = await formulaire({
    titre: repondre ? t('modifier.repondre') : t('modifier.titre'), valider: repondre ? t('modifier.envoyer') : t('modifier.renvoyer'), large: true, corps: avertissement(p, repondre),
    champs: [
      { nom: 'texte', label: t('modifier.message'), type: 'textarea', lignes: 6, valeur: ancien, requis: true },
      { nom: 'code', label: t('modifier.restaurer_code'), type: 'checkbox', valeur: false, desactive: !restaurable },
    ],
  });
  if (!v || !v.texte.trim()) return null;
  return post(`/taches/${enc(ident)}/modifier`, { tour, texte: v.texte, code: !!v.code });
}

// Bloc « Versions précédentes » en tête de conversation (null s'il n'y en a pas) ; chaque version se charge à l'ouverture.
// La conversation se redessine à chaque événement de tour : ce qui était ouvert le reste (clés `<tâche>` et `<tâche>:<n>`).
const ouverts = new Set();
const suivre = (d, cle, charger) => {
  d.addEventListener('toggle', () => { if (d.open) { ouverts.add(cle); charger?.(); } else ouverts.delete(cle); });
  if (ouverts.has(cle)) d.open = true;
};
export async function blocVersions(ident) {
  let vs;
  try { vs = await api(`/taches/${enc(ident)}/versions`); } catch { return null; }
  if (!vs.length) return null;
  const bloc = h('details', { class: 'modif-versions' }, h('summary', null, t('modifier.versions', { n: vs.length })),
    vs.map((v) => {
      const d = h('details', { class: 'modif-version' }, h('summary', null, tn('modifier.version', v.retires, { v: v.n, date: v.date.replace('T', ' ') })));
      suivre(d, `${ident}:${v.n}`, async () => {
        if (d.dataset.charge) return;
        d.dataset.charge = '1';
        const x = await api(`/taches/${enc(ident)}/versions/${v.n}`);
        d.append(h('div', { class: 'conv' }, rendreConversation(x.messages, false, new Set())));
      });
      return d;
    }));
  suivre(bloc, ident);
  return bloc;
}
