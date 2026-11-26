// Rôle : volet gauche, onglets « Tâches » / « Notes » et arborescence des dossiers du vault (un niveau par requête).
// Frontières : API /vault/dossier ; ouvre une note par store.ouvrirNote, un dossier en tableau par store.ouvrirVue('base') ; ne rend jamais le contenu d'une note.
// Performance : chaque dossier n'est lu qu'une fois (cache) ; l'événement SSE `note` relit seulement les dossiers ancêtres.
import { h, $, remplacer, nomDe } from './dom.js';
import { S, on, ouvrirNote, ouvrirGraphe, ouvrirVue, fixerOnglet, erreur } from './store.js';
import { ouvert } from './interface.js';
import { api } from './api.js';
import { t, tn } from './langues.js';
import { nouvelleNote } from './note-gestes.js';

const CLE = 'orch.notes.ouverts';
const enc = encodeURIComponent;
let ouverts = (() => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch { return {}; } })();
const cache = new Map(), enVol = new Map();
let cont, visibles = [], cleFocus = null, courant = '', minuteur = 0;
const sauver = () => localStorage.setItem(CLE, JSON.stringify(ouverts));
const ancetres = (chemin) => chemin.split('/').slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join('/'));

function charger(chemin, force = false) {
  if (!ouvert('notes')) return Promise.resolve({ dossiers: [], notes: [] }); // la route répondrait 409
  if (!force && cache.has(chemin)) return Promise.resolve(cache.get(chemin));
  if (enVol.has(chemin)) return enVol.get(chemin);
  const p = api(`/vault/dossier?chemin=${enc(chemin)}`).then((d) => { cache.set(chemin, d); return d; }).finally(() => enVol.delete(chemin));
  enVol.set(chemin, p);
  return p;
}
const sûr = async (fn) => { try { await fn(); } catch (e) { erreur(e.message); } };
// Charge, niveau par niveau, les dossiers ouverts (mémorisés) qui ne sont pas encore en cache.
async function completer() {
  for (let k = 0; k < 8; k++) {
    const manquants = aplatir('', 0, []).filter((v) => v.type === 'attente').map((v) => v.k.slice(2));
    if (!manquants.length) return;
    await Promise.all(manquants.map((c) => charger(c).catch(() => { delete ouverts[c]; sauver(); }))); // dossier disparu : on l'oublie sans bruit
  }
}

function aplatir(chemin, niveau, out) {
  const d = cache.get(chemin);
  if (!d) { out.push({ type: 'attente', niveau, k: `a:${chemin}` }); return out; }
  for (const f of d.dossiers) {
    out.push({ type: 'dossier', niveau, k: `d:${f.chemin}`, f });
    if (ouverts[f.chemin]) aplatir(f.chemin, niveau + 1, out);
  }
  for (const n of d.notes) out.push({ type: 'note', niveau, k: `n:${n.chemin}`, n });
  return out;
}
const noteOuverte = () => (S.vue === 'note' && !S.selection ? S.note : null);

