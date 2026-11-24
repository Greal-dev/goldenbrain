// Panneaux de la vue tâche (Conversation, Notes) et panneau « Notes » de l'utilisateur.
// Rôle : construire un panneau réductible (état mémorisé dans le navigateur) ; dessiner les notes datées
// (Markdown, liens [[…]]), les ajouter et les modifier par les routes /notes.
// Frontières : n'écrit que par l'API ; detail.js place les panneaux et relit la tâche après un geste.
// Invariant porté : INV-EXECUTANT-2 (les notes sont l'espace de l'utilisateur ; l'agent les lit sans les écrire).
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { rendreMd } from './md.js';
import { creerIA } from './notes_ia.js';
import { t } from './langues.js';
import { notesRepliees } from './discussion.js';

const enc = encodeURIComponent;
const CLE = 'gb.panneaux-tache';
const replis = () => { try { return JSON.parse(localStorage.getItem(CLE)) || {}; } catch { return {}; } };

// Panneau réductible d'un clic ; replié, il se réduit à une bande portant son titre (en mode discussion : un intercalaire vertical
// à droite, avec le nombre de notes). Les notes sont repliées tant que l'utilisateur ne les a pas ouvertes (INV-DISCUSSION-1).
export function panneau(nom, titre, ...contenu) {
  const bouton = h('button', { type: 'button', class: 'btn petit p-replier' });
  const compte = h('span', { class: 'p-n n', hidden: true });
  const el = h('section', { class: `volet-t volet-t-${nom}`, 'data-panneau': nom },
    h('header', { class: 'p-tete' }, h('h3', { class: 'p-titre' }, titre), compte, bouton), h('div', { class: 'p-corps' }, ...contenu));
  const poser = (replie) => {
    el.classList.toggle('replie', replie);
    bouton.textContent = replie ? t('notes_tache.deplier') : t('notes_tache.replier');
    bouton.setAttribute('aria-expanded', String(!replie));
    bouton.title = replie ? t('notes_tache.deplier_titre', { titre }) : t('notes_tache.replier_titre', { titre });
  };
  const etat = () => { const e = replis(); return nom in e ? !!e[nom] : nom === 'notes' && notesRepliees(); };
  bouton.addEventListener('click', () => {
    const e = replis(); e[nom] = !el.classList.contains('replie');
    try { localStorage.setItem(CLE, JSON.stringify(e)); } catch { /* stockage indisponible : l'état vaut pour la séance */ }
    poser(e[nom]);
  });
  el.querySelector('.p-tete').addEventListener('click', (e) => { if (el.classList.contains('replie') && !e.target.closest('button')) bouton.click(); });
  // « Tout afficher » déplie les notes ; le retour au mode discussion les replie (retour au défaut).
  const suivre = (e) => {
    if (!el.isConnected) { document.removeEventListener('gb-disposition', suivre); return; }
    if (nom === 'notes') {
      const x = replis();
      if (e.detail?.tout) x[nom] = false; else delete x[nom];
      try { localStorage.setItem(CLE, JSON.stringify(x)); } catch { /* stockage indisponible : séance */ }
    }
    poser(etat());
  };
  document.addEventListener('gb-disposition', suivre);
  poser(etat());
  el.compte = (n) => { compte.textContent = String(n); compte.hidden = !n; compte.title = t('notes_tache.compteur', { n }); };
  return el;
}

// Contenu du panneau « Notes » ; `apres()` relit la tâche après un ajout ou une modification.
export function creerNotes(apres, erreur) {
  const liste = h('div', { class: 'notes-t' });
  const ta = h('textarea', { rows: 3, 'aria-label': t('notes_tache.nouvelle'), placeholder: t('notes_tache.placeholder') });
  const ajouter = h('button', { class: 'btn primaire', type: 'submit' }, t('notes_tache.ajouter'));
  const form = h('form', { class: 'notes-ajout' }, ta, ajouter);
  let id = null, courante = null;
  const ia = creerIA(liste, () => ({ id, notes: courante?.notes || [] }), apres, erreur);
  const geste = async (fn, bouton) => {
    bouton.disabled = true;
    try { await fn(); apres(); return true; } catch (e) { erreur(e.message); return false; } finally { bouton.disabled = false; }
  };
  const envoyer = async () => {
    const texte = ta.value.trim();
    if (texte && await geste(() => post(`/taches/${enc(id)}/notes`, { texte }), ajouter)) ta.value = '';
  };
  form.addEventListener('submit', (e) => { e.preventDefault(); envoyer(); });
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); envoyer(); } });

  function editer(li, n) {
    const zone = h('textarea', { rows: Math.min(14, n.texte.split('\n').length + 1), 'aria-label': t('notes_tache.texte') });
    zone.value = n.texte;
    const ok = h('button', { class: 'btn primaire petit', type: 'button' }, t('notes_tache.enregistrer'));
    // Avant la relecture, la zone d'édition est retirée : sinon le garde de `dessiner` garderait l'ancien texte.
    ok.addEventListener('click', () => geste(async () => { await api(`/taches/${enc(id)}/notes/${n.n}`, { methode: 'PUT', corps: { texte: zone.value } }); li.querySelector('.note-edition')?.remove(); }, ok));
    const annuler = h('button', { class: 'btn petit', type: 'button', onclick: () => dessiner(courante, true) }, t('notes_tache.annuler'));
    remplacer(li, h('div', { class: 'note-edition' }, zone, h('div', { class: 'note-gestes' }, annuler, ok)));
    zone.focus();
  }

  // Une relecture (tour d'agent, flux) ne détruit pas une note en cours d'édition, sauf geste explicite.
  function dessiner(tk, force = false) {
    if (!force && tk.id === id && liste.querySelector('.note-edition')) { courante = tk; return; }
    id = tk.id; courante = tk;
    const notes = tk.notes || [];
    if (!notes.length) {
      remplacer(liste, h('p', { class: 'vide' }, t('notes_tache.vide')));
      return;
    }
    remplacer(liste, h('ol', { class: 'notes-liste' }, notes.map((n, i) => {
      const li = h('li', { class: 'note-t', 'data-n': i });
      remplacer(li,
        h('div', { class: 'note-t-tete' }, h('time', null, n.quand), n.modifiee ? h('span', { class: 'note-modif' }, t('notes_tache.modifiee', { quand: n.modifiee })) : null,
          h('button', { class: 'btn petit note-modifier', type: 'button', onclick: () => editer(li, n) }, t('notes_tache.modifier'))),
        rendreMd(h('div', { class: 'md' }), n.texte));
      return li;
    })));
  }
  return { el: h('div', { class: 'notes-panneau' }, ia.barre, ia.zone, liste, form), dessiner };
}
