// Rôle : mode discussion (INV-DISCUSSION-1) — dès qu'une tâche est ouverte, la conversation occupe l'essentiel de l'écran :
// barre haute sur une rangée (les autres boutons dans « Menu »), arbre replié en un rail à intercalaire, notes derrière un
// intercalaire à droite. Rien n'est supprimé : tout reste à un geste (survol, clic, Alt+T / Alt+N / Alt+M / Alt+D).
// Frontières : DOM, localStorage et PUT /api/interface (marque « vu ») ; la mise en page est dans discussion.css (classes `discussion`, `rail`, `apercu`
// posées ici) ; les notes se replient par notes_tache.js, qui écoute l'événement `gb-disposition`.
// Choix mémorisés dans `gb.disposition` (navigateur) ; bandeau de premier usage vu une fois par poste (serveur, INV-DISCUSSION-2) ; au téléphone (≤ 480 px) rien ne change.
import { S, on } from './store.js';
import { $, h } from './dom.js';
import { t } from './langues.js';
import { intention } from './deroulant.js';
import { changerInterface } from './interface.js';

const CLE = 'gb.disposition', VU = 'gb.disposition-vu';
const lire = () => { try { return { tout: false, arbre: false, ...JSON.parse(localStorage.getItem(CLE)) }; } catch { return { tout: false, arbre: false }; } };
let D = lire();
export const disposition = () => D;
const ecrire = () => { try { localStorage.setItem(CLE, JSON.stringify(D)); } catch { /* stockage indisponible : le choix vaut pour la séance */ } };
const etroit = matchMedia('(max-width: 480px)');
const actif = () => !!S.selection && !D.tout && !etroit.matches;

function menu(ouvert) {
  $('#b-menu').classList.toggle('ouvert', ouvert);
  $('#btn-menu').setAttribute('aria-expanded', String(ouvert));
}

function appliquer() {
  const on_ = actif(), corps = document.body.classList, nav = $('#volet-gauche');
  corps.toggle('discussion', on_);
  corps.toggle('tache-ouverte', !!S.selection && !etroit.matches);
  corps.toggle('arbre-epingle', on_ && D.arbre);
  nav.classList.toggle('rail', on_ && !D.arbre);
  if (!on_ || D.arbre) nav.classList.remove('apercu');
  $('#rail-arbre').setAttribute('aria-expanded', String(!on_ || D.arbre || nav.classList.contains('apercu')));
  // « En cours » devient une pastille de la rangée haute ; hors discussion, il retrouve sa rangée.
  const travaux = $('#btn-travaux'), zone = travaux.parentElement; // la pastille voyage avec son déroulant (INV-DEROULANT-1)
  if (on_) $('#btn-nouvelle').before(zone); else if (zone.parentElement.classList.contains('b-haut')) document.querySelector('.b-bas').prepend(zone);
  travaux.classList.toggle('btn-compte', on_);
  const bascule = $('#btn-disposition');
  bascule.setAttribute('aria-pressed', String(D.tout));
  bascule.firstElementChild.textContent = t(D.tout ? 'index.mode_discussion' : 'index.tout_afficher');
  if (!on_) menu(false);
  if (on_) bulle();
}

function changer(partie) {
  const bascule = 'tout' in partie && partie.tout !== D.tout;
  D = { ...D, ...partie };
  ecrire();
  appliquer();
  if (bascule) document.dispatchEvent(new CustomEvent('gb-disposition', { detail: D })); // seul un changement de mode touche aux notes
}
const epingler = (v = !D.arbre) => { changer({ arbre: v }); $('#volet-gauche').classList.remove('apercu'); };
const toutAfficher = () => changer({ tout: !D.tout });
// Les notes sont repliées par défaut tant que la disposition n'est pas « tout afficher » (lu par notes_tache.js) ; au téléphone elles le
// sont toujours par défaut : le fil et la saisie gardent l'écran, les notes s'ouvrent d'un toucher (INV-REACTIVITE-1).
export const notesRepliees = () => etroit.matches || !D.tout;

// Premier usage : un bandeau dit où sont passés l'arbre, les notes et les autres boutons. Il prend sa place dans la pile des bandeaux
// (bandeaux.js : un seul à la fois, avant le corps), donc ne recouvre ni le titre ni le fil ; il ne s'affiche qu'une fois (marqué vu dès
// l'apparition) et se referme seul à la première interaction (clic, touche) ou après 20 s.
function bulle() {
  // INV-DISCUSSION-2 : vu une fois par poste — mémoire du serveur (`[interface] vus`), pas seulement de ce navigateur.
  let vu = !!S.interface?.vus?.includes('discussion');
  try { vu ||= localStorage.getItem(VU) === '1'; } catch { vu = true; /* stockage indisponible : pas de bandeau */ }
  if (vu || document.querySelector('[data-id="bulle-discussion"]')) return;
  const ecoute = (e) => { if (!e.target.closest?.('.bulle-discussion')) fermer(); };
  const fermer = () => {
    document.querySelector('[data-id="bulle-discussion"]')?.remove();
    for (const ev of ['pointerdown', 'keydown']) document.removeEventListener(ev, ecoute, true);
  };
  try { localStorage.setItem(VU, '1'); } catch { /* sans effet */ }
  changerInterface({ vu: 'discussion' }).catch(() => { /* hors ligne : le navigateur s'en souvient déjà */ });
  $('#bandeaux').append(h('div', { class: 'bulle-discussion', role: 'status', 'data-id': 'bulle-discussion' },
    h('b', null, t('discussion.bulle_titre')), h('span', null, t('discussion.bulle_texte')),
    h('button', { type: 'button', class: 'btn petit primaire', 'data-id': 'bulle-compris', onclick: fermer }, t('discussion.compris'))));
  // L'interaction qui a ouvert la tâche est déjà passée : l'écoute commence après elle. Un clic sur le bandeau lui-même le déplie (bandeaux.js).
  setTimeout(() => { for (const ev of ['pointerdown', 'keydown']) document.addEventListener(ev, ecoute, true); }, 300);
  setTimeout(fermer, 20000);
}

export function initDiscussion() {
  const nav = $('#volet-gauche'), zone = document.querySelector('.b-menu-zone');
  $('#btn-menu').addEventListener('click', () => menu(!$('#b-menu').classList.contains('ouvert')));
  intention([zone], () => menu(true), () => menu(false), actif); // INV-DEROULANT-1 : mêmes délais que tout déroulant
  $('#b-menu').addEventListener('click', (e) => { if (e.target.closest('button') && e.target.id !== 'btn-menu') menu(false); });
  document.addEventListener('click', (e) => { if (!e.target.closest('.b-menu-zone')) menu(false); });
  $('#btn-disposition').addEventListener('click', toutAfficher);
  $('#rail-arbre').addEventListener('click', () => { if (actif()) epingler(); });
  intention([nav], () => nav.classList.add('apercu'), () => nav.classList.remove('apercu'), () => nav.classList.contains('rail'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { menu(false); nav.classList.remove('apercu'); }
    if (!e.altKey || e.ctrlKey || e.metaKey || etroit.matches) return;
    const k = e.key.toLowerCase(), notes = document.querySelector('.volet-t-notes .p-replier');
    if (k === 't' && actif()) epingler(); else if (k === 'n' && notes) notes.click(); else if (k === 'm' && actif()) menu(!$('#b-menu').classList.contains('ouvert')); else if (k === 'd' && S.selection) toutAfficher(); else return;
    e.preventDefault();
  });
  on('selection', appliquer);
  etroit.addEventListener('change', appliquer);
  appliquer();
}