function ligne(v) {
  const pad = `padding-left:${8 + v.niveau * 14}px`;
  if (v.type === 'attente') return h('div', { class: 'ligne attente', role: 'none', style: pad }, t('notes.chargement'));
  if (v.type === 'dossier') {
    const o = !!ouverts[v.f.chemin];
    return h('div', { class: `ligne t-dossier${v.f.chemin === courant ? ' courant' : ''}`, role: 'treeitem', 'data-k': v.k, 'aria-level': v.niveau + 1,
      'aria-expanded': String(o), 'aria-label': tn('notes.dossier_aria', v.f.notes, { nom: v.f.nom }), tabindex: v.k === cleFocus ? '0' : '-1', style: pad },
    h('span', { class: `chev${o ? ' ouvert' : ''}`, 'aria-hidden': 'true' }),
    h('span', { class: 'titre', title: v.f.chemin }, v.f.nom),
    h('span', { class: 'compte', title: tn('notes.compte_titre', v.f.notes) }, v.f.notes),
    h('button', { class: 't-base', type: 'button', tabindex: '-1', 'data-id': 'voir-tableau', title: t('base.voir'), 'aria-label': t('base.voir_aria', { nom: v.f.nom }) }, '▦'));
  }
  const sel = v.n.chemin === noteOuverte();
  return h('div', { class: `ligne t-note${sel ? ' sel' : ''}`, role: 'treeitem', 'data-k': v.k, 'aria-level': v.niveau + 1, 'aria-selected': String(sel),
    tabindex: v.k === cleFocus ? '0' : '-1', style: pad },
  h('span', { class: 'chev vide', 'aria-hidden': 'true' }),
  h('span', { class: 'titre', title: `${v.n.titre || v.n.nom}\n${v.n.chemin}` }, v.n.nom));
}

function dessiner() {
  if (!cont) return;
  const top = cont.scrollTop;
  const actif = cont.contains(document.activeElement) ? document.activeElement.dataset.k : null;
  visibles = aplatir('', 0, []);
  if (!visibles.some((v) => v.k === cleFocus)) cleFocus = (visibles.find((v) => v.type === 'note' && v.n.chemin === noteOuverte()) || visibles.find((v) => v.k))?.k ?? null;
  remplacer(cont, visibles.map(ligne), cache.size && !visibles.length ? h('p', { class: 'vide' }, t('notes.aucune')) : null);
  cont.scrollTop = top;
  if (actif) cont.querySelector(`[data-k="${CSS.escape(actif)}"]`)?.focus({ preventScroll: true });
  $('#notes-dossier').textContent = courant ? nomDe(courant) : t('notes.racine');
  $('#notes-dossier').title = courant || t('notes.racine_titre');
}

// Ouvre les dossiers ancêtres d'un chemin (lecture un par un), puis surligne et fait défiler.
async function reveler(chemin, dossier = false) {
  const chaine = dossier ? [...ancetres(`${chemin}/x`)] : ancetres(chemin);
  await sûr(async () => {
    await charger('');
    for (const a of chaine) { ouverts[a] = true; await charger(a); }
  });
  sauver();
  const k = dossier ? `d:${chemin}` : `n:${chemin}`;
  cleFocus = k;
  dessiner();
  cont.querySelector(`[data-k="${CSS.escape(k)}"]`)?.scrollIntoView({ block: 'nearest' });
}
export function voirDossier(chemin) {
  courant = chemin;
  fixerOnglet('notes');
  if (!chemin) { dessiner(); return; }
  ouverts[chemin] = true; sauver();
  reveler(chemin, true);
}
export const dossierCourant = () => courant;

async function basculer(f) {
  ouverts[f.chemin] = !ouverts[f.chemin];
  courant = f.chemin;
  sauver();
  if (ouverts[f.chemin]) await sûr(() => charger(f.chemin));
  dessiner();
}

function surTouche(e) {
  const rows = [...cont.querySelectorAll('[role=treeitem]')];
  const i = rows.indexOf(document.activeElement);
  if (i < 0) return;
  const v = visibles.find((x) => x.k === rows[i].dataset.k);
  const niv = +rows[i].getAttribute('aria-level');
  const aller = (j) => { if (rows[j]) { rows[j].focus(); e.preventDefault(); } };
  switch (e.key) {
    case 'ArrowDown': return aller(i + 1);
    case 'ArrowUp': return aller(i - 1);
    case 'Home': return aller(0);
    case 'End': return aller(rows.length - 1);
    case 'ArrowRight':
      e.preventDefault();
      if (v.type === 'dossier') { if (!ouverts[v.f.chemin]) basculer(v.f); else rows[i + 1]?.focus(); }
      return;
    case 'ArrowLeft':
      e.preventDefault();
      if (v.type === 'dossier' && ouverts[v.f.chemin]) basculer(v.f);
      else for (let j = i - 1; j >= 0; j--) if (+rows[j].getAttribute('aria-level') < niv) { rows[j].focus(); break; }
      return;
    case 't': if (v.type === 'dossier') { e.preventDefault(); ouvrirVue('base', v.f.chemin); } return; // « Voir en tableau » au clavier
    case 'Enter': case ' ':
      e.preventDefault();
      if (v.type === 'note') ouvrirNote(v.n.chemin); else basculer(v.f);
  }
}

