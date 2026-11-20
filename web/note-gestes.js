// Rôle : gestes sur les notes qui passent par un formulaire — créer, renommer / déplacer.
// Frontières : API /vault/note ; ouvre le résultat par store.ouvrirNote ; 501 sur le déplacement = fonction absente du serveur (bouton masqué).
import { S, emit, erreur, ouvrirNote } from './store.js';
import { post } from './api.js';
import { formulaire } from './dialogue.js';
import { dossierDe, nomDe } from './dom.js';
import { t, tn } from './langues.js';

const INTERDITS = '[^\\\\\\/:*?"<>\\|]+'; // \ / : * ? " < > | (forme compatible avec le drapeau v de l'attribut pattern)
let deplacerIndisponible = false;
export const deplacerDisponible = () => !deplacerIndisponible;

export async function nouvelleNote(dossier = '', nom = '') {
  const v = await formulaire({
    titre: t('note_gestes.nouvelle_titre'), valider: t('note_gestes.creer'),
    champs: [
      { nom: 'nom', label: t('note_gestes.nom_label'), requis: true, valeur: nom, motif: INTERDITS, aide: t('note_gestes.interdits_aide') },
      { nom: 'dossier', label: t('note_gestes.dossier_label'), valeur: dossier },
    ],
  });
  if (!v) return null;
  try {
    const note = await post('/vault/note', { dossier: v.dossier.trim().replace(/^\/+|\/+$/g, ''), nom: v.nom.trim().replace(/\.md$/i, '') });
    emit('note-ecrite', note.chemin);
    ouvrirNote(note.chemin, true);
    return note;
  } catch (e) { erreur(e.message); return null; }
}

// Lien « à créer » : le dossier est celui de la cible si elle en porte un, sinon celui de la note ouverte.
export function creerDepuisLien(cible) {
  const dossier = cible.includes('/') ? dossierDe(cible) : (S.note ? dossierDe(S.note) : '');
  return nouvelleNote(dossier, nomDe(cible).replace(/\.md$/i, ''));
}

// Renvoie la note déplacée, ou null (annulé, refusé, ou route absente : 501).
export async function deplacerNote(note) {
  const v = await formulaire({
    titre: t('note_gestes.deplacer_titre'), valider: t('note_gestes.deplacer'), texte: t('note_gestes.deplacer_texte'),
    champs: [{ nom: 'vers', label: t('note_gestes.chemin_label'), valeur: note.chemin, requis: true }],
  });
  if (!v || v.vers.trim() === note.chemin) return null;
  try {
    const r = await post('/vault/note/deplacer', { chemin: note.chemin, vers: v.vers.trim().replace(/^\/+/, '') });
    emit('note-ecrite', note.chemin);
    emit('note-ecrite', r.note.chemin);
    if (r.fichiers_reecrits) erreur(tn('note_gestes.reecrits', r.fichiers_reecrits), 'info');
    return r.note;
  } catch (e) {
    if (e.statut === 501) { deplacerIndisponible = true; erreur(t('note_gestes.indisponible'), 'info'); emit('note-deplacer-ko'); } else erreur(e.message);
    return null;
  }
}
