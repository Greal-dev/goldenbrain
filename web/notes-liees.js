// Rôle : bloc « Notes liées » du détail d'une tâche — liens sortants vers des notes, liens entrants, mentions non liées.
// Frontières : API GET /vault/note (liens et entrants du fichier de tâche), GET /vault/mentions (INV-NOTE-4) ; replié, chargé
// seulement à l'ouverture ; n'écrit rien (la création depuis un lien orphelin reste dans la vue de la note).
import { h, remplacer } from './dom.js';
import { ouvrirNote } from './store.js';
import { api } from './api.js';
import { t } from './langues.js';

const enc = encodeURIComponent;

function liste(titre, l, vide) {
  return h('div', null, h('h4', null, `${titre} (${l.length})`),
    l.length ? h('ul', null, l.map((e) => h('li', null,
      h('button', { class: 'lien-titre', type: 'button', onclick: () => ouvrirNote(e.chemin), title: e.chemin }, e.titre || e.chemin),
      e.extrait ? h('span', { class: 'n-extrait' }, ` ${e.extrait}`) : null))) : h('p', { class: 'vide' }, vide));
}

// L'en-tête du détail se redessine à chaque rafraîchissement : le même bloc est rendu tant que la tâche ne change pas (il reste ouvert).
let dernier = null;
export function notesLiees(chemin) {
  if (dernier?.chemin === chemin) return dernier.el;
  const corps = h('div', null);
  const el = h('details', { class: 'd-notes-liees f-notes', ontoggle: async (e) => {
    if (!e.target.open || corps.dataset.charge) return;
    corps.dataset.charge = '1';
    remplacer(corps, h('p', { class: 'vide' }, t('notes_liees.chargement')));
    try {
      const [n, m] = await Promise.all([api(`/vault/note?chemin=${enc(chemin)}`), api(`/vault/mentions?chemin=${enc(chemin)}`)]);
      const vus = new Set();
      const sortants = (n.liens || []).filter((l) => l.chemin && l.chemin.endsWith('.md') && !vus.has(l.chemin) && vus.add(l.chemin))
        .map((l) => ({ chemin: l.chemin, titre: l.cible }));
      remplacer(corps, liste(t('notes_liees.cite'), sortants, t('notes_liees.aucune_citee')),
        liste(t('notes_liees.mentionnee'), n.entrants || [], t('notes_liees.aucune_entrante')),
        liste(t('notes_liees.mentions'), m, t('notes_liees.aucune')));
    } catch (x) { delete corps.dataset.charge; remplacer(corps, h('p', { class: 'vide' }, x.message)); }
  } }, h('summary', null, t('notes_liees.titre')), corps);
  dernier = { chemin, el };
  return el;
}