// Après une écriture (SSE `note`) : seuls les dossiers déjà lus et ancêtres de la note sont relus.
export function evtNote(e) {
  const touches = ['', ...ancetres(e.chemin || '')].filter((c) => cache.has(c));
  clearTimeout(minuteur);
  minuteur = setTimeout(async () => { await sûr(() => Promise.all(touches.map((c) => charger(c, true)))); dessiner(); }, 300);
}
export async function actualiser() {
  const l = [...cache.keys()];
  cache.clear();
  await sûr(() => Promise.all(l.map((c) => charger(c, true))));
  await completer();
  dessiner();
}

function majOnglets() {
  const n = S.onglet === 'notes';
  for (const [id, actif] of [['#onglet-taches', !n], ['#onglet-notes', n]]) {
    const b = $(id);
    b.setAttribute('aria-selected', String(actif));
    b.tabIndex = actif ? 0 : -1;
  }
  $('#pan-taches').hidden = n;
  $('#pan-notes').hidden = !n;
  $('#volet-gauche').setAttribute('aria-label', n ? t('notes.volet_notes') : t('notes.volet_taches'));
}

export function initNotes() {
  cont = $('#notes-arbre');
  for (const id of ['taches', 'notes']) $(`#onglet-${id}`).addEventListener('click', () => fixerOnglet(id));
  $('#onglets').addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const o = S.onglet === 'notes' ? 'taches' : 'notes'; fixerOnglet(o); $(`#onglet-${o}`).focus(); }
  });
  on('onglet', () => { majOnglets(); if (S.onglet === 'notes') charger('').then(completer).then(dessiner, (e) => erreur(e.message)); });
  $('#btn-note-neuve').addEventListener('click', () => nouvelleNote(courant));
  $('#btn-note-actu').addEventListener('click', actualiser);
  $('#btn-graphe').addEventListener('click', () => ouvrirGraphe(null));
  cont.addEventListener('keydown', surTouche);
  cont.addEventListener('focusin', (e) => {
    const k = e.target.dataset?.k;
    if (!k || k === cleFocus) return;
    cont.querySelector('[tabindex="0"]')?.setAttribute('tabindex', '-1');
    e.target.setAttribute('tabindex', '0');
    cleFocus = k;
  });
  cont.addEventListener('click', (e) => {
    const row = e.target.closest('[data-k]');
    const v = row && visibles.find((x) => x.k === row.dataset.k);
    if (!v) return;
    cleFocus = v.k;
    if (v.type === 'dossier' && e.target.closest('.t-base')) { ouvrirVue('base', v.f.chemin); return; } // INV-BASES-1 : vue en lecture seule
    if (v.type === 'note') ouvrirNote(v.n.chemin); else basculer(v.f);
    row.focus?.();
  });
  on('note-ecrite', (chemin) => evtNote({ chemin }));
  on('selection', () => {
    if (S.vue === 'note' && !S.selection && S.note) {
      courant = S.note.includes('/') ? S.note.slice(0, S.note.lastIndexOf('/')) : '';
      reveler(S.note);
    } else dessiner();
  });
  majOnglets();
  if (S.onglet === 'notes' || noteOuverte()) charger('').then(completer).then(() => { if (noteOuverte()) reveler(S.note); else dessiner(); }, (e) => erreur(e.message));
}
