// Rôle : modification en bloc des tâches de la vue principale — cases à cocher, sélection par étendue (Maj+clic),
// « tout sélectionner » (tâches affichées seulement), barre d'action, confirmation avec récapitulatif, annulation en un clic.
// Frontières : l'état de sélection est local à l'affichage ; tout changement passe par POST /api/lots (tout ou rien,
// tâches occupées exclues par le serveur, INV-LOT-1) ; aucune sélection ne survit à ce qui n'est plus affiché.
import { t, tn } from './langues.js';
import { h, remplacer, libelleStatut, ORDRE_STATUTS } from './dom.js';
import { api } from './api.js';
import { erreur, emit } from './store.js';

const sel = new Set();
let ancre = null, barre = null, tete = null, visibles = () => [], brouillon = { statut: '', echeance: '' }, recap = null, dernier = null, recapIA = null, consigneIA = '';

const ids = () => visibles().map((c) => c.dataset.id);
function pousser() { majLot(); }

export function caseLigne(n) {
  const c = h('input', { type: 'checkbox', class: 'c-sel', 'data-id': n.id, 'aria-label': t('lot.case', { titre: n.titre }), ...(sel.has(n.id) ? { checked: '' } : {}) });
  c.addEventListener('click', (e) => {
    e.stopPropagation();
    const tous = ids();
    if (e.shiftKey && ancre && tous.includes(ancre)) { // étendue entre la dernière case cochée et celle-ci
      const [a, b] = [tous.indexOf(ancre), tous.indexOf(n.id)].sort((x, y) => x - y);
      for (const i of tous.slice(a, b + 1)) { if (c.checked) sel.add(i); else sel.delete(i); }
      for (const x of visibles()) x.checked = sel.has(x.dataset.id);
    } else if (c.checked) sel.add(n.id); else sel.delete(n.id);
    ancre = n.id; recap = recapIA = null;
    pousser();
  });
  return c;
}
export function basculerSel(id) {
  if (sel.has(id)) sel.delete(id); else sel.add(id);
  ancre = id; recap = null;
  for (const x of visibles()) if (x.dataset.id === id) x.checked = sel.has(id);
  pousser();
}
export function caseTout(fournisseur) {
  visibles = fournisseur;
  tete = h('input', { type: 'checkbox', class: 'c-sel-tout', 'aria-label': t('lot.tout'), title: t('lot.tout'),
    onclick: (e) => { e.stopPropagation(); const v = tete.checked; for (const c of visibles()) { c.checked = v; if (v) sel.add(c.dataset.id); else sel.delete(c.dataset.id); } recap = null; pousser(); } });
  return tete;
}

async function apercu() {
  if (!brouillon.statut && !brouillon.echeance) return erreur(t('lot.rien'), 'info');
  try {
    const r = await api('/lots', { methode: 'POST', corps: { taches: [...sel], ...corpsChangement(), apercu: true } });
    recap = r;
  } catch (e) { return erreur(e.message); }
  majLot();
}
const corpsChangement = () => ({ ...(brouillon.statut ? { statut: brouillon.statut } : {}), ...(brouillon.echeance ? { echeance: brouillon.echeance } : {}) });
async function appliquer() {
  try {
    const r = await api('/lots', { methode: 'POST', corps: { taches: [...sel], ...corpsChangement() } });
    dernier = { lot: r.lot, n: r.changees.length, exclues: r.exclues, annule: null };
  } catch (e) { return erreur(e.message); }
  sel.clear(); recap = null; brouillon = { statut: '', echeance: '' }; ancre = null;
  for (const c of visibles()) c.checked = false;
  emit('recharger-arbre'); majLot();
}
// « Confier / Renvoyer à l'IA » en bloc (INV-MAIN-5) : aperçu, puis envoi en file ; les tâches occupées ou sans attente de l'IA sont ignorées.
async function apercuIA() {
  try { recapIA = await api('/lots/ia', { methode: 'POST', corps: { taches: [...sel], apercu: true } }); } catch (e) { return erreur(e.message); }
  majLot();
}
async function envoyerIA() {
  try {
    const r = await api('/lots/ia', { methode: 'POST', corps: { taches: [...sel], consigne: consigneIA } });
    dernier = { lot: null, n: r.envoyees.length, exclues: r.exclues, annule: null, ia: true };
  } catch (e) { return erreur(e.message); }
  sel.clear(); recap = recapIA = null; consigneIA = ''; ancre = null;
  for (const c of visibles()) c.checked = false;
  emit('recharger-arbre'); majLot();
}
async function annuler() {
  const lot = dernier.lot;
  try {
    const r = await api(`/lots/${lot}/annuler`, { methode: 'POST' });
    dernier = { ...dernier, annule: r };
  } catch (e) { return erreur(e.message); }
  emit('recharger-arbre'); majLot();
}

