// Rôle : carte d'une proposition d'agent (accepter / refuser), partagée par le panneau et la vue d'ensemble.
// INV-EXEC-5 : seule une action humaine ici exécute une proposition.
import { h, depuis } from './dom.js';
import { S, emit, erreur, titreTache } from './store.js';
import { post } from './api.js';
import { t } from './langues.js';
import { garnir } from './garnir.js';

const LONG = 140;
const gras = (x) => h('b', null, x);

export function description(p) {
  const titre = p.titre_tache || titreTache(p.tache);
  const tache = gras(titre);
  switch (p.type) {
    case 'deplacer': return garnir(t('propositions.deplacer'), { tache, cible: h('code', null, p.valeur) });
    case 'rattacher': {
      const lot = p.taches?.length > 1, racine = p.valeur === 'racine';
      const parent = gras(titreTache(p.valeur));
      const phrase = garnir(t(racine ? (lot ? 'propositions.detacher_lot' : 'propositions.detacher') : (lot ? 'propositions.rattacher_lot' : 'propositions.rattacher'), { n: p.taches?.length }), { tache, parent });
      if (!lot) return phrase;
      return h('details', { class: 'prop-long' }, h('summary', null, phrase), h('ul', null, ...(p.titres || p.taches).map((x) => h('li', null, x))));
    }
    case 'ticket': return garnir(t('propositions.ticket'), { valeur: gras(p.valeur), tache });
    case 'projet': return garnir(t('propositions.projet'), { tache, valeur: gras(p.valeur) });
    case 'lier': {
      const v = String(p.valeur ?? '');
      const i = v.indexOf(':');
      const [sens, cible] = i < 0 ? ['', v] : [v.slice(0, i), v.slice(i + 1)];
      const b = gras(titreTache(cible));
      if (sens === 'alimente') return garnir(t('propositions.lier_alimente'), { tache, cible: b });
      if (sens === 'prerequis') return garnir(t('propositions.lier_prerequis'), { tache, cible: b });
      if (sens === 'voir_aussi') return garnir(t('propositions.lier_voir_aussi'), { tache, cible: b });
      return garnir(t('propositions.lier', { valeur: v }), { tache });
    }
    case 'operation': return garnir(t('propositions.operation'), { tache, valeur: gras(p.valeur) });
    case 'echeance': return garnir(t('propositions.echeance', { valeur: p.valeur }), { tache });
    case 'fermer': return garnir(p.valeur === 'abandonne' ? t('propositions.fermer_abandonne') : t('propositions.fermer_cloture'), { tache });
    case 'renommer': return garnir(t('propositions.renommer'), { tache, valeur: gras(p.valeur) });
    case 'tache': return garnir(t('propositions.tache'), { valeur: gras(p.valeur), tache });
    case 'perimetre': {
      const v = String(p.valeur ?? '');
      if (v.length <= LONG) return garnir(t('propositions.perimetre', { texte: v }), { tache });
      return h('details', { class: 'prop-long' },
        h('summary', null, garnir(t('propositions.perimetre', { texte: `${v.slice(0, LONG).trimEnd()}…` }), { tache })),
        h('p', null, v));
    }
    default: return [`${p.type} : `, titre, ' ', p.valeur];
  }
}
async function trancher(p, action) {
  try {
    await post(`/propositions/${p.n}/${action}`);
    emit('recharger');
  } catch (e) { erreur(e.message); emit('recharger'); } // 409 : la proposition reste en attente, le message explique pourquoi
}
export const enAttente = () => S.props.filter((p) => p.etat === 'en_attente');
export function carteProposition(p) {
  const d = description(p);
  const bloc = !Array.isArray(d); // libellé replié (<details>) : la méta passe sur sa propre ligne
  return h('li', { class: 'prop' },
    h('div', { class: 'prop-txt' }, d,
      h('span', { class: `prop-meta${bloc ? ' bloc' : ''}` }, (bloc ? '' : ' · ') + t('propositions.par_agent', { de: p.de || t('propositions.agent') }) + (p.cree ? t('propositions.il_y_a', { duree: depuis(p.cree) }) : '')),
      p.motif ? h('div', { class: 'prop-motif' }, p.motif) : null),
    h('div', { class: 'prop-btns' },
      h('button', { class: 'btn primaire petit', onclick: () => trancher(p, 'accepter') }, t('propositions.accepter')),
      h('button', { class: 'btn petit', onclick: () => trancher(p, 'refuser') }, t('propositions.refuser'))));
}
