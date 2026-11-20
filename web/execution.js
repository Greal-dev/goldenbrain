// Rôle : réglage « Exécution » d'une tâche mère ou d'un conteneur, et motif de la décision sur une sous-tâche.
// Frontières : la règle vit au serveur (regroupement.py) ; ce module ne fait que lire, poser et afficher.
// Invariant : INV-REGROUPE-1 (réglage hérité vers le bas, défaut automatique, motif affiché).
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

const LIBELLES = { automatique: t('execution.mode_auto'), par_tache: t('execution.mode_tache'), regroupee: t('execution.mode_regroupee') };

export function selecteurExecution(noeud, ex, apres) {
  const herite = t('execution.heriter', { mode: LIBELLES[ex.herite] || ex.herite, de: ex.herite_de ? ` — ${ex.herite_de}` : '' });
  const opt = (v, txt) => h('option', { value: v, selected: v === (ex.reglage || '') ? true : null }, txt);
  const s = h('select', { 'aria-label': t('execution.aria'), 'data-execution': '', title: t('execution.titre') },
    opt('', herite), opt('automatique', t('execution.opt_auto')), opt('par_tache', t('execution.opt_tache')), opt('regroupee', t('execution.opt_regroupee')));
  s.onchange = async () => {
    try { apres(await api('/execution', { methode: 'PUT', corps: { noeud, reglage: s.value } })); } catch (e) { erreur(e.message); }
  };
  return s;
}

export function motifExecution(ex) {
  const d = ex?.decision;
  return d ? h('span', { class: `execution ${d.mode}`, 'data-motif-execution': d.mode }, d.motif) : null;
}

// Vue en cascade : réglage du conteneur affiché (lu au changement de nœud seulement).
let vu = null;
export async function majReglageConteneur(zone, cont) {
  const cible = cont?.type === 'conteneur' ? cont.id : null;
  if (cible === vu) return;
  vu = cible; remplacer(zone);
  if (!cible) return;
  try {
    const ex = await api(`/execution?noeud=${encodeURIComponent(cible)}`);
    const poser = (n) => { if (vu === cible) remplacer(zone, selecteurExecution(cible, n, poser)); };
    poser(ex);
  } catch (e) { erreur(e.message); }
}
