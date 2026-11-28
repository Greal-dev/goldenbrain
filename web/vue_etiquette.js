// Rôle : page « Vue par étiquette » (#etiquette=<mot>) — tâches et routines qui portent le mot, avec leur dernier résultat ; « Lancer toutes les routines ».
//        « Nouvelle étiquette » et « Trouver les tâches » (etiquette_trouver.js, chargé au clic, INV-ETIQUETTE-5).
// Frontières : lit GET /etiquettes/<mot>/vue (une requête, INV-ETIQUETTE-4) ; n'écrit que par POST /routines/<id>/executer (existante) ;
//            chargée à la demande (app.js, INV-REACTIVITE-1) ; styles existants de « Aujourd'hui » et « En cours », aucune feuille nouvelle.
import { t, tn } from './langues.js';
import { h, remplacer, heure, libelleStatut, filLisible } from './dom.js';
import { api, post } from './api.js';
import { ouvrir, ouvrirVue, erreur } from './store.js';
import { charger, pret } from './paresseux.js';

const enc = encodeURIComponent;
let coque = null, mot = null, version = 0, bilan = '', panneau = null;

function trouver() {
  if (!panneau?.isConnected) {
    panneau = h('section', { class: 'etiq-trouver', 'data-id': 'etiq-trouver-panneau' });
    coque.querySelector('[data-id="etiq-gestes"]')?.after(panneau);
  }
  const ici = panneau, moi = mot;
  charger('etiquette_trouver').then((m) => { if (ici === panneau) m.remplir(ici, moi, recharger); }, (e) => erreur(e.message));
}
const nouvelle = () => charger('etiquette_trouver').then((m) => m.nouvelleEtiquette(), (e) => erreur(e.message));

const issue = (d) => (d ? `${t(`vue_etiquette.issue_${d.issue}`)} ${heure(d.a)}` : t('vue_etiquette.jamais'));

function infosRoutine(r) {
  return h('span', { class: 'tr-raison', 'data-id': 'etiq-routine' },
    [r.programme, r.en_pause ? t('vue_etiquette.en_pause') : null, t('vue_etiquette.derniere', { quand: issue(r.derniere) }),
      r.prochaine && !r.en_pause ? t('vue_etiquette.prochaine', { quand: heure(r.prochaine) }) : null].filter(Boolean).join(' · '));
}

async function executer(x) {
  try { await post(`/routines/${enc(x.id)}/executer`); } catch (e) { erreur(e.message); }
  await recharger();
}

async function toutLancer(routines) {
  const libres = routines.filter((x) => !x.routine.en_cours);
  const r = await Promise.allSettled(libres.map((x) => post(`/routines/${enc(x.id)}/executer`)));
  const lancees = r.filter((x) => x.status === 'fulfilled').length; // un 409 (déjà en cours) compte comme sautée
  bilan = t('vue_etiquette.bilan', { lancees, sautees: routines.length - lancees });
  await recharger();
}

function ligne(x) {
  const r = x.routine;
  return h('li', { class: 'vue-etiq-ligne', 'data-id': 'etiq-ligne', 'data-tache': x.id },
    h('button', { class: 'au-ligne tr-ligne lien-titre', type: 'button', 'data-id': 'etiq-titre', onclick: () => ouvrir(x.id) },
      h('span', { class: 'au-titre', title: x.titre }, x.titre),
      h('span', { class: 'au-place' }, filLisible(x.fil).join(' › ')), h('span', { class: 'etiq-st' }, libelleStatut(x.statut))),
    r ? h('div', null, infosRoutine(r), ' ',
      h('button', { class: 'btn petit', type: 'button', 'data-id': 'etiq-executer', disabled: r.en_cours ? '' : null, onclick: () => executer(x) },
        r.en_cours ? t('vue_etiquette.en_cours') : t('vue_etiquette.executer'))) : null,
    h('p', { class: 'au-date', 'data-id': 'etiq-resultat', title: x.resultat || null },
      x.phrase || t('vue_etiquette.sans_resultat'), x.maj ? h('span', { class: 'tr-raison' }, ` · ${t('vue_etiquette.maj', { date: x.maj })}`) : null),
    x.autres.length ? h('span', { class: 'etiq-puces' }, x.autres.map((m) => h('button', { type: 'button', class: 'etiq retirable', 'data-etiquette': m,
      title: t('vue_etiquette.puce_titre', { mot: m }), onclick: () => ouvrirVue('etiquette', m) }, `#${m}`))) : null);
}

function dessiner(d) {
  const routines = d.taches.filter((x) => x.routine);
  remplacer(coque, h('h2', { class: 'casc-titre' }, d.mot === 'recent' ? t('etiquettes.recent') : t('vue_etiquette.titre', { mot: d.mot })),
    d.consigne ? h('p', { class: 'au-date' }, d.consigne) : null,
    h('p', { 'data-id': 'etiq-gestes' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'etiq-trouver', onclick: trouver }, t('etiq_trouver.bouton')), ' ',
      h('button', { class: 'btn', type: 'button', 'data-id': 'etiq-nouvelle', onclick: nouvelle }, t('etiq_trouver.nouvelle'))),
    panneau?.isConnected ? panneau : null, // fermé (retiré) : il ne revient pas au prochain dessin
    routines.length ? h('p', null, h('button', { class: 'btn primaire', type: 'button', 'data-id': 'etiq-tout-lancer', onclick: () => toutLancer(routines) }, t('vue_etiquette.tout_lancer', { n: routines.length })), bilan ? h('span', { class: 'tr-raison', 'data-id': 'etiq-bilan', role: 'status' }, ` ${bilan}`) : null) : null,
    d.taches.length ? h('ul', { class: 'au-liste' }, d.taches.map(ligne)) : h('p', { class: 'vide' }, t('vue_etiquette.vide')),
    h('p', { class: 'aide' }, tn('lot.n_taches', d.taches.length)));
  if (!panneau?.isConnected && pret('etiquette_trouver')?.prendre(d.mot)) trouver(); // étiquette tout juste créée : étape 2 d'emblée
}

async function recharger() {
  if (!coque?.isConnected) return;
  const moi = ++version;
  try {
    const d = await api(`/etiquettes/${enc(mot)}/vue`);
    if (moi === version && coque.isConnected) dessiner(d);
  } catch (e) { erreur(e.message); }
}

export async function dessinerVueEtiquette(zone, nom) {
  if (nom !== mot) { bilan = ''; panneau = null; }
  mot = nom;
  if (!coque || coque.parentNode !== zone) {
    coque = h('div', { class: 'aujourdhui', 'data-id': 'vue-etiquette' }, h('p', { class: 'vide' }, '…'));
    remplacer(zone, coque);
  }
  await recharger();
}
