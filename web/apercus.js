// Rôle : aperçus déroulants de la barre haute (INV-DEROULANT-1) — « Aujourd'hui », « Décisions », les trois pastilles de « À moi » (à valider,
// questions, à faire par vous ; INV-MAIN-4), « En cours » : cinq lignes au plus (dix pour « À valider », qui se valide en lot) et « Tout voir » vers la page pleine ; pastille « Infos » qui déroule les bandeaux d'information (poste réservé, mise à jour,
// réseau), une alerte qui exige un geste restant, elle, dans la pile des bandeaux (bandeaux.js).
// Frontières : lit GET /aujourdhui, GET /decisions et GET /main/a-moi à l'ouverture, S (arbre, état) sinon ; n'écrit que la validation en lot
// (POST /lots, annulable, geste humain) ; les bandeaux d'information
// sont dessinés par leurs modules (bandeau.js, version.js, maj-auto.js), ce module ne fait que les compter.
import { t, tn } from './langues.js';
import { h, $, remplacer, pastille, depuis } from './dom.js';
import { S, on, emit, ouvrir, ouvrirVue, erreur } from './store.js';
import { api } from './api.js';
import { libelleEcheance } from './temps.js';
import { deroulant } from './deroulant.js';

const MAX = 5, MAX_VALIDER = 10;
const versions = new WeakMap();
const choisis = new Set(); // « À valider » : la sélection survit aux redessins du panneau
let dernierLot = null;

function liste(items, vide) {
  if (!items.length) return h('p', { class: 'vide' }, vide);
  return h('ul', { class: 'apercu-liste' }, items.slice(0, MAX).map((x) => h('li', null,
    h('button', { type: 'button', 'data-id': x.id, title: x.titre, onclick: () => ouvrir(x.id) },
      x.statut ? pastille(x.statut) : null, h('span', { class: 'ap-titre' }, x.titre), h('span', { class: `ap-sous${x.retard ? ' retard' : ''}` }, x.sous || '')))));
}

// Un appel lent ne redessine pas un panneau refermé ou rouvert depuis.
async function charger(corps, d, chemin, rendre) {
  const moi = (versions.get(d) || 0) + 1;
  versions.set(d, moi);
  if (!corps.firstChild) remplacer(corps, h('p', { class: 'vide' }, t('apercus.chargement')));
  try {
    const r = await api(chemin);
    if (moi === versions.get(d) && d.ouvert()) remplacer(corps, rendre(r));
  } catch (e) { erreur(e.message); }
}

function lignesAujourdhui(r) {
  const vus = new Set(), l = [];
  for (const g of r.groupes) for (const x of g.taches) if (!vus.has(x.id)) { vus.add(x.id); l.push({ ...x, sous: libelleEcheance(x.echeance, x.retard) || g.titre }); }
  return l;
}
const lignesDecisions = (r) => r.decisions.map((x) => ({ id: x.tache, titre: x.titre, statut: x.statut, sous: x.libelle }));
const lignesMoi = (cle) => (r) => r[cle].map((x) => ({ ...x, sous: x.depuis || x.phrase }));

// « À valider » : cases à cocher, « Valider la sélection » (POST /lots, un seul lot, annulable), survol = résultat et essai.
function listeValider(items, d) {
  const vus = new Set(items.map((x) => x.id));
  for (const i of choisis) if (!vus.has(i)) choisis.delete(i);
  const vue = items.slice(0, MAX_VALIDER);
  const bouton = h('button', { type: 'button', class: 'btn primaire petit', 'data-id': 'valider-selection', disabled: choisis.size ? null : '', onclick: () => validerSelection(d) }, t('apercus.valider_selection'));
  const lignes = vue.map((x) => h('li', null,
    h('input', { type: 'checkbox', class: 'ap-case', 'data-id': x.id, 'aria-label': t('lot.case', { titre: x.titre }), ...(choisis.has(x.id) ? { checked: '' } : {}),
      onchange: (e) => { if (e.target.checked) choisis.add(x.id); else choisis.delete(x.id); bouton.disabled = !choisis.size; } }),
    h('button', { type: 'button', 'data-id': x.id, title: [x.resultat && t('aujourdhui.resultat', { valeur: x.resultat }), x.essai && t('aujourdhui.essai', { valeur: x.essai })].filter(Boolean).join('\n') || x.titre, onclick: () => ouvrir(x.id) },
      pastille(x.statut), h('span', { class: 'ap-titre' }, x.titre), h('span', { class: 'ap-sous' }, x.sous || ''))));
  return h('div', { class: 'ap-valider' }, dernierLot ? h('p', { class: 'lot-etat', role: 'status' }, tn('apercus.valide', dernierLot.n),
      h('button', { type: 'button', class: 'btn petit', 'data-id': 'valider-annuler', onclick: () => annulerValidation(d) }, t('lot.annuler'))) : null,
    items.length ? [h('ul', { class: 'apercu-liste' }, lignes), h('div', { class: 'ap-pied' }, bouton)] : h('p', { class: 'vide' }, t('apercus.rien_a_valider')));
}
async function validerSelection(d) {
  const taches = [...choisis];
  if (!taches.length) return;
  try {
    const r = await api('/lots', { methode: 'POST', corps: { taches, statut: 'cloture' } });
    dernierLot = { lot: r.lot, n: r.changees.length };
  } catch (e) { return erreur(e.message); }
  choisis.clear(); emit('recharger-arbre'); d.redessiner();
}
async function annulerValidation(d) {
  const lot = dernierLot?.lot;
  dernierLot = null;
  if (lot) try { await api(`/lots/${lot}/annuler`, { methode: 'POST' }); } catch (e) { erreur(e.message); }
  emit('recharger-arbre'); d.redessiner();
}
const enCours = () => [...(S.etat.tours || []).map((x) => ({ id: x.tache, titre: x.titre, sous: depuis(x.depuis) })),
  ...(S.etat.file || []).map((f) => ({ id: f.tache, titre: f.titre, sous: t('apercus.en_file') }))];

