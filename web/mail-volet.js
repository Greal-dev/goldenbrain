// Rôle : onglet « Mails » du volet gauche — les mails de la boîte de réception (expéditeur, objet, date, non lu en gras), gestes de ligne
//        (masquer, créer / associer une tâche) ; un clic ouvre le mail dans la page « Email » (#mail).
// Frontières : lit /api/mail seulement ; chargée à l'ouverture de l'onglet (notes.js, INV-MAIL-6) ; la page Email reste propriétaire de la lecture.
import { t } from './langues.js';
import { h, remplacer, heure } from './dom.js';
import { api } from './api.js';
import { S, on, ouvrirVue, erreur } from './store.js';
import { charger } from './paresseux.js';
import { actionsLigne } from './mail-gestes.js';

let cont = null, jeton = 0, abonne = false;

async function ouvrirMail(uid) {
  try { (await charger('mail')).choisir(uid); } catch (e) { erreur(e.message); return; }
  ouvrirVue('mail');
}

function ligne(m) {
  return h('li', { class: 'mail-item' }, h('button', { type: 'button', class: `mail-ligne${m.lu ? '' : ' non-lu'}`, 'data-id': 'volet-mail-ligne', 'data-uid': m.uid, onclick: () => ouvrirMail(m.uid) },
    h('span', { class: 'mail-de' }, m.de), h('span', { class: 'mail-date' }, m.date ? heure(m.date) : ''),
    h('span', { class: 'mail-objet' }, m.piece ? '📎 ' : '', m.objet || t('mail.sans_objet'))), actionsLigne('inbox', m));
}

export async function dessinerVoletMail(racine) {
  cont = racine;
  if (!abonne) { abonne = true; on('mail-change', () => { if (S.onglet === 'mails' && cont?.isConnected) dessinerVoletMail(cont); }); }
  const mien = ++jeton;
  let r, l;
  try { r = await api('/mail/reglages'); } catch (e) { erreur(e.message); return; }
  if (!r.adresse || !r.mdp) {
    remplacer(racine, h('p', { class: 'note' }, t('mail.non_reglee')),
      h('button', { type: 'button', class: 'btn primaire', 'data-id': 'volet-mail-regler', onclick: () => { location.hash = '#reglages/messagerie'; } }, t('mail.aller_reglages')));
    return;
  }
  try { l = await api('/mail/messages?vue=inbox&q=&page=0'); } catch (e) { if (mien === jeton) remplacer(racine, h('p', { class: 'note' }, e.message)); return; }
  if (mien !== jeton) return;
  remplacer(racine,
    h('div', { class: 'g-tete' }, h('span', { class: 'g-titre' }, t('mail.inbox')),
      h('button', { type: 'button', class: 'btn petit', 'data-id': 'volet-mail-actu', title: t('mail.actualiser'), 'aria-label': t('mail.actualiser'), onclick: () => dessinerVoletMail(racine) }, '↻')),
    l.messages.length ? h('ul', { class: 'mail-lignes mail-volet-liste', 'data-id': 'volet-mail-liste' }, l.messages.map(ligne)) : h('p', { class: 'note' }, t('mail.aucun')));
}
