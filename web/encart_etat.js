// Rôle : encart « Où en est-on » sous l'en-tête d'une tâche — fait, attendu de vous, prochaine étape, en trois lignes.
// Frontières : lit seulement `tache.fiche` et `tache.main` déjà servis par GET /taches/{id} ; ne calcule aucun état (INV-MAIN-1),
// n'écrit rien, n'ajoute aucune consigne à l'IA : la fiche est réécrite par l'agent à chaque tour.
import { t } from './langues.js';
import { h, remplacer } from './dom.js';

const MAX = 160;

// Première phrase, entière si elle tient ; sinon coupée à un mot avec « … ». Le texte complet reste dans title=.
export function premierePhrase(texte, max = MAX) {
  const s = String(texte || '').replace(/\s+/g, ' ').trim();
  const m = s.match(/^.+?[.!?…](?=\s|$)/);
  const p = m ? m[0] : s;
  if (p.length <= max) return p;
  const coupe = p.slice(0, max - 1);
  return `${coupe.slice(0, Math.max(coupe.lastIndexOf(' '), max / 2))}…`;
}

const ligne = (cle, brut, texte) => h('div', { class: 'encart-ligne', 'data-ligne': cle, title: brut },
  h('span', { class: 'encart-lib' }, t(`encart.${cle}`)), h('span', { class: 'encart-txt' }, texte));

export function encartEtat(tache) {
  const f = tache?.fiche || {}, m = tache?.main;
  const fait = (f.resultat || f.fait || '').trim(), pas = (f.prochain_pas || f.reste || '').trim();
  const humain = m?.cle === 'humain' ? (m.phrase || m.motif || '').trim() : '';
  if (!fait && !pas) return null; // fiche vide : rien à reprendre, et l'en-tête dit déjà la phrase de la main (INV-MAIN-1)
  const attendu = humain ? ligne('attendu', humain, premierePhrase(humain))
    : m?.cle === 'ia' || m?.cle === 'file' ? ligne('attendu', t('encart.rien'), t('encart.rien')) : null;
  return h('div', { class: 'encart-etat', 'data-id': 'encart-etat' },
    fait ? ligne('fait', fait, premierePhrase(fait)) : null, attendu, pas ? ligne('prochaine', pas, premierePhrase(pas)) : null);
}

// Placement : l'encart se redessine avec la fiche (même chemin que dessinerFiche).
export const placerEncart = (conteneur, tache) => remplacer(conteneur, encartEtat(tache));