// Infos : compteur des bandeaux d'information visibles ; « alerte » si l'un demande un geste (réseau perdu, serveur à redémarrer).
function compterInfos(d) {
  const vus = [...$('#panneau-etat').querySelectorAll(':scope > [role="status"]')].filter((el) => !el.hidden);
  const b = $('#btn-etat');
  b.hidden = !vus.length;
  $('#n-etat').textContent = String(vus.length);
  b.classList.toggle('alerte', vus.some((el) => ['reseau-perdu', 'maj-serveur'].includes(el.id)));
  if (!vus.length) d.fermer(); // plus rien à dire : un panneau vide, même épinglé, ne reste pas ouvert
}

export function initApercus() {
  const tv = t('apercus.tout_voir');
  const auj = deroulant({ bouton: $('#btn-aujourdhui'), panneau: $('#panneau-aujourdhui'), titre: t('apercus.aujourdhui'),
    toutVoir: { libelle: tv, agir: () => ouvrirVue('aujourdhui') },
    remplir: (c) => charger(c, auj, '/aujourdhui', (r) => liste(lignesAujourdhui(r), t('apercus.rien_aujourdhui'))) });
  const dec = deroulant({ bouton: $('#btn-decisions'), panneau: $('#panneau-decisions'), titre: t('apercus.decisions'),
    toutVoir: { libelle: tv, agir: () => ouvrirVue('decisions') },
    remplir: (c) => charger(c, dec, '/decisions', (r) => liste(lignesDecisions(r), t('apercus.rien_decisions'))) });
  const filtrer = { libelle: t('apercus.filtrer_arbre'), agir: () => { S.filtreAMoi = true; emit('filtre'); } };
  const moi = {}; // INV-MAIN-4 : trois pastilles, chacune sa liste, la plus ancienne d'abord
  for (const [cle, bouton, panneau, titre, vide] of [['valider', '#btn-avalider', '#panneau-avalider', 'apercus.a_valider', 'apercus.rien_a_valider'],
    ['question', '#btn-questions', '#panneau-questions', 'apercus.questions', 'apercus.rien_questions'], ['faire', '#btn-afaire', '#panneau-afaire', 'apercus.a_faire', 'apercus.rien_a_faire']]) {
    const d = moi[cle] = deroulant({ bouton: $(bouton), panneau: $(panneau), titre: t(titre), toutVoir: filtrer,
      remplir: (c) => charger(c, d, '/main/a-moi', cle === 'valider' ? (r) => listeValider(lignesMoi(cle)(r), d) : (r) => liste(lignesMoi(cle)(r), t(vide))) });
  }
  const trav = deroulant({ bouton: $('#btn-travaux'), panneau: $('#panneau-travaux'), titre: t('apercus.en_cours'),
    toutVoir: { libelle: tv, agir: () => ouvrirVue('travaux') },
    remplir: (c) => remplacer(c, liste(enCours(), t('apercus.rien_en_cours'))) });
  on('etat', () => { trav.redessiner(); for (const d of Object.values(moi)) d.redessiner(); });
  on('arbre', () => { for (const d of Object.values(moi)) d.redessiner(); });
  const infos = deroulant({ bouton: $('#btn-etat'), panneau: $('#panneau-etat'), titre: t('apercus.infos'), garder: true });
  new MutationObserver(() => compterInfos(infos)).observe($('#panneau-etat'), { subtree: true, attributes: true, attributeFilter: ['hidden'] });
  compterInfos(infos);
}
