// Rôle : mode discussion (INV-DISCUSSION-1) — dès qu'une tâche est ouverte, la conversation occupe l'essentiel de l'écran :
// barre haute sur une rangée (les autres boutons dans « Menu »), arbre replié en un rail à intercalaire, notes derrière un
// intercalaire à droite. Rien n'est supprimé : tout reste à un geste (survol, clic, Alt+T / Alt+N / Alt+M / Alt+D).
// Frontières : DOM et localStorage seulement ; la mise en page est dans discussion.css (classes `discussion`, `rail`, `apercu`
// posées ici) ; les notes se replient par notes_tache.js, qui écoute l'événement `gb-disposition`.
// Choix mémorisés par poste dans `gb.disposition` ; au téléphone (≤ 480 px) rien ne change.
import { S, on } from './store.js';
import { $, h } from './dom.js';
import { t } from './langues.js';

const CLE = 'gb.disposition', VU = 'gb.disposition-vu';
const lire = () => { try { return { tout: false, arbre: false, ...JSON.parse(localStorage.getItem(CLE)) }; } catch { return { tout: false, arbre: false }; } };
let D = lire();
export const disposition = () => D;
const ecrire = () => { try { localStorage.setItem(CLE, JSON.stringify(D)); } catch { /* stockage indisponible : le choix vaut pour la séance */ } };
const etroit = matchMedia('(max-width: 480px)');
const actif = () => !!S.selection && !D.tout && !etroit.matches;
let minuteurs = {};
const apres = (nom, ms, f) => { clearTimeout(minuteurs[nom]); minuteurs[nom] = setTimeout(f, ms); };
const souris = (e) => e.pointerType === 'mouse';

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
  const travaux = $('#btn-travaux');
  if (on_) $('#btn-nouvelle').before(travaux); else if (travaux.parentElement.classList.contains('b-haut')) document.querySelector('.b-bas').prepend(travaux);
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
// Les notes sont repliées par défaut tant que la disposition n'est pas « tout afficher » (lu par notes_tache.js).
export const notesRepliees = () => !D.tout && !etroit.matches;

// Premier usage : un bandeau dit où sont passés l'arbre, les notes et les autres boutons. Il prend sa place dans la page, avant le corps,
// donc ne recouvre ni le titre ni le fil ; il ne s'affiche qu'une fois (marqué vu dès l'apparition).
function bulle() {
  let vu = true;
  try { vu = localStorage.getItem(VU) === '1'; } catch { /* stockage indisponible : pas de bandeau */ }
  if (vu || document.querySelector('[data-id="bulle-discussion"]')) return;
  const fermer = () => document.querySelector('[data-id="bulle-discussion"]')?.remove();
  try { localStorage.setItem(VU, '1'); } catch { /* sans effet */ }
  $('#corps').before(h('div', { class: 'bulle-discussion', role: 'status', 'data-id': 'bulle-discussion' },
    h('b', null, t('discussion.bulle_titre')), h('span', null, t('discussion.bulle_texte')),
    h('button', { type: 'button', class: 'btn petit primaire', 'data-id': 'bulle-compris', onclick: fermer }, t('discussion.compris'))));
  setTimeout(fermer, 20000);
}

export function initDiscussion() {
  const nav = $('#volet-gauche'), zone = document.querySelector('.b-menu-zone');
  $('#btn-menu').addEventListener('click', () => menu(!$('#b-menu').classList.contains('ouvert')));
  zone.addEventListener('pointerenter', (e) => { if (souris(e) && actif()) apres('menu', 120, () => menu(true)); });
  zone.addEventListener('pointerleave', (e) => { if (souris(e)) apres('menu', 350, () => menu(false)); });
  $('#b-menu').addEventListener('click', (e) => { if (e.target.closest('button') && e.target.id !== 'btn-menu') menu(false); });
  document.addEventListener('click', (e) => { if (!e.target.closest('.b-menu-zone')) menu(false); });
  $('#btn-disposition').addEventListener('click', toutAfficher);
  $('#rail-arbre').addEventListener('click', () => { if (actif()) epingler(); });
  nav.addEventListener('pointerenter', (e) => { if (souris(e) && nav.classList.contains('rail')) apres('arbre', 150, () => nav.classList.add('apercu')); });
  nav.addEventListener('pointerleave', (e) => { if (souris(e)) apres('arbre', 350, () => nav.classList.remove('apercu')); });
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
