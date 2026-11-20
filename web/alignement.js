// Rôle : alignement des dossiers sur l'arbre — pastille du bandeau, panneau des écarts (cases à cocher), appel du plan.
// Frontières : API GET /alignement (au chargement et après chaque geste d'arbre) ; le plan et l'application sont dans alignement-plan.js.
import { t, tn } from './langues.js';
import { h, $, remplacer } from './dom.js';
import { on } from './store.js';
import { ouvert } from './interface.js';
import { api } from './api.js';
import { voirPlan } from './alignement-plan.js';

let ecarts = [], choisis = new Set(), minuteur = 0, indisponible = false;

export async function rafraichirEcarts() {
  if (!ouvert('alignement')) { ecarts = []; dessiner(); return ecarts; } // INV-INTERFACE-1 : la route répondrait 409
  if (indisponible) return ecarts;
  try { ecarts = await api('/alignement'); } catch (e) { if (e.statut === 404 || e.statut === 501) indisponible = true; ecarts = []; }
  choisis = new Set([...choisis].filter((c) => ecarts.some((e) => e.conteneur === c && !e.conflit)));
  dessiner();
  return ecarts;
}

function dessiner() {
  const b = $('#btn-align');
  b.hidden = !ecarts.length;
  $('#n-align').textContent = ecarts.length;
  $('#lib-align').textContent = tn('alignement.libelle', ecarts.length);
  if (!$('#panneau-align').hidden) panneau();
}

function panneau() {
  const libres = ecarts.filter((e) => !e.conflit);
  const tout = h('input', { type: 'checkbox', 'aria-label': t('alignement.tout_cocher'), disabled: libres.length ? null : true,
    checked: libres.length && libres.every((e) => choisis.has(e.conteneur)) ? true : null,
    onchange: (ev) => { choisis = new Set(ev.target.checked ? libres.map((e) => e.conteneur) : []); panneau(); } });
  const ligne = (e) => h('li', { class: `al-ecart${e.conflit ? ' en-conflit' : ''}` },
    h('label', { class: 'case' }, h('input', { type: 'checkbox', disabled: e.conflit ? true : null, checked: choisis.has(e.conteneur) ? true : null,
      onchange: (ev) => { if (ev.target.checked) choisis.add(e.conteneur); else choisis.delete(e.conteneur); panneau(); } }), h('b', null, e.titre)),
    h('div', { class: 'al-chemins' }, h('code', null, e.de), ' → ', h('code', null, e.vers)),
    e.conflit ? h('div', { class: 'al-conflit' }, t('alignement.conflit', { motif: e.conflit })) : null);
  remplacer($('#panneau-align'),
    h('p', { class: 'dlg-texte' }, t('alignement.explication')),
    h('label', { class: 'case al-tout' }, tout, t('alignement.tout_cocher_texte')),
    h('ul', { class: 'al-liste' }, ecarts.map(ligne)),
    h('div', { class: 'dlg-actions' },
      h('button', { type: 'button', class: 'btn primaire', disabled: choisis.size ? null : true,
        onclick: () => { ouvrirPanneau(false); voirPlan([...choisis]); } }, t('alignement.voir_plan', { n: choisis.size }))));
}
function ouvrirPanneau(o) {
  $('#panneau-align').hidden = !o;
  $('#btn-align').setAttribute('aria-expanded', String(o));
  if (o) panneau();
}

export function initAlignement() {
  $('#btn-align').addEventListener('click', () => ouvrirPanneau($('#panneau-align').hidden));
  document.addEventListener('click', (e) => { if (!e.target.closest('.rel-align')) ouvrirPanneau(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#panneau-align').hidden) ouvrirPanneau(false); });
  // Après chaque geste d'arbre (ou changement signalé par le serveur) ; regroupé pour ne pas multiplier les appels.
  on('arbre', () => { clearTimeout(minuteur); minuteur = setTimeout(rafraichirEcarts, 600); });
  rafraichirEcarts();
}
