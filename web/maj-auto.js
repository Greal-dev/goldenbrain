// Rôle : mise à jour automatique (INV-MAJ-3) et canal stable ou bêta (INV-MAJ-4) — réglages dans Réglages, bandeau discret (préparation, « Mis à jour vers … », incident),
// battement d'activité qui reporte la mise à jour tant que l'utilisateur est à l'écran.
// Frontières : GET/PUT /api/maj-auto, POST /api/maj-auto/activite, DELETE /api/maj-auto/bandeau ; lit S.etat.version.maj_auto.
import { h, $, remplacer } from './dom.js';
import { api, post } from './api.js';
import { S, on, erreur } from './store.js';
import { t, tn, LANGUE } from './langues.js';

const BATTEMENT_MS = 20000;
let zone = null, bandeau = null, dernier = 0;

const etat = () => S.etat.version?.maj_auto;
const tours = (n) => tn('maj_auto.reprises', n);

function dessinerBandeau() {
  const m = etat();
  const incident = m?.incident, fait = m?.bandeau, prepare = m?.phase === 'gel';
  bandeau.hidden = !(incident || fait || prepare);
  if (bandeau.hidden) return;
  const fermer = h('button', { type: 'button', class: 'btn petit', 'data-id': 'maj-auto-fermer', onclick: fermerBandeau }, t('maj_auto.fermer'));
  if (incident) {
    remplacer(bandeau, h('span', { class: 'maj-t' }, h('b', null, t('maj_auto.abandonnee')), t('maj_auto.incident', { a: incident.a, cause: incident.cause }), incident.geste ? h('i', null, t('maj_auto.que_faire', { geste: incident.geste })) : ''), fermer);
  } else if (fait) {
    remplacer(bandeau, h('span', { class: 'maj-t' }, fait.reprises ? t('maj_auto.mis_a_jour', { version: fait.version, a: fait.a, reprises: tours(fait.reprises) }) : t('maj_auto.mis_a_jour_aucune', { version: fait.version, a: fait.a })), fermer);
  } else {
    remplacer(bandeau, h('span', { class: 'maj-t' }, tn('maj_auto.preparation', m.attendus)));
  }
}

async function fermerBandeau() {
  try { await api('/maj-auto/bandeau', { methode: 'DELETE' }); } catch (e) { erreur(e.message); return; }
  const m = etat();
  if (m) { m.bandeau = null; m.incident = null; }
  dessinerBandeau();
}

// Un geste dans la page signale « je suis là » ; au plus un envoi par battement, et seulement si l'option est active.
function geste() {
  const maintenant = Date.now();
  if (!etat()?.reglage?.actif || maintenant - dernier < BATTEMENT_MS) return;
  dernier = maintenant;
  post('/maj-auto/activite', {}).catch(() => {});
}

async function regler(corps) {
  try { remplir(await api('/maj-auto', { methode: 'PUT', corps })); } catch (e) { erreur(e.message); recharger(); }
}

function remplir(m) {
  if (S.etat.version) S.etat.version.maj_auto = { ...(S.etat.version.maj_auto || {}), ...m };
  if (!zone?.isConnected) return;
  const r = m.reglage;
  const champ = (id, type, valeur, extra = {}) => h('input', { type, 'data-id': id, value: valeur, 'aria-label': id, ...extra });
  const delai = champ('maj-auto-delai', 'number', r.delai_min, { min: 1, max: 1440 });
  const debut = champ('maj-auto-debut', 'time', r.fenetre_debut), fin = champ('maj-auto-fin', 'time', r.fenetre_fin);
  const canal = h('select', { 'data-id': 'maj-canal', 'aria-label': t('maj_auto.canal_aria'), onchange: (e) => regler({ canal: e.target.value }) },
    [['stable', t('maj_auto.canal_stable')], ['beta', t('maj_auto.canal_beta')]].map(([v, l]) => h('option', { value: v, selected: r.canal === v ? true : null }, l)));
  const beta = `https://github.com/Greal-dev/goldenbrain/blob/main/BETA${LANGUE === 'en' ? '' : `.${LANGUE}`}.md`; // page du testeur dans sa langue
  remplacer(zone,
    h('label', { class: 'rg-ligne' }, t('maj_auto.canal'), canal),
    h('p', { class: 'note' }, t('maj_auto.canal_note'),
      h('a', { href: beta, target: '_blank', rel: 'noopener', 'data-id': 'maj-testeur' }, t('maj_auto.testeur'))),
    h('label', { class: 'rg-ligne' }, h('input', { type: 'checkbox', 'data-id': 'maj-auto-actif', checked: r.actif ? true : null, onchange: (e) => regler({ actif: e.target.checked }) }),
      t('maj_auto.appliquer')),
    h('p', { class: 'note' }, t('maj_auto.note')),
    h('label', { class: 'rg-ligne' }, t('maj_auto.delai'), delai,
      h('button', { type: 'button', class: 'btn petit', 'data-id': 'maj-auto-delai-ok', onclick: () => regler({ delai_min: Number(delai.value) }) }, t('maj_auto.enregistrer'))),
    h('label', { class: 'rg-ligne' }, t('maj_auto.fenetre_de'), debut, t('maj_auto.fenetre_a'), fin,
      h('button', { type: 'button', class: 'btn petit', 'data-id': 'maj-auto-fenetre-ok', onclick: () => regler({ fenetre_debut: debut.value, fenetre_fin: fin.value }) }, t('maj_auto.enregistrer'))),
    h('p', { class: 'note' }, t('maj_auto.attend')));
}

function recharger() {
  if (zone?.isConnected) api('/maj-auto').then(remplir).catch((e) => erreur(e.message));
}

export function sectionMiseAJour() {
  zone = h('div', { 'data-id': 'maj-auto' }, h('p', { class: 'note' }, t('maj_auto.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('maj_auto.titre')), zone];
}

export function initMajAuto() {
  bandeau = $('#maj-auto');
  on('etat', dessinerBandeau);
  for (const ev of ['pointermove', 'keydown', 'pointerdown']) document.addEventListener(ev, geste, { passive: true });
  dessinerBandeau();
}
