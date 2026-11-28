// Rôle : volet droit — lecture d'une note (fil d'Ariane, propriétés, corps rendu, liens entrants, boutons).
// Frontières : API GET /vault/note, GET /vault/mentions (mentions non liées, INV-NOTE-4, chargées à la demande), POST /validation-auto/reglage (contexte de projet, INV-VALID-2) ; l'édition est déléguée à note-edition.js ; le rendu Markdown à md.js.
// Performance : le corps est rendu en une passe (une seule affectation d'innerHTML), jamais ligne par ligne.
import { h, remplacer, heure, dossierDe, nomDe } from './dom.js';
import { S, on, ouvrir, ouvrirNote, ouvrirGraphe, erreur, chemin as cheminArbre } from './store.js';
import { api, post } from './api.js';
import { rendreMd } from './md.js';
import { voirDossier } from './notes.js';
import { editer, enEdition, signalerChangement, enregistrementRecent } from './note-edition.js';
import { nouvelleNote, deplacerNote, deplacerDisponible } from './note-gestes.js';
import { reduire } from './transfo.js';
import { creerChat } from './notes_chat.js';
import { t } from './langues.js';

const enc = encodeURIComponent;
const FRONT = /^﻿?---[ \t]*\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)/;
let racine = null, note = null, chemin = null, ref = {}, ancien = null, chat = null;

const valeur = (v) => (Array.isArray(v) ? v.map(valeur).join(', ') : v && typeof v === 'object' ? JSON.stringify(v) : String(v ?? ''));

function contexte(n) {
  const liens = new Map();
  for (const l of n.liens || []) {
    const k = String(l.cible || '').toLowerCase();
    if (k && typeof liens.get(k) !== 'string') liens.set(k, l.chemin ?? null); // un lien résolu l'emporte sur un doublon « à créer »
  }
  return { liens, depuis: dossierDe(n.chemin) };
}

function fil(n) {
  const parts = n.chemin.split('/').slice(0, -1);
  const crumb = (txt, c) => h('span', null, h('button', { class: 'crumb', type: 'button', title: t('note_vue.dossier_titre', { nom: txt }), onclick: () => voirDossier(c) }, txt));
  return h('nav', { class: 'fil', 'aria-label': t('note_vue.fil_aria') }, crumb(t('note_vue.vault'), ''), parts.map((p, i) => crumb(p, parts.slice(0, i + 1).join('/'))));
}

// `contexte.md` : la note du projet (conteneur) dont elle porte le dossier.
const estContexte = () => nomDe(note.chemin) === 'contexte.md' && dossierDe(note.chemin) !== '';
function surReduire() {
  const id = dossierDe(note.chemin);
  const noeud = cheminArbre(S.arbre, (n) => n.type === 'conteneur' && n.id === id)?.at(-1);
  reduire({ id, titre: noeud?.titre || nomDe(id) });
}

function surSupprimer() { import('./suppression.js').then((m) => m.supprimer({ conteneur: dossierDe(note.chemin) })); }

// INV-VALID-2 : le réglage de validation du projet est l'accord écrit de l'utilisateur, tracé dans le contexte.
function reglageValidation() {
  const conteneur = dossierDe(note.chemin);
  const mode = String(note.frontmatter?.validation || '').toLowerCase();
  const choix = h('select', { 'aria-label': t('note_vue.validation_aria'), 'data-validation': '' },
    h('option', { value: '' }, t('note_vue.validation_heritee')),
    h('option', { value: 'manuelle' }, t('note_vue.validation_manuelle')),
    h('option', { value: 'automatique' }, t('note_vue.validation_automatique')));
  choix.value = ['manuelle', 'automatique'].includes(mode) ? mode : '';
  choix.onchange = async () => {
    const v = choix.value;
    if (!v || (v === 'automatique' && !confirm(t('note_vue.confirmer_auto')))) { choix.value = mode; return; }
    try { await post('/validation-auto/reglage', { conteneur, mode: v }); await dessinerNote(racine, note.chemin); } catch (e) { erreur(e.message); choix.value = mode; }
  };
  return h('label', { class: 'n-validation', title: note.frontmatter?.validation_accord || t('note_vue.cloture_titre') }, choix);
}

