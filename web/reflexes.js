// Rôle : « Réflexes de l'agent » — pour chaque assistant IA du poste, état du bloc de réflexes GoldenBrain dans son fichier de
//        consignes (absent, à jour, ancienne version, retouché), aperçu du changement, puis Accepter / Plus tard / Retirer.
// Frontières : GET /api/accueil/reflexes, POST …/appliquer et …/plus-tard (poste seulement). Rien n'est écrit sans le clic de
//        l'utilisateur sur Accepter ou Retirer (INV-REFLEXES-1). Montré dans Réglages > Agents et dans les premiers pas.
// INV-WEB-1 : tout passe par h().
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { emit, erreur } from './store.js';
import { t } from './langues.js';

const ROUTE = '/accueil/reflexes';

function ligne(a, boite, apres) {
  const geste = async (chemin, corps) => {
    try { dessiner(boite, await post(ROUTE + chemin, corps), apres); apres?.(); } catch (x) { erreur(x.message); }
  };
  const actions = [];
  if (a.etat !== 'a_jour') {
    actions.push(h('button', { class: 'btn primaire', type: 'button', 'data-id': `rf-accepter-${a.id}`, onclick: () => geste('/appliquer', { harnais: a.id, action: 'installer' }) },
      a.etat === 'absent' ? t('reflexes.accepter') : t('reflexes.mettre_a_jour')));
    if (a.propose) actions.push(h('button', { class: 'btn', type: 'button', 'data-id': `rf-plus-tard-${a.id}`, onclick: () => geste('/plus-tard', { harnais: a.id }) }, t('reflexes.plus_tard')));
  }
  if (a.etat !== 'absent') {
    actions.push(h('button', { class: 'btn', type: 'button', 'data-id': `rf-retirer-${a.id}`,
      onclick: () => { if (confirm(t('reflexes.retirer_confirmer', { fichier: a.fichier }))) geste('/appliquer', { harnais: a.id, action: 'retirer' }); } }, t('reflexes.retirer')));
  }
  return h('li', { class: 'pp-assistant', 'data-id': `rf-${a.id}`, 'data-etat': a.etat },
    h('div', null, h('b', null, a.libelle), ` — ${t(`reflexes.etat_${a.etat}`, { version: a.version })}`),
    h('div', { class: 'note' }, a.fichier),
    a.apercu ? h('details', null, h('summary', null, t('reflexes.apercu')), h('pre', { class: 'note', 'data-id': `rf-apercu-${a.id}` }, a.apercu)) : null,
    actions.length ? h('div', { class: 'ac-actions' }, actions) : null);
}

function dessiner(boite, r, apres) {
  const liste = (r.assistants || []).filter((a) => a.present || a.etat !== 'absent');
  emit('resume', ['reflexes', r.propose ? t('reflexes.resume_propose') : t('reflexes.resume_ok')]);
  remplacer(boite,
    h('p', { class: 'note' }, t('reflexes.intro', { version: r.version })),
    liste.length ? h('ul', { class: 'pp-liste', 'data-id': 'rf-liste' }, liste.map((a) => ligne(a, boite, apres)))
      : h('p', { class: 'note', 'data-id': 'rf-aucun' }, t('reflexes.aucun')));
}

/** Section autonome : se charge elle-même ; `apres` est rappelé après chaque geste (premiers pas). */
export function sectionReflexes(apres = null) {
  const boite = h('div', { 'data-id': 'reflexes' }, h('p', { class: 'note' }, t('reflexes.lecture')));
  api(ROUTE).then((r) => dessiner(boite, r, apres)).catch(() => remplacer(boite, h('p', { class: 'note' }, t('reflexes.poste_seulement'))));
  return boite;
}
