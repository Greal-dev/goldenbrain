// Rôle : gestes de la page « Email » qui ouvrent un dialogue — compositeur (répondre, répondre à tous, transférer ; l'envoi est le clic
//        « Envoyer »), « Créer une tâche » (directement le dialogue « Nouvelle tâche » du bandeau, titre = objet, consigne par défaut, encart du mail joint), « Associer à une tâche » (tâche, consigne facultative) et
//        « Masquer » (retire de la boîte sans supprimer, « Annuler » le remet) ; `actionsLigne` : les trois gestes d'une ligne de liste.
// Frontières : POST /api/mail/envoyer, /tache, /archiver et /restaurer ; la création passe par le dialogue « Nouvelle tâche » existant, dont le « Lancer »
//        est différé jusqu'à ce que le mail soit rangé (INV-MAIL-2 : le premier tour reçoit le mail comme donnée, avec l'instruction).
import { t } from './langues.js';
import { h } from './dom.js';
import { api, post } from './api.js';
import { S, parcourir, chemin, erreur, emit, ouvrir } from './store.js';
import { formulaire } from './dialogue.js';
import { nouvelleTache } from './bandeau.js';
import { filLisible } from './dom.js';

const enc = encodeURIComponent;
const FERMES = new Set(['fait', 'cloture', 'abandonne']);
const TITRES = { repondre: 'mail.repondre', repondre_tous: 'mail.repondre_tous', transferer: 'mail.transferer' };

export async function composer(mode, vue, m) {
  let b;
  try { b = await api(`/mail/brouillon?mode=${mode}&vue=${enc(vue)}&uid=${m.uid}`); } catch (e) { erreur(e.message); return; }
  const v = await formulaire({
    titre: t(TITRES[mode]), valider: t('mail.envoyer'), large: true, texte: t('mail.envoi_aide'),
    champs: [
      { nom: 'a', label: t('mail.a'), requis: true, valeur: b.a },
      { nom: 'cc', label: t('mail.cc'), valeur: b.cc },
      { nom: 'objet', label: t('mail.objet'), valeur: b.objet },
      { nom: 'texte', label: t('mail.message'), type: 'textarea', lignes: 10 },
    ],
  });
  if (!v) return;
  try {
    await post('/mail/envoyer', { mode, vue, uid: m.uid, a: v.a, cc: v.cc, objet: v.objet, texte: v.texte });
    erreur(t('mail.envoye'), 'info');
  } catch (e) { erreur(e.message); }
}

function tachesOuvertes() {
  const r = [];
  for (const n of parcourir(S.arbre || [])) {
    if (n.type !== 'tache' || FERMES.has(n.statut)) continue;
    r.push({ valeur: n.id, libelle: n.titre, groupe: filLisible(chemin(S.arbre, (x) => x === n).slice(0, -1).map((x) => x.titre)).join(' › ') });
  }
  return r;
}

// INV-MAIL-8 : masquer n'efface rien (déplacement vers « Tous les messages ») ; l'annulation retrouve le mail par son Message-ID.
export async function masquer(vue, m) {
  let r;
  try { r = await post('/mail/archiver', { vue, uid: m.uid }); } catch (e) { erreur(e.message); return; }
  emit('mail-change', { masque: m.uid });
  const annuler = async () => {
    try { await post('/mail/restaurer', { message_id: r.message_id }); emit('mail-change', {}); erreur(t('mail.remis'), 'info'); } catch (e) { erreur(e.message); }
  };
  erreur(t('mail.masque'), 'info', r.message_id ? { libelle: t('mail.annuler'), fn: annuler } : null);
}

export const masquable = (vue) => vue === 'inbox' || vue === 'non-lus';

/** Gestes d'une ligne de liste, visibles au survol (toujours sur écran tactile) ; hors du bouton de la ligne, jamais dedans. */
export function actionsLigne(vue, m) {
  const g = (cle, court, id, f) => h('button', { type: 'button', class: 'btn petit', 'data-id': id, title: t(cle), 'aria-label': t(cle), onclick: f }, t(court));
  return h('div', { class: 'mail-actions' },
    masquable(vue) ? g('mail.archiver', 'mail.archiver', 'mail-ligne-masquer', () => masquer(vue, m)) : null,
    g('mail.creer_tache', 'mail.tache_court', 'mail-ligne-creer', () => versTache(vue, m, true)),
    g('mail.rattacher', 'mail.associer_court', 'mail-ligne-associer', () => versTache(vue, m, false)));
}

export async function versTache(vue, m, creer) {
  let cible, consigne = '';
  if (creer) {
    cible = await nouvelleTache({ titre: m.objet || t('mail.sans_objet'), description: t('mail.consigne_defaut'), differer: true, encart: t('mail.encart', { objet: m.objet || t('mail.sans_objet'), de: m.de }) });
    if (!cible) return;
    consigne = cible.description || '';
  } else {
    const v = await formulaire({
      titre: t('mail.rattacher'), valider: t('mail.rattacher'), texte: t('mail.tache_aide'),
      champs: [{ nom: 'tache', label: t('mail.tache'), type: 'select', valeur: S.selection, options: tachesOuvertes() },
        { nom: 'consigne', label: t('mail.consigne'), type: 'textarea', lignes: 2, aide: t('mail.consigne_aide') },
        { nom: 'lancer', label: t('mail.lancer_agent'), type: 'checkbox', valeur: true }],
    });
    if (!v) return;
    cible = { id: v.tache, lancer: !!v.lancer };
    consigne = v.consigne.trim();
  }
  try {
    await post('/mail/tache', { vue, uid: m.uid, tache: cible.id, consigne, lancer: !!cible.lancer });
    emit('recharger');
    if (creer) ouvrir(cible.id); else erreur(t('mail.rattache'), 'info');
  } catch (e) { erreur(e.message); }
}
