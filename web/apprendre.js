// Rôle : mode « Apprendre » côté écran — section des Réglages (interrupteur général) et réglage par tâche (en-tête de la tâche).
// Frontières : GET/PUT /api/apprendre et POST /api/taches/<id>/apprendre ; le serveur reste maître des valeurs ; l'affichage des
//        encadrés d'explication est le rendu Markdown des conversations (callout `[!apprendre]`, style dans apprendre.css).
// INV-APPRENDRE-1, INV-LANGUE-1 : libellés aux dictionnaires (préfixe apprendre.), vocabulaire grand public.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { emit, erreur } from './store.js';
import { t } from './langues.js';

let zone = null;

async function regler(actif) {
  try { remplir(await api('/apprendre', { methode: 'PUT', corps: { actif } })); } catch (e) { erreur(e.message); recharger(); }
}

function remplir(s) {
  emit('resume', ['apprendre', s.actif ? t('apprendre.resumeOui') : t('apprendre.resumeNon')]);
  if (!zone) return;
  remplacer(zone,
    h('label', { class: 'case' },
      h('input', { type: 'checkbox', 'data-id': 'ap-actif', checked: s.actif ? true : null, onchange: (e) => regler(e.target.checked) }),
      h('b', null, t('apprendre.case'))),
    h('p', { class: 'note', 'data-id': 'ap-aide' }, t('apprendre.aide')));
}

export function recharger() {
  if (zone?.isConnected) api('/apprendre').then(remplir).catch((e) => erreur(e.message));
}

export function sectionApprendre() {
  zone = h('div', { 'data-id': 'apprendre' }, h('p', { class: 'note' }, t('apprendre.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('apprendre.titre')), zone];
}

// Réglage d'une tâche : « oui » / « non » dans son frontmatter, rien = suit le réglage général.
export function selecteurApprendre(tk, surTache) {
  const pose = String(tk.frontmatter?.apprendre ?? '').toLowerCase();
  const val = pose === 'oui' ? 'oui' : pose === 'non' ? 'non' : '';
  const opt = (v, lib) => h('option', { value: v, selected: v === val ? true : null }, lib);
  return h('label', { class: 'ap-tache', title: t('apprendre.tacheTitre') }, `${t('apprendre.tache')} `,
    h('select', { 'data-id': 'ap-tache', 'aria-label': t('apprendre.tacheTitre'),
      onchange: async (e) => {
        const v = e.target.value;
        try { surTache(await post(`/taches/${encodeURIComponent(tk.id)}/apprendre`, { valeur: v === '' ? null : v === 'oui' })); } catch (x) { erreur(x.message); }
      } }, opt('', t('apprendre.suivre')), opt('oui', t('apprendre.oui')), opt('non', t('apprendre.non'))));
}