function barreLecture() {
  const b = (txt, f, o = {}) => h('button', { class: `btn petit${o.cls ? ` ${o.cls}` : ''}`, type: 'button', onclick: f, title: o.titre || null }, txt);
  remplacer(ref.barre,
    b(t('note_vue.modifier'), demarrerEdition, { titre: t('note_vue.modifier_titre') }),
    b(t('note_vue.nouvelle'), () => nouvelleNote(dossierDe(note.chemin)), { titre: t('note_vue.nouvelle_titre') }),
    deplacerDisponible() ? b(t('note_vue.deplacer'), surDeplacer) : null,
    estContexte() ? b(t('note_vue.reduire'), surReduire, { titre: t('note_vue.reduire_titre') }) : null,
    estContexte() ? b(t('cascade.supprimer'), surSupprimer, { cls: 'danger', titre: t('cascade.supprimer_titre') }) : null,
    estContexte() ? reglageValidation() : null,
    b(t('note_vue.graphe'), () => ouvrirGraphe(note.chemin), { titre: t('note_vue.graphe_titre') }),
    note.tache ? b(t('note_vue.ouvrir_tache'), () => ouvrir(note.tache), { cls: 'primaire', titre: t('note_vue.ouvrir_tache_titre') }) : null,
    h('span', { class: 'n-maj', title: note.maj || null }, note.maj ? t('note_vue.modifiee', { heure: heure(note.maj) }) : ''));
}

function proprietes(n) {
  const cles = Object.keys(n.frontmatter || {});
  if (!cles.length) return null;
  return h('details', { class: 'n-props', open: localStorage.getItem('orch.note.props') !== '0' ? true : null,
    ontoggle: (e) => localStorage.setItem('orch.note.props', e.target.open ? '1' : '0') },
  h('summary', null, t('note_vue.proprietes', { n: cles.length })),
  h('table', { class: 'n-props-t' }, h('tbody', null, cles.map((k) => h('tr', null, h('th', { scope: 'row' }, k), h('td', null, valeur(n.frontmatter[k])))))));
}

function entrants(n) {
  const l = n.entrants || [];
  return h('section', { class: 'n-entrants', 'aria-label': t('note_vue.entrants_aria') }, h('h3', null, t('note_vue.entrants', { n: l.length })),
    l.length ? h('ul', null, l.map((e) => h('li', null,
      h('button', { class: 'lien-titre', type: 'button', onclick: () => ouvrirNote(e.chemin), title: e.chemin }, e.titre || e.chemin),
      h('span', { class: 'n-chemin' }, e.chemin),
      e.extrait ? h('span', { class: 'n-extrait' }, e.extrait) : null))) : h('p', { class: 'vide' }, t('note_vue.aucune_entrante')));
}

// INV-NOTE-4 : les notes qui citent le titre sans le lier ; repliées et chargées seulement à l'ouverture (coût d'un balayage).
function mentions(n) {
  const liste = h('div', null);
  return h('details', { class: 'n-mentions', ontoggle: async (e) => {
    if (!e.target.open || liste.dataset.charge) return;
    liste.dataset.charge = '1';
    remplacer(liste, h('p', { class: 'vide' }, t('note_vue.recherche')));
    try {
      const l = await api(`/vault/mentions?chemin=${enc(n.chemin)}`);
      remplacer(liste, l.length ? h('ul', null, l.map((m) => h('li', null,
        h('button', { class: 'lien-titre', type: 'button', onclick: () => ouvrirNote(m.chemin), title: m.chemin }, m.titre || m.chemin),
        h('span', { class: 'n-chemin' }, m.chemin), h('span', { class: 'n-extrait' }, m.extrait)))) : h('p', { class: 'vide' }, t('note_vue.aucune_mention')));
    } catch (x) { delete liste.dataset.charge; remplacer(liste, h('p', { class: 'vide' }, x.message)); }
  } }, h('summary', null, h('h3', null, t('note_vue.mentions'))), liste);
}

