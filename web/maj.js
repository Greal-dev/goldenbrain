// Rôle : bandeau « Une mise à jour est disponible » (branche de diffusion en avance sur le dépôt local), son « Quoi de neuf » et geste « Mettre à jour ».
// Frontières : GET/POST /mise-a-jour ; le redémarrage et l'attente du retour sont ceux de version.js. INV-MAJ-1, INV-NOUV-1 (docs/ARCHITECTURE.md).
import { h, $, remplacer } from './dom.js';
import { erreur } from './store.js';
import { api, post } from './api.js';
import { attendreRetour } from './version.js';
import { t, tn } from './langues.js';

const RECONTROLE_MS = 30 * 60 * 1000; // le serveur ne contacte le dépôt distant qu'une fois par heure
let zone, bouton;

function dessiner(e) {
  const dispo = e?.depot && e.retard > 0;
  zone.hidden = !dispo;
  if (!dispo) return;
  const n = e.retard;
  // INV-MAJ-4 : le canal a changé dans les Réglages ; « Mettre à jour » rejoint sa branche.
  const lieu = { distant: e.distant, branche: e.branche };
  const texte = e.bascule ? (e.canal === 'beta' ? t('maj.bascule_beta', lieu) : t('maj.bascule_stable', lieu)) : tn('maj.retard', n, lieu);
  remplacer(zone, h('span', { class: 'maj-t' }, h('b', null, t('maj.disponible')), texte, quoiDeNeuf(e.nouveautes)), bouton);
}

// « Quoi de neuf » : les nouveautés de la version en attente, tirées du journal CHANGELOG.md (INV-NOUV-1).
function quoiDeNeuf(sections) {
  if (!sections?.length) return null;
  return h('details', { class: 'maj-neuf' }, h('summary', null, t('maj.quoi_de_neuf')),
    ...sections.map(s => h('div', null, s.version ? h('b', null, t('maj.version', { version: s.version })) : null,
      h('ul', null, ...s.entrees.map(entree => h('li', null, entree))))));
}

async function controler() {
  try { dessiner(await api('/mise-a-jour')); } catch { /* hors ligne ou serveur ancien : pas de bandeau */ }
}

async function mettre() {
  bouton.disabled = true;
  const avant = (await api('/etat').catch(() => null))?.version?.demarree;
  try {
    const r = await post('/mise-a-jour', {});
    if (!r.redemarre) { zone.hidden = true; return; }
  } catch (e) {
    bouton.disabled = false;
    erreur(e.statut === 404 ? t('maj.trop_ancien') : e.message);
    return;
  }
  await attendreRetour(avant);
}

export function initMaj() {
  zone = $('#maj-dispo');
  bouton = h('button', { type: 'button', class: 'btn petit primaire', onclick: mettre }, t('maj.mettre'));
  controler();
  setInterval(controler, RECONTROLE_MS);
}
