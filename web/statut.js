// Rôle : choix du statut d'une tâche — une seule liste de choix (détail : <select> ; arbre et cascade : menu sur la pastille),
// une seule écriture (POST /taches/<id>/statut, la route du détail) et l'annulation du dernier changement.
// Frontières : n'écrit rien d'autre ; la ligne se met à jour par l'événement 'recharger' (relecture de l'arbre).
import { h, ORDRE_STATUTS, RETOUR, libelleStatut, groupeStatut } from './dom.js';
import { post } from './api.js';
import { emit, erreur } from './store.js';
import { t } from './langues.js';

const enc = encodeURIComponent;
export const INFO_VERROU = t('statut.verrou_info');

// Transitions proposées en premier à l'humain, selon le statut courant ; les autres restent atteignables (« Autres statuts »).
// `retour` désigne le statut de retour réglé (RETOUR, INV-STATUT-1).
const SUITES = {
  'a-faire': ['en-cours', 'abandonne'], 'en-cours': ['retour', 'bloque', 'fait', 'abandonne'],
  retour: ['en-cours', 'fait', 'bloque', 'abandonne'], bloque: ['en-cours', 'retour', 'abandonne'],
  fait: ['cloture', 'en-cours', 'retour'], cloture: ['en-cours'], abandonne: ['a-faire', 'en-cours'],
};
const suites = (g) => (SUITES[g === RETOUR ? 'retour' : g] || []).map((s) => (s === 'retour' ? RETOUR : s));

// Choix offerts pour un statut courant : le statut lui-même, les transitions courantes, puis les autres (même ordre partout).
export function groupesStatut(statut) {
  const g = groupeStatut(statut), sug = suites(g);
  return [{ titre: null, statuts: [statut] }, { titre: t('statut.transitions'), statuts: sug },
    { titre: t('statut.autres'), statuts: ORDRE_STATUTS.filter((s) => s !== g && !sug.includes(s)) }].filter((x) => x.statuts.length);
}

export const ecrireStatut = (id, statut) => post(`/taches/${enc(id)}/statut`, { statut });

// --- annulation : un seul bandeau à la fois, quelques secondes ---
let bandeau = null, minuteur = 0;
function fermerBandeau() { clearTimeout(minuteur); bandeau?.remove(); bandeau = null; }
function proposerAnnulation(n, avant, apres) {
  fermerBandeau();
  const annuler = h('button', { type: 'button', class: 'btn petit', onclick: async () => {
    fermerBandeau();
    try { await ecrireStatut(n.id, avant); emit('recharger'); } catch (e) { if (!e.annule) erreur(e.message); }
  } }, t('statut.annuler'));
  bandeau = h('div', { class: 'annul-statut', role: 'status' },
    h('span', null, t('statut.change', { titre: n.titre, avant: libelleStatut(avant), apres: libelleStatut(apres) })), annuler);
  document.body.append(bandeau);
  minuteur = setTimeout(fermerBandeau, 8000);
}

// --- menu sur la pastille ---
let ouvert = null; // { menu, declencheur }
export function fermerMenu(rendreFocus = true) {
  if (!ouvert) return;
  const { menu, declencheur, cle } = ouvert;
  ouvert = null;
  menu.remove();
  document.removeEventListener('pointerdown', surExterieur, true);
  if (rendreFocus) setTimeout(() => (declencheur.isConnected ? declencheur : document.querySelector(`[data-cle="${CSS.escape(cle || '')}"] .st-chg`))?.focus({ preventScroll: true }), 0);
}
function surExterieur(e) { if (ouvert && !ouvert.menu.contains(e.target) && !ouvert.declencheur.contains(e.target)) fermerMenu(false); }

function refuser(declencheur, message) {
  const ligne = declencheur.closest('[data-cle]');
  if (!ligne) { erreur(message); return; }
  ligne.querySelector('.st-refus')?.remove();
  const el = h('span', { class: 'st-refus', role: 'alert' }, message);
  declencheur.after(el);
  setTimeout(() => el.remove(), 7000);
}

