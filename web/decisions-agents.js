// Rôle : lignes « Agent Claude Code » de la page « Décisions » — une carte par groupe d'agents doublons,
// rattachement proposé (tâche existante, création, ignorer) modifiable, appliqué par lot ou à l'unité.
// Frontières : écrit seulement par POST /decisions/agents (INV-AGENTSCC-1) ; ne lit que les lignes déjà chargées.
import { h } from './dom.js';
import { t } from './langues.js';

const choix = new Map();   // id d'agent -> { action, tache } (choix de l'utilisateur, sinon la proposition)
const cochees = new Set(); // groupes cochés pour le lot

const proposition = (a) => choix.get(a.id) || { action: a.action, tache: a.tache || (a.candidats[0]?.tache ?? '') };

function selecteur(a, redessiner) {
  const c = proposition(a);
  const options = [
    ...a.candidats.map((k) => ({ v: `rattacher:${k.tache}`, t: t('decisions_agents.rattacher', { titre: k.titre, pct: Math.round(k.score * 100) }) })),
    { v: 'creer:', t: t('decisions_agents.creer', { nom: a.nom }) }, { v: 'ignorer:', t: t('decisions_agents.ignorer') }];
  const sel = h('select', { class: 'ag-choix', 'aria-label': t('decisions_agents.sort_de', { nom: a.nom }),
    onchange: () => { const [action, tache] = sel.value.split(':'); choix.set(a.id, { action, tache: tache || '' }); redessiner(); } },
  options.map((o) => h('option', { value: o.v, selected: o.v === `${c.action}:${c.action === 'rattacher' ? c.tache : ''}` ? true : null }, o.t)));
  return sel;
}

export function ligneAgent(d, { geste, lot, redessiner }) {
  const a = d.agent, c = proposition(a);
  const appliquer = () => { cochees.delete(a.id); return geste(() => lot('/decisions/agents', { choix: [{ id: a.id, ...c }] })); };
  return h('li', { class: 'dc dc-agent', 'data-genre': 'agent', 'data-agent': a.id },
    h('div', { class: 'dc-tete' },
      h('input', { type: 'checkbox', class: 'dc-coche', 'aria-label': t('decisions_agents.cocher', { nom: a.nom }), checked: cochees.has(a.id) ? true : null,
        onchange: (e) => { (e.target.checked ? cochees.add(a.id) : cochees.delete(a.id)); redessiner(); } }),
      h('span', { class: 'tag' }, d.libelle), h('b', { class: 'dc-titre' }, a.nom),
      h('span', { class: 'dc-motif' }, t('decisions_agents.etat_maj', { etat: a.etat || t('decisions_agents.etat_inconnu'), date: (a.maj || '').slice(0, 10) }))),
    h('p', { class: 'dc-essai' }, a.dossier, a.historique.length ? t('decisions_agents.conversations', { n: a.historique.length + 1 }) : ''),
    h('p', { class: `dc-q${a.detail ? '' : ' manque'}` }, a.detail || t('decisions_agents.aucun_message')),
    h('div', { class: 'dc-actions' }, selecteur(a, redessiner),
      h('button', { class: 'btn primaire petit', type: 'button', 'data-appliquer-agent': '', onclick: appliquer }, t('decisions_agents.appliquer')),
      a.reprise_ici ? null : h('span', { class: 'dc-essai', title: t('decisions_agents.autre_dossier_titre') }, t('decisions_agents.autre_dossier'))));
}

// Bouton du lot : applique le choix (proposé ou modifié) de chaque agent coché.
export function lotAgents(tout, { geste, lot }) {
  const sel = tout.filter((d) => d.genre === 'agent' && cochees.has(d.agent.id));
  return h('button', { class: 'btn primaire petit', id: 'dc-lot-agents', type: 'button', disabled: sel.length ? null : true,
    onclick: () => { const c = sel.map((d) => ({ id: d.agent.id, ...proposition(d.agent) })); cochees.clear(); geste(() => lot('/decisions/agents', { choix: c })); } },
  t('decisions_agents.appliquer_coches', { n: sel.length }));
}
