// Rôle : champ de recherche du bandeau — filtre de l'arbre des tâches (existant) + liste déroulante à deux groupes
// (tâches : arbre en mémoire ; notes : GET /vault/recherche, anti-rebond 200 ms). Entrée = page de résultats plein texte.
// Frontières : lit S.arbre ; ouvre par store ; la page de résultats est dans resultats.js.
import { t } from './langues.js';
import { h, $, remplacer, pastille } from './dom.js';
import { S, emit, ouvrir, ouvrirNote, ouvrirRecherche, parcourir } from './store.js';
import { ouvert } from './interface.js';
import { api } from './api.js';
import { focaliser } from './arbre.js';

const norm = (s) => (s || '').normalize('NFD').replace(/\p{M}/g, '').toLowerCase();
let champ, liste, items = [], actif = -1, notes = [], notesKO = '', chargement = false, seq = 0, minuteur = 0;

function tachesLocal(q) {
  const mots = norm(q).split(/\s+/).filter(Boolean);
  const r = [];
  for (const n of parcourir(S.arbre)) {
    if (n.type === 'tache' && mots.every((m) => norm(n.titre).includes(m))) { r.push(n); if (r.length >= 6) break; }
  }
  return r;
}
function fermer() { liste.hidden = true; champ.setAttribute('aria-expanded', 'false'); champ.removeAttribute('aria-activedescendant'); actif = -1; }

function choisir(it) {
  fermer();
  if (it.type === 'tache') ouvrir(it.id); else ouvrirNote(it.chemin);
}
function marquer() {
  [...liste.querySelectorAll('[role=option]')].forEach((li, i) => { li.setAttribute('aria-selected', String(i === actif)); li.classList.toggle('actif', i === actif); });
  if (actif >= 0) { champ.setAttribute('aria-activedescendant', `rech-${actif}`); liste.querySelector(`#rech-${actif}`)?.scrollIntoView({ block: 'nearest' }); } else champ.removeAttribute('aria-activedescendant');
}

function dessiner() {
  const q = champ.value.trim();
  if (!q) { fermer(); return; }
  const taches = tachesLocal(q);
  items = [...taches.map((n) => ({ type: 'tache', id: n.id })), ...notes.map((n) => ({ type: 'note', chemin: n.chemin }))];
  actif = Math.min(actif, items.length - 1);
  const opt = (i, ...contenu) => h('li', { id: `rech-${i}`, role: 'option', 'aria-selected': 'false', onmousedown: (e) => { e.preventDefault(); choisir(items[i]); } }, contenu);
  const g = (titre, ...enfants) => h('li', { role: 'presentation', class: 'rech-groupe' }, h('div', { class: 'rech-g-titre' }, titre), h('ul', { role: 'group', 'aria-label': titre }, enfants));
  remplacer(liste,
    g(t('recherche.taches'), taches.length ? taches.map((n, i) => opt(i, pastille(n.statut), h('span', { class: 'res-titre' }, n.titre))) : h('li', { class: 'rech-vide' }, t('recherche.aucune_tache'))),
    g(t('recherche.notes'), notes.length ? notes.map((n, i) => {
      const x = n.extraits?.[0];
      return opt(taches.length + i, h('span', { class: 'res-titre' }, n.titre || n.chemin), h('span', { class: 'fil-mini' }, n.chemin), x ? h('span', { class: 'rech-extrait' }, x.texte) : null);
    }) : h('li', { class: 'rech-vide' }, notesKO || (chargement ? t('recherche.en_cours') : t('recherche.aucune_note')))),
    h('li', { role: 'presentation', class: 'rech-pied' }, t('recherche.pied')));
  liste.hidden = false;
  champ.setAttribute('aria-expanded', 'true');
  marquer();
}

function chercherNotes() {
  const q = champ.value.trim();
  clearTimeout(minuteur);
  if (!q || !ouvert('notes')) { notes = []; return; }
  chargement = true;
  minuteur = setTimeout(async () => {
    const mon = ++seq;
    try { const r = await api(`/vault/recherche?q=${encodeURIComponent(q)}&limite=8`); if (mon !== seq) return; notes = r; notesKO = ''; } catch (e) { if (mon !== seq) return; notes = []; notesKO = t('recherche.indisponible'); }
    chargement = false;
    dessiner();
  }, 200);
}

export function initRecherche() {
  champ = $('#recherche');
  liste = $('#rech-liste');
  champ.addEventListener('input', () => {
    S.recherche = champ.value; emit('filtre');
    actif = -1;
    chercherNotes(); dessiner();
  });
  champ.addEventListener('focus', () => { if (champ.value.trim()) dessiner(); });
  champ.addEventListener('keydown', (e) => {
    const ouverte = !liste.hidden;
    if (e.key === 'Escape') {
      if (ouverte) { e.preventDefault(); fermer(); e.stopPropagation(); return; } // preventDefault : sinon le champ de type search se vide
      champ.value = ''; S.recherche = ''; emit('filtre'); focaliser();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (ouverte && items.length) { actif = (actif + 1) % items.length; marquer(); } else focaliser();
    } else if (e.key === 'ArrowUp' && ouverte && items.length) {
      e.preventDefault(); actif = (actif - 1 + items.length) % items.length; marquer();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const q = champ.value.trim();
      if (ouverte && actif >= 0 && items[actif]) choisir(items[actif]);
      else if (q) { fermer(); ouvrirRecherche(q); }
    }
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('.rech-zone')) fermer(); });
  champ.addEventListener('blur', () => setTimeout(() => { if (!liste.contains(document.activeElement)) fermer(); }, 120));
}
// La page de résultats garde son terme dans le champ (retour arrière du navigateur compris).
export function fixerTerme(q) { champ.value = q; S.recherche = q; emit('filtre'); fermer(); }