async function choisir(n, declencheur, statut) {
  fermerMenu();
  if (statut === n.statut) return;
  const avant = n.statut;
  try {
    await ecrireStatut(n.id, statut);
    emit('recharger');
    // L'arbre se redessine (relecture différée) : la pastille d'origine disparaît ; le focus revient à celle de la même ligne.
    const cle = declencheur.closest('[data-cle]')?.dataset.cle;
    if (cle) setTimeout(() => { if (document.activeElement === document.body || !document.activeElement) document.querySelector(`[data-cle="${CSS.escape(cle)}"] .st-chg`)?.focus({ preventScroll: true }); }, 900);
    proposerAnnulation(n, avant, statut);
  } catch (e) { if (!e.annule) refuser(declencheur, e.message); }
}

function ouvrirMenu(n, declencheur) {
  fermerMenu(false);
  const items = [];
  const menu = h('div', { class: 'menu-statut', role: 'menu', 'aria-label': t('statut.menu_label', { titre: n.titre }) },
    groupesStatut(n.statut).map((g) => h('div', { role: 'group', 'aria-label': g.titre || t('statut.actuel') },
      g.titre ? h('div', { class: 'ms-titre', 'aria-hidden': 'true' }, g.titre) : null,
      g.statuts.map((s) => {
        const b = h('button', { type: 'button', role: 'menuitemradio', class: `ms-item st-${s}`, 'aria-checked': String(s === n.statut), tabindex: '-1',
          onclick: (e) => { e.stopPropagation(); choisir(n, declencheur, s); } },
        h('span', { class: `pastille st-${s}`, 'aria-hidden': 'true' }), s === n.statut && n.a_valider ? t('statut.a_valider') : libelleStatut(s));
        items.push(b);
        return b;
      }))));
  menu.addEventListener('keydown', (e) => {
    const i = items.indexOf(document.activeElement);
    const aller = (j) => { e.preventDefault(); items[(j + items.length) % items.length].focus(); };
    if (e.key === 'ArrowDown') aller(i + 1);
    else if (e.key === 'ArrowUp') aller(i - 1);
    else if (e.key === 'Home') aller(0);
    else if (e.key === 'End') aller(-1);
    else if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); e.stopPropagation(); fermerMenu(); }
    else if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); // le bouton actif réagit au clic synthétique
  });
  document.body.append(menu);
  const r = declencheur.getBoundingClientRect();
  menu.style.left = `${Math.max(4, Math.min(r.left, innerWidth - menu.offsetWidth - 4))}px`;
  menu.style.top = `${r.bottom + menu.offsetHeight + 8 > innerHeight ? Math.max(4, r.top - menu.offsetHeight - 2) : r.bottom + 2}px`;
  ouvert = { menu, declencheur, cle: declencheur.closest('[data-cle]')?.dataset.cle };
  document.addEventListener('pointerdown', surExterieur, true);
  (items.find((b) => b.getAttribute('aria-checked') === 'true') || items[0]).focus();
}

// Rend une pastille d'arbre ou de cascade cliquable : bouton focalisable ; clic, Entrée ou Espace ouvre le menu sans sélectionner la ligne.
export function rendreChangeable(el, n) {
  const verrou = !!n.statut_verrouille;
  el.classList.add('st-chg');
  el.setAttribute('role', 'button');
  el.tabIndex = 0;
  el.setAttribute('aria-haspopup', 'menu');
  el.setAttribute('aria-label', t('statut.aria', { statut: libelleStatut(n.statut), titre: n.titre }));
  if (verrou) { el.setAttribute('aria-disabled', 'true'); el.title = INFO_VERROU; } else el.title = t('statut.changer');
  const agir = () => { if (!verrou) (ouvert?.declencheur === el ? fermerMenu() : ouvrirMenu(n, el)); };
  el.addEventListener('click', (e) => { e.stopPropagation(); agir(); });
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') { e.preventDefault(); e.stopPropagation(); agir(); }
  });
  el.addEventListener('dragstart', (e) => e.preventDefault());
  return el;
}