function afficher(defilement = 0) {
  ref = {};
  chat ||= creerChat(() => note, (n) => { note = n; afficher(ref.defile?.scrollTop || 0); }, erreur); // une barre par note ouverte : sa proposition survit au rendu
  ref.barre = h('div', { class: 'n-barre', role: 'toolbar', 'aria-label': t('note_vue.barre_aria') });
  ref.md = h('div', { class: 'md note-md' });
  ref.defile = h('div', { class: 'n-defile' }, proprietes(note), ref.md, entrants(note), mentions(note));
  ref.zone = h('div', { class: 'n-zone' }, ref.defile);
  remplacer(racine, h('div', { class: 'vue-note' }, h('div', { class: 'd-tete' }, fil(note), h('h2', { class: 'd-titre' }, note.titre || note.nom), ref.barre), ref.zone, chat));
  rendreMd(ref.md, String(note.contenu || '').replace(FRONT, ''), contexte(note));
  barreLecture();
  ref.defile.scrollTop = defilement;
}

function demarrerEdition() {
  chat.hidden = true; // pas de retouche IA pendant l'édition à la main
  editer({ note, zone: ref.zone, barre: ref.barre, surFin: (n) => { if (n) note = n; chat.hidden = false; afficher(); ref.barre.querySelector('button')?.focus(); } });
}
async function surDeplacer() {
  ancien = note.chemin; // le déplacement signale l'ancien chemin par SSE : ce n'est pas une suppression « ailleurs »
  setTimeout(() => { ancien = null; }, 3000);
  const n = await deplacerNote(note);
  if (n) ouvrirNote(n.chemin);
}

function absente(c, e) {
  return h('div', { class: 'note-absente' }, h('h2', null, t('note_vue.absente_titre')), h('p', null, h('code', null, c)),
    h('p', { class: 'vide' }, t('note_vue.absente_suite', { erreur: e.message })),
    h('button', { class: 'btn', type: 'button', onclick: () => voirDossier(dossierDe(c)) }, t('note_vue.voir_dossier')));
}

export async function dessinerNote(el, c) {
  racine = el; chemin = c; note = null; chat = null;
  remplacer(el, h('p', { class: 'vide' }, t('note_vue.chargement')));
  try {
    const n = await api(`/vault/note?chemin=${enc(c)}`);
    if (chemin !== c) return;
    note = n;
    afficher();
    if (S.editer) { S.editer = false; demarrerEdition(); }
  } catch (e) { if (chemin === c) remplacer(el, absente(c, e)); }
}

// SSE `note` : relecture silencieuse si la note ouverte n'est pas en cours d'édition ; sinon, avertissement.
export async function evtNote(e) {
  if (!note || S.vue !== 'note' || S.selection || e.chemin !== note.chemin || e.chemin === ancien) return;
  if (enEdition()) { if (!enregistrementRecent()) signalerChangement(); return; }
  const c = note.chemin;
  try {
    const n = await api(`/vault/note?chemin=${enc(c)}`);
    if (!note || n.chemin !== note.chemin || n.mtime_ns === note.mtime_ns || enEdition()) return;
    note = n;
    afficher(ref.defile?.scrollTop || 0);
  } catch (x) {
    if (note?.chemin !== c) return; // on a navigué ailleurs entre-temps
    if (x.statut === 404) remplacer(racine, absente(c, x)); else erreur(x.message);
  }
}

export function initNoteVue() {
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'e' || e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
    if (S.vue !== 'note' || S.selection || !note || enEdition() || !ref.zone?.isConnected) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
    if (document.querySelector('dialog[open]')) return;
    e.preventDefault();
    demarrerEdition();
  });
  on('note-deplacer-ko', () => { if (note && ref.barre?.isConnected && !enEdition()) barreLecture(); });
}
