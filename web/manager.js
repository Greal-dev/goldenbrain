// Rôle : volet « manager » à droite — le fil de l'assistant, lu et écrit ici comme sur Telegram (INV-MANAGER-1).
// Frontières : aucune logique de tri ni de geste ici : le serveur (manager.py) soumet, applique et journalise ;
// ce module affiche le fil, envoie le texte tapé et le bouton pressé. INV-WEB-1 : tout texte passe par h() ou rendreMd.
// Sobriété : rien n'est chargé tant que le volet est fermé ; ensuite, seuls les événements « manager » et le tour de
// la tâche de l'assistant le rafraîchissent (aucun sondage).
import { t } from './langues.js';
import { h, $, heure, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { rendreMd } from './md.js';

const CLE = 'orch.manager';
let el = null, fil = null, charge = false, envoi = false, enCharge = false, perime = false;

export const ouvertManager = () => localStorage.getItem(CLE) === '1';

export function initManager() {
  el = $('#volet-manager');
  const btn = $('#btn-manager');
  if (!el || !btn) return;
  btn.addEventListener('click', () => basculer(!ouvertManager()));
  basculer(ouvertManager());
}

function basculer(ouvrir) {
  localStorage.setItem(CLE, ouvrir ? '1' : '0');
  document.body.classList.toggle('manager-ouvert', ouvrir);
  $('#btn-manager').setAttribute('aria-pressed', String(ouvrir));
  el.hidden = !ouvrir;
  if (ouvrir && !charge) { dessinerCadre(); charger(); }
  if (ouvrir) $('#mgr-saisie')?.focus({ preventScroll: true });
}

function dessinerCadre() {
  const zone = h('textarea', { id: 'mgr-saisie', rows: '2', placeholder: t('manager.saisie'), 'aria-label': t('manager.saisie') });
  zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); envoyer(zone); } });
  remplacer(el,
    h('header', { class: 'mgr-tete' },
      h('button', { type: 'button', class: 'btn mgr-retour', onclick: () => basculer(false) }, t('manager.retour')),
      h('b', null, t('manager.titre')),
      h('span', { class: 'mgr-tg', id: 'mgr-tg', hidden: '' }, t('manager.telegram')),
      h('button', { type: 'button', class: 'mgr-fermer', title: t('manager.fermer'), 'aria-label': t('manager.fermer'), onclick: () => basculer(false) }, '×')),
    h('div', { class: 'mgr-fil', id: 'mgr-fil', role: 'log', 'aria-live': 'polite' }),
    h('form', { class: 'mgr-saisie', onsubmit: (e) => { e.preventDefault(); envoyer(zone); } },
      zone, h('button', { type: 'submit', class: 'btn primaire' }, t('manager.envoyer'))));
}

// Un événement arrivé pendant la lecture du fil peut lui être postérieur : on relit alors (course vue sous charge).
async function charger() {
  if (enCharge) { perime = true; return; }
  enCharge = true; perime = false;
  try { fil = await api('/manager'); charge = true; dessinerFil(); } catch (e) { erreur(e.message); }
  enCharge = false;
  if (perime) charger();
}

// Reconnexion SSE ou redémarrage du serveur : le fil se relit, s'il a déjà été chargé.
export function rechargerManager() { if (charge) charger(); }

function dessinerFil() {
  const zone = $('#mgr-fil');
  if (!zone || !fil) return;
  // Ne défiler en bas que si le lecteur y était déjà (ou au premier dessin) : on ne l'arrache pas à sa lecture.
  const enBas = !zone.firstChild || zone.scrollHeight - zone.scrollTop - zone.clientHeight < 40;
  $('#mgr-tg').hidden = !fil.telegram;
  remplacer(zone, fil.messages.length ? null : h('p', { class: 'mgr-aide' }, t('manager.aide')),
    ...fil.messages.map(elMessage),
    fil.en_cours ? h('p', { class: 'mgr-reflechit' }, h('span', { class: 'tourne', 'aria-hidden': 'true' }), t('manager.reflechit')) : null);
  if (enBas) zone.scrollTop = zone.scrollHeight;
}

function elMessage(m) {
  const moi = m.de === 'vous';
  const actifs = !m.issue && (m.boutons || []).length;
  return h('article', { class: `msg ${moi ? 'user' : 'agent'}`, 'data-n': String(m.n) },
    h('header', null, h('b', null, moi ? t('manager.vous') : t('manager.manager')), m.quand ? h('time', null, heure(m.quand)) : null,
      m.canal === 'telegram' ? h('span', { class: 'mgr-canal' }, t('manager.via_telegram')) : null),
    rendreMd(h('div', { class: 'md' }), m.texte || ''),
    actifs ? h('div', { class: 'mgr-boutons' }, ...m.boutons.map((b) =>
      h('button', { type: 'button', class: `btn${b.data === 'confirmer' ? ' primaire' : ''}`, onclick: (e) => trancher(m.n, b.data, e.currentTarget) }, b.texte))) : null,
    m.issue ? h('p', { class: 'mgr-issue' }, m.issue) : null);
}

async function envoyer(zone) {
  const texte = zone.value.trim();
  if (!texte || envoi) return;
  envoi = true;
  try { await post('/manager/message', { texte }); zone.value = ''; } catch (e) { erreur(e.message); } finally { envoi = false; }
}

async function trancher(n, choix, bouton) {
  bouton.closest('.mgr-boutons')?.querySelectorAll('button').forEach((b) => { b.disabled = true; });
  try { await post('/manager/bouton', { n, choix }); } catch (e) { erreur(e.message); charger(); }
}

// SSE « manager » : un message ajouté ou tranché (de ce canal comme de Telegram).
export function evtManager(e) {
  if (!e.message) return;
  if (enCharge) { perime = true; return; }
  if (!charge) return;
  if (!fil.tache) { charger(); return; } // premier message : la tâche de l'assistant vient d'être créée
  const i = fil.messages.findIndex((m) => m.n === e.message.n);
  if (i >= 0) fil.messages[i] = e.message; else fil.messages.push(e.message);
  fil.messages = fil.messages.slice(-200); // le serveur plafonne aussi à 200
  dessinerFil();
}

// Tour de l'assistant qui commence ou finit : la ligne « réfléchit » suit.
export function evtTourManager(e) {
  if (enCharge) { perime = true; return; }
  if (!charge || !fil.tache || e.tache !== fil.tache) return;
  fil.en_cours = e.type === 'tour_debut';
  dessinerFil();
}
