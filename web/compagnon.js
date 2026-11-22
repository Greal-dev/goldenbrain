// Rôle : vue « Accueil » du compagnon mobile — à décider, en cours, arbre allégé, lus dans l'instantané (GET /compagnon/instantane).
// Frontières : lecture, plus UN geste d'écriture (jalon 2) : valider ou renvoyer une tâche à valider, par les routes existantes
//        /taches/{id}/valider|renvoyer, en ligne seulement et après confirmation ; le reste passe par les écrans existants.
//        INV-PWA-2 : le seul stockage local est l'instantané léger, en IndexedDB, si le serveur le permet (`hors_ligne`) ET que
//        l'utilisateur l'a coché sur cet appareil ; durée bornée par `ttl_s`, effacé sur 401 (appareil révoqué) ou sur demande.
import { h, remplacer, pastille } from './dom.js';
import { post } from './api.js';
import { formulaire } from './dialogue.js';
import { ouvrir, ouvrirVue, on, erreur } from './store.js';
import { libelleEcheance } from './temps.js';
import { t, tn } from './langues.js';

const BASE = 'gb-compagnon', CLE = 'orch.compagnon.hors_ligne';
let envoi = null, message = null, effaceMessage = 0;   // geste en cours (tâche) ; dernier retour visible {ok, texte}
let coque = null, etat = { donnees: null, hors_ligne_actuel: false, verifie: null }, parent = null, version = 0;

// --- stockage local (opt-in) ------------------------------------------------------------------
const ouvrirBase = () => new Promise((ok, ko) => {
  const q = indexedDB.open(BASE, 1);
  q.onupgradeneeded = () => q.result.createObjectStore('i');
  q.onsuccess = () => ok(q.result); q.onerror = () => ko(q.error);
});
async function banque(mode, fn) {
  const b = await ouvrirBase();
  return new Promise((ok, ko) => { const r = fn(b.transaction('i', mode).objectStore('i')); r.onsuccess = () => { b.close(); ok(r.result); }; r.onerror = () => { b.close(); ko(r.error); }; });
}
const lireLocal = () => banque('readonly', (s) => s.get('dernier')).catch(() => null);
const ecrireLocal = (v) => banque('readwrite', (s) => s.put(v, 'dernier')).catch(() => {});
export const effacerLocal = () => banque('readwrite', (s) => s.clear()).catch(() => {});
const perime = (d) => !d || Date.now() > Date.parse(d.genere) + d.ttl_s * 1000;
const voulu = () => localStorage.getItem(CLE) === '1';

// --- lecture -----------------------------------------------------------------------------------
async function charger() {
  const local = voulu() ? await lireLocal() : null;
  const garde = local && !perime(local) ? local : null;
  try {
    const r = await fetch('/api/compagnon/instantane', { headers: garde ? { 'If-None-Match': `"${garde.empreinte}"` } : {} });
    if (r.status === 401) { await effacerLocal(); throw new Error('401'); }
    if (r.status === 304 && garde) etat = { donnees: garde, enligne: true, verifie: new Date() };
    else if (r.ok) {
      const d = await r.json();
      etat = { donnees: d, enligne: true, verifie: new Date() };
      if (d.hors_ligne && voulu()) await ecrireLocal(d); else await effacerLocal(); // le serveur retire la permission : rien ne reste
    } else throw new Error(String(r.status));
  } catch {
    etat = { donnees: garde, enligne: false, verifie: garde ? new Date(garde.genere) : null };
  }
}