const noms = (l) => l.map((x) => x.titre).join(', ');
function contenu() {
  if (!sel.size) {
    if (!dernier) return [];
    if (dernier.annule) return [h('span', { class: 'lot-etat' }, t('lot.annule')), dernier.annule.ignorees.length ? h('span', { class: 'lot-note' }, t('lot.ignorees', { liste: noms(dernier.annule.ignorees) })) : null, fermer()];
    return [h('span', { class: 'lot-etat', role: 'status' }, tn(dernier.ia ? 'lot.ia_fait' : 'lot.fait', dernier.n)),
      dernier.exclues.length ? h('span', { class: 'lot-note' }, t('lot.exclues', { liste: noms(dernier.exclues) })) : null,
      dernier.ia ? null : h('button', { type: 'button', class: 'btn petit', id: 'lot-annuler', onclick: annuler }, t('lot.annuler')), fermer()];
  }
  const compte = h('span', { class: 'lot-n', role: 'status', 'aria-live': 'polite' }, tn('lot.n_selection', sel.size));
  if (recapIA) {
    return [compte, h('span', { class: 'lot-recap', id: 'lot-ia-recap' }, tn('lot.ia_n', recapIA.envoyees.length)),
      recapIA.exclues.length ? h('span', { class: 'lot-note' }, t('lot.exclues', { liste: noms(recapIA.exclues) })) : null,
      h('input', { type: 'text', class: 'lot-ia-consigne', id: 'lot-ia-consigne', 'aria-label': t('main.consigne'), placeholder: t('main.consigne'), value: consigneIA, oninput: (e) => { consigneIA = e.target.value; } }),
      recapIA.envoyees.length ? h('button', { type: 'button', class: 'btn primaire', id: 'lot-ia-confirmer', onclick: envoyerIA }, t('lot.ia_confirmer')) : null,
      h('button', { type: 'button', class: 'btn petit', onclick: () => { recapIA = null; majLot(); } }, t('lot.retour'))];
  }
  if (recap) {
    const vers = [brouillon.statut ? libelleStatut(brouillon.statut) : null, brouillon.echeance ? t('lot.vers_echeance', { date: brouillon.echeance }) : null].filter(Boolean).join(', ');
    const de = Object.entries(recap.de).map(([s, k]) => `${k} ${libelleStatut(s)}`).join(', ');
    return [compte, h('span', { class: 'lot-recap', id: 'lot-recap' }, `${tn('lot.n_taches', recap.retenues.length)} : ${de} → ${vers}`),
      recap.exclues.length ? h('span', { class: 'lot-note' }, t('lot.exclues', { liste: noms(recap.exclues) })) : null,
      recap.retenues.length ? h('button', { type: 'button', class: 'btn primaire', id: 'lot-confirmer', onclick: appliquer }, t('lot.confirmer')) : null,
      h('button', { type: 'button', class: 'btn petit', onclick: () => { recap = null; majLot(); } }, t('lot.retour'))];
  }
  const choix = h('select', { id: 'lot-statut', 'aria-label': t('lot.statut'), onchange: () => { brouillon.statut = choix.value; } },
    h('option', { value: '' }, t('lot.garder')), ORDRE_STATUTS.map((s) => h('option', { value: s, ...(s === brouillon.statut ? { selected: '' } : {}) }, libelleStatut(s))));
  const date = h('input', { type: 'date', id: 'lot-echeance', 'aria-label': t('lot.echeance'), value: brouillon.echeance, onchange: () => { brouillon.echeance = date.value; } });
  return [compte, choix, date, h('button', { type: 'button', class: 'btn primaire', id: 'lot-appliquer', onclick: apercu }, t('lot.appliquer')),
    h('button', { type: 'button', class: 'btn', id: 'lot-ia', title: t('lot.ia_titre'), onclick: apercuIA }, t('lot.ia')),
    h('button', { type: 'button', class: 'btn petit', onclick: () => { sel.clear(); recap = recapIA = null; for (const c of visibles()) c.checked = false; majLot(); } }, t('lot.vider'))];
}
const fermer = () => h('button', { type: 'button', class: 'btn-discret', 'aria-label': t('lot.fermer'), onclick: () => { dernier = null; majLot(); } }, '×');

export const barreLot = () => { barre = h('div', { class: 'lot-barre', role: 'region', 'aria-label': t('lot.barre'), hidden: true }); return barre; };
// Rien d'invisible n'est modifié : une tâche repliée ou filtrée quitte la sélection.
export function majLot() {
  if (!barre) return;
  const vis = new Set(ids());
  for (const i of sel) if (!vis.has(i)) sel.delete(i);
  if (tete) { const k = vis.size ? [...vis].filter((i) => sel.has(i)).length : 0; tete.checked = k > 0 && k === vis.size; tete.indeterminate = k > 0 && k < vis.size; }
  if (recap && recap.retenues.length + recap.exclues.length !== sel.size) recap = null;
  if (recapIA && recapIA.envoyees.length + recapIA.exclues.length !== sel.size) recapIA = null;
  const c = contenu();
  barre.hidden = !c.length;
  remplacer(barre, c);
}
