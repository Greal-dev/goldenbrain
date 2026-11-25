// Rôle : propositions d'agent (accepter / refuser) groupées par tâche émettrice, une ligne chacune ; partagées par le panneau,
// l'accueil et la page Décisions. INV-EXEC-5 : seule une action humaine ici exécute une proposition. INV-PROP-2 : groupe replié
// en une ligne, une ligne par proposition, motif et détail au dépli ou au survol, jamais de carte multi-lignes.
import { h, depuis } from './dom.js';
import { S, emit, erreur, titreTache } from './store.js';
import { post } from './api.js';
import { t } from './langues.js';
import { garnir } from './garnir.js';

const LONG = 140;
const gras = (x) => h('b', null, x);

export function description(p, court = false) { // court : la phrase seule, le détail long va au dépli
  const titre = p.titre_tache || titreTache(p.tache);
  const tache = gras(titre);
  switch (p.type) {
    case 'deplacer': return garnir(t('propositions.deplacer'), { tache, cible: h('code', null, p.valeur) });
    case 'rattacher': {
      const lot = p.taches?.length > 1, racine = p.valeur === 'racine';
      const parent = gras(titreTache(p.valeur));
      const phrase = garnir(t(racine ? (lot ? 'propositions.detacher_lot' : 'propositions.detacher') : (lot ? 'propositions.rattacher_lot' : 'propositions.rattacher'), { n: p.taches?.length }), { tache, parent });
      if (!lot || court) return phrase;
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
      if (court) return garnir(t('propositions.perimetre', { texte: `${v.slice(0, LONG).trimEnd()}…` }), { tache });
      return h('details', { class: 'prop-long' },
        h('summary', null, garnir(t('propositions.perimetre', { texte: `${v.slice(0, LONG).trimEnd()}…` }), { tache })),
        h('p', null, v));
    }
    default: return [`${p.type} : `, titre, ' ', p.valeur];
  }
}
async function trancher(p, action) {
  try {
    const r = await post(`/propositions/${p.n}/${action}`);
    if (r?.deja_fait) erreur(t('propositions.deja_fait'), 'info'); // geste déjà réalisé : acceptée, sans erreur
    emit('recharger');
  } catch (e) { erreur(e.message); emit('recharger'); } // 409 : la proposition reste en attente, le message explique pourquoi
}
export const enAttente = () => S.props.filter((p) => p.etat === 'en_attente');
const long = (p) => (p.type === 'perimetre' && String(p.valeur ?? '').length > LONG ? h('p', null, p.valeur)
  : p.type === 'rattacher' && p.taches?.length > 1 ? h('ul', null, ...(p.titres || p.taches).map((x) => h('li', null, x))) : null);
// Bouton d'icône posé dans un <summary> : le clic agit sans replier ni déplier.
const icone = (attr, libelle, signe, agir) => h('button', { type: 'button', class: `btn-icone ${attr}`, [`data-${attr}`]: '', 'aria-label': libelle, title: libelle,
  onclick: (e) => { e.preventDefault(); e.stopPropagation(); agir(); } }, signe);
const sansRepli = (f) => (e) => { e.preventDefault(); e.stopPropagation(); f(); };

// Une proposition = une ligne : verbe et objet tronqués, deux icônes ; motif et détail long au dépli, texte complet au survol.
export function ligneProposition(p, agir = trancher, classe = 'prop', extra = null) {
  const de = p.de || t('propositions.agent');
  const survol = [p.motif, t('propositions.par_agent', { de }) + (p.cree ? t('propositions.il_y_a', { duree: depuis(p.cree) }) : '')].filter(Boolean).join('\n');
  const plus = long(p);
  return h('li', { class: classe, 'data-n': p.n, title: p.motif || null },
    h('details', { class: 'prop-d' },
      h('summary', { title: survol },
        h('span', { class: 'prop-txt' }, description(p, true)),
        h('span', { class: 'prop-btns' },
          icone('accepter', t('propositions.accepter'), '✓', () => agir(p, 'accepter')),
          icone('refuser', t('propositions.refuser'), '✕', () => agir(p, 'refuser')))),
      p.motif ? h('p', { class: 'prop-motif' }, p.motif) : null, plus,
      h('p', { class: 'prop-meta' }, survol.split('\n').pop())),
    extra);
}
async function toutTrancher(ps, action) {
  for (const p of ps) { try { await post(`/propositions/${p.n}/${action}`); } catch (e) { erreur(e.message); } }
  emit('recharger');
}
// Groupe d'une tâche émettrice, replié par défaut : « Propositions de <tâche> (n) — Tout accepter / Tout refuser ».
export function groupePropositions(de, ps, { agir = trancher, tout = (a) => toutTrancher(ps, a), classeLigne = 'prop', extra = () => null } = {}) {
  return h('details', { class: 'prop-groupe', 'data-de': de },
    h('summary', null,
      h('span', { class: 'prop-g-titre' }, t('decisions.propositions_de', { de: titreTache(de) })), ' ', h('span', { class: 'n' }, ps.length),
      h('span', { class: 'prop-g-btns' },
        h('button', { type: 'button', class: 'btn petit', 'data-tout': 'accepter', onclick: sansRepli(() => tout('accepter')) }, t('decisions.tout_accepter')),
        h('button', { type: 'button', class: 'btn petit btn-discret', 'data-tout': 'refuser', onclick: sansRepli(() => tout('refuser')) }, t('decisions.tout_refuser')))),
    h('ul', { class: 'prop-lignes' }, ps.map((p) => ligneProposition(p, agir, classeLigne, extra(p)))));
}
export function parEmetteur(l) {
  const m = new Map();
  for (const p of l) { const de = p.de || p.tache; if (!m.has(de)) m.set(de, []); m.get(de).push(p); }
  return [...m];
}
export const listePropositions = (l, classe = 'props') => h('ul', { class: classe }, parEmetteur(l).map(([de, ps]) => h('li', null, groupePropositions(de, ps))));
