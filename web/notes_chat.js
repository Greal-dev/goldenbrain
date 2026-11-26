// Barre de chat IA sous la note ouverte (vue Notes) : créer une tâche depuis la note, reformuler, réorganiser, résumer, consigne libre.
// Rôle : demander une proposition (POST /vault/note/ia), l'afficher ; une tâche s'ouvre dans le formulaire « Nouvelle tâche »
// prérempli (titre, description liée à la note, projet déduit) ; une retouche s'applique par PUT /vault/note sur « Appliquer »
// seulement, et reste annulable (réécriture de la version d'origine).
// Frontières : rien n'est écrit sans geste ; le texte de la note ne part qu'au modèle du rôle `notes` (INV-NOTECHAT-1).
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { rendreMd } from './md.js';
import { difference } from './notes_ia.js';
import { t } from './langues.js';

const FRONT = /^﻿?---[ \t]*\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)/;
const GESTES = [['tache', t('notes_chat.tache')], ['reformuler', t('notes_chat.reformuler')], ['reorganiser', t('notes_chat.reorganiser')], ['resumer', t('notes_chat.resumer')]];
const LIBELLE = Object.fromEntries([...GESTES, ['libre', t('notes_chat.libre')]]);

// `etat()` : la note affichée { chemin, contenu, mtime_ns } ; `surNote(n)` : la note vient d'être réécrite ; `erreur(msg)`.
export function creerChat(etat, surNote, erreur) {
  const zone = h('div', { class: 'chat-zone', 'aria-live': 'polite' });
  const champ = h('input', { type: 'text', class: 'chat-champ', 'data-chat': 'consigne', maxlength: 2000,
    placeholder: t('notes_chat.placeholder'), 'aria-label': t('notes_chat.champ_aria') });
  const fermer = () => remplacer(zone);
  let seq = 0;

  async function ecrire(contenu, bouton) {
    bouton.disabled = true;
    try { surNote(await api('/vault/note', { methode: 'PUT', corps: { chemin: etat().chemin, contenu, mtime_ns: etat().mtime_ns } })); return true; }
    catch (e) { erreur(e.message); bouton.disabled = false; return false; }
  }

  function tete(action, r) {
    const cout = r.cout == null ? t('notes_chat.cout_inconnu') : t('notes_chat.cout', { cout: r.cout.toFixed(4) });
    return h('div', { class: 'ia-tete' }, h('b', null, LIBELLE[action]), h('span', { class: 'ia-cout' }, `${cout} · ${r.harnais}${r.modele ? ' / ' + r.modele : ''}`));
  }
  const bouton = (txt, f, cls = '') => h('button', { class: `btn petit ${cls}`.trim(), type: 'button', onclick: f }, txt);

  function montrerTache(r) {
    const creer = async () => {
      const { nouvelleTache } = await import('./bandeau.js');
      fermer();
      nouvelleTache({ titre: r.titre, description: r.description, conteneur: r.conteneur });
    };
    remplacer(zone, h('div', { class: 'ia-prop', 'data-chat': 'tache' }, tete('tache', r), h('p', null, h('b', null, r.titre)),
      rendreMd(h('div', { class: 'md' }), r.description),
      h('div', { class: 'note-gestes' }, bouton(t('notes_chat.refuser'), fermer), bouton(t('notes_chat.creer_tache'), creer, 'primaire'))));
  }

  function montrerRetouche(action, r) {
    const avant = etat().contenu;
    const appliquer = async (b) => {
      const front = (avant.match(FRONT) || [''])[0];
      if (!(await ecrire(front + r.proposition + (avant.endsWith('\n') ? '\n' : ''), b))) return;
      const annuler = bouton(t('notes_chat.annuler_modif'), async () => { if (await ecrire(avant, annuler)) fermer(); });
      remplacer(zone, h('div', { class: 'ia-fait', 'data-chat': 'fait' }, h('span', null, t('notes_chat.appliquee')), annuler, bouton(t('notes_chat.fermer'), fermer)));
    };
    const ok = bouton(t('notes_chat.appliquer'), () => appliquer(ok), 'primaire');
    remplacer(zone, h('div', { class: 'ia-prop', 'data-chat': 'retouche' }, tete(action, r),
      difference(r.original, r.proposition) || rendreMd(h('div', { class: 'md' }), r.proposition),
      h('div', { class: 'note-gestes' }, bouton(t('notes_chat.refuser'), fermer), ok)));
  }

  async function lancer(action) {
    const consigne = champ.value.trim();
    if (action === 'libre' && !consigne) { champ.focus(); return; }
    const mon = ++seq;
    const n = etat();
    remplacer(zone, h('div', { class: 'ia-prop' }, h('div', { class: 'ia-tete' }, h('b', null, LIBELLE[action]), h('span', null, t('notes_chat.en_cours')))));
    try {
      const r = await post('/vault/note/ia', { chemin: n.chemin, action, consigne });
      if (mon !== seq || etat().chemin !== n.chemin) return; // une demande plus récente, ou une autre note
      champ.value = '';
      if (r.erreur) remplacer(zone, h('div', { class: 'ia-prop' }, tete(action, r), h('p', { class: 'erreur' }, r.erreur), h('div', { class: 'note-gestes' }, bouton(t('notes_chat.fermer'), fermer))));
      else if (action === 'tache') montrerTache(r); else montrerRetouche(action, r);
    } catch (e) { if (mon === seq) { fermer(); erreur(e.message); } }
  }

  champ.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); lancer('libre'); } });
  const barre = h('div', { class: 'chat-barre', role: 'toolbar', 'aria-label': t('notes_chat.barre') },
    h('div', { class: 'chat-gestes' }, ...GESTES.map(([a, lib]) => h('button', { class: 'btn petit', type: 'button', 'data-chat-geste': a, onclick: () => lancer(a) }, lib))),
    h('div', { class: 'chat-saisie' }, champ, bouton(t('notes_chat.envoyer'), () => lancer('libre'), 'primaire')));
  return h('div', { class: 'chat-note' }, zone, barre);
}