// --- affichage ---------------------------------------------------------------------------------
const heureCourte = (d) => d.toLocaleString(undefined, { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' });

function ouvrirTache(id) { if (etat.enligne) ouvrir(id); }

// Retour immédiat et visible (jalon 2) : « envoi… » sur les boutons, puis bandeau de confirmation ou d'erreur dans la vue ;
// la décision quitte la liste dès la réussite, sans attendre le rafraîchissement.
function annoncer(ok, texte) {
  message = { ok, texte }; clearTimeout(effaceMessage);
  if (ok) effaceMessage = setTimeout(() => { message = null; if (coque?.isConnected) dessiner(); }, 6000);
}

async function geste(d, fn, reussi) {
  if (envoi) return;
  envoi = d.tache; message = null; dessiner();
  try {
    await fn();
    etat.donnees.decisions = etat.donnees.decisions.filter((x) => x.tache !== d.tache);
    annoncer(true, t(reussi, { titre: d.titre }));
  } catch (e) { annoncer(false, t('compagnon.echec', { titre: d.titre, erreur: e.message })); }
  envoi = null; dessiner();
  await actualiser();
}

async function valider(d) {
  const v = await formulaire({ titre: t('compagnon.valider_titre', { titre: d.titre }), texte: t('compagnon.valider_texte'), valider: t('decisions.valider'), focus: 'annuler' });
  if (v) await geste(d, () => post(`/taches/${d.tache}/valider`, {}), 'compagnon.valide');
}

async function renvoyer(d) {
  const v = await formulaire({ titre: t('decisions.refuser_titre', { titre: d.titre }), valider: t('decisions.renvoyer'),
    champs: [{ nom: 'texte', label: t('decisions.motif_renvoi'), type: 'textarea', requis: true }] });
  if (v) await geste(d, () => post(`/taches/${d.tache}/renvoyer`, { texte: v.texte.trim() }), 'compagnon.renvoye');
}

function carteDecision(d) {
  const enCours = envoi === d.tache;
  const actions = d.genre === 'validation' && etat.enligne ? h('div', { class: 'co-actions' },
    h('button', { type: 'button', class: 'btn primaire', disabled: !!envoi, 'aria-busy': enCours ? 'true' : null, onclick: () => valider(d) },
      enCours ? t('compagnon.envoi') : t('decisions.valider')),
    h('button', { type: 'button', class: 'btn', disabled: !!envoi, onclick: () => renvoyer(d) }, t('decisions.renvoyer'))) : null;
  return h('li', null, h('button', { class: 'co-carte', type: 'button', disabled: !etat.enligne, onclick: () => ouvrirTache(d.tache) },
    h('span', { class: 'co-genre' }, d.libelle), h('span', { class: 'co-titre' }, d.titre),
    d.question ? h('span', { class: 'co-q' }, d.question) : null,
    h('span', { class: `co-meta${d.retard ? ' retard' : ''}` }, [d.projet, libelleEcheance(d.echeance, d.retard)].filter(Boolean).join(' · '))), actions);
}

function ligneNoeud(n) {
  const dossier = n.type !== 'tache';
  return h('li', null, h('button', { class: 'co-ligne', type: 'button', disabled: !dossier && !etat.enligne,
    onclick: () => { if (dossier) { parent = `${n.type}:${n.id}`; dessiner(); } else ouvrirTache(n.id); } },
    dossier ? h('span', { class: 'co-dossier', 'aria-hidden': 'true' }, '▸') : pastille(n.statut),
    h('span', { class: 'co-titre' }, n.titre),
    n.a_valider ? h('span', { class: 'tag' }, t('compagnon.a_valider')) : null,
    dossier && n.ouvertes ? h('span', { class: 'n' }, n.ouvertes) : h('span', { class: `co-meta${n.retard ? ' retard' : ''}` }, libelleEcheance(n.echeance, n.retard))));
}

function fil(arbre) {
  const par = new Map(arbre.map((n) => [`${n.type}:${n.id}`, n]));
  const chaine = [];
  for (let k = parent; k && par.has(k);) { chaine.unshift(par.get(k)); k = par.get(k).parent; }
  return chaine;
}

function sectionArbre(arbre) {
  const chaine = fil(arbre), enfants = arbre.filter((n) => n.parent === parent);
  const retour = parent && chaine.length ? h('button', { class: 'co-retour', type: 'button', onclick: () => { parent = chaine.at(-1).parent; dessiner(); } },
    '‹ ', chaine.map((n) => n.titre).join(' › ')) : null;
  return h('section', { class: 'co-section' }, h('h3', null, t('compagnon.arbre')), retour,
    enfants.length ? h('ul', { class: 'co-liste' }, enfants.map(ligneNoeud)) : h('p', { class: 'vide' }, t('compagnon.vide')),
    etat.donnees.tronque ? h('p', { class: 'vide' }, t('compagnon.tronque')) : null);
}

function reglage() {
  if (!etat.donnees?.hors_ligne) return null;   // le poste n'a pas autorisé le stockage local : aucune option
  const c = h('input', { type: 'checkbox', checked: voulu() });
  c.addEventListener('change', async () => { localStorage.setItem(CLE, c.checked ? '1' : '0'); if (!c.checked) await effacerLocal(); await actualiser(); });
  return h('section', { class: 'co-section co-reglage' }, h('label', null, c, ' ', t('compagnon.garder')),
    h('p', { class: 'vide' }, t('compagnon.garder_aide')),
    h('button', { type: 'button', class: 'btn', onclick: async () => { await effacerLocal(); localStorage.setItem(CLE, '0'); await actualiser(); } }, t('compagnon.effacer')));
}

function dessiner() {
  const { donnees: d, enligne, verifie } = etat;
  const etatLigne = h('div', { class: `co-etat${enligne ? '' : ' hors'}`, role: 'status' },
    h('span', { class: 'co-point', 'aria-hidden': 'true' }),
    enligne ? t('compagnon.connecte', { heure: verifie ? heureCourte(verifie) : '' }) : d ? t('compagnon.injoignable', { date: heureCourte(new Date(d.genere)) }) : t('compagnon.rien_hors_ligne'),
    h('button', { type: 'button', class: 'btn-discret', onclick: actualiser, 'aria-label': t('compagnon.actualiser') }, '⟳'));
  const bandeau = message ? h('div', { class: `co-retour-geste ${message.ok ? 'ok' : 'ko'}`, role: message.ok ? 'status' : 'alert' }, message.texte,
    h('button', { type: 'button', class: 'btn-discret', 'aria-label': t('compagnon.fermer'), onclick: () => { message = null; dessiner(); } }, '×')) : null;
  if (!d) return remplacer(coque, h('h2', { class: 'casc-titre' }, t('compagnon.titre')), etatLigne);
  remplacer(coque, h('h2', { class: 'casc-titre' }, t('compagnon.titre')), etatLigne, bandeau,
    h('section', { class: 'co-section' }, h('h3', null, t('compagnon.a_decider'), ' ', h('span', { class: 'n' }, d.decisions.length)),
      d.decisions.length ? h('ul', { class: 'co-liste' }, d.decisions.map(carteDecision)) : h('p', { class: 'vide' }, t('compagnon.rien_a_decider')),
      enligne && d.decisions.length ? h('button', { type: 'button', class: 'btn', onclick: () => ouvrirVue('decisions') }, t('compagnon.tout_traiter')) : null),
    h('section', { class: 'co-section' }, h('h3', null, t('compagnon.en_cours'), ' ', h('span', { class: 'n' }, d.travaux.tours.length)),
      d.travaux.tours.length ? h('ul', { class: 'co-liste' }, d.travaux.tours.map((x) => h('li', null, h('button', { class: 'co-ligne', type: 'button', disabled: !enligne, onclick: () => ouvrirTache(x.tache) },
        h('span', { class: 'co-titre' }, x.titre), h('span', { class: 'co-meta' }, x.projet))))) : h('p', { class: 'vide' }, t('compagnon.rien_en_cours')),
      d.travaux.en_file ? h('p', { class: 'co-meta' }, tn('compagnon.en_file', d.travaux.en_file)) : null),
    sectionArbre(d.arbre), reglage());
}

async function actualiser() {
  const v = ++version;
  await charger();
  if (v === version && coque?.isConnected) dessiner();
}

export function dessinerCompagnon(racine) {
  coque = h('div', { class: 'compagnon' });
  remplacer(racine, coque);
  dessiner();
  actualiser();
}

let minuterie = 0;
for (const nom of ['arbre', 'props']) on(nom, () => { // flux d'événements existant : rien ne tourne quand la vue est fermée
  if (!coque?.isConnected) return;
  clearTimeout(minuterie); minuterie = setTimeout(actualiser, 800);
});
