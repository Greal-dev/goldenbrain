// Rôle : rendu de la conversation d'une tâche — messages, tours, étapes à la demande, activité en direct.
// Frontières : DOM seulement (aucun appel API, aucun état de défilement : detail.js s'en charge). INV-WEB-1 : tout texte passe par h() ou rendreMd.
// Étapes (lot 7) : la bascule est une classe CSS (`masque`) sur le conteneur, jamais un nouveau rendu : rien ne saute à la bascule.
// Un tour = les messages de l'agent entre deux messages d'une autre source ; sa réponse finale = son dernier message qui porte du texte.
import { h, heure, ajouter } from './dom.js';
import { rendreMd } from './md.js';
import { t, tn } from './langues.js';

const CLE = 'orch.etapes';
export const etapesAffichees = () => localStorage.getItem(CLE) === '1';
export const memoriserEtapes = (v) => localStorage.setItem(CLE, v ? '1' : '0');

const resumeOutils = (o) => { const m = {}; o.forEach((x) => { m[x] = (m[x] || 0) + 1; }); return Object.entries(m).map(([k, n]) => (n > 1 ? `${k} ×${n}` : k)).join(' · '); };

export function elMsg(m, classes = '') {
  // Message du système (échec d'un tour) : signé GoldenBrain, jamais confondu avec l'agent ni avec Vous.
  if (m.role === 'systeme') {
    return h('article', { class: `msg systeme${classes ? ` ${classes}` : ''}`, role: 'alert' },
      h('header', null, h('b', null, t('conversation.echec')), m.horodatage ? h('time', null, heure(m.horodatage)) : null),
      h('div', { class: 'md' }, m.texte));
  }
  const u = m.role === 'utilisateur';
  // Un message entre crochets vient de GoldenBrain (mandat, message d'une autre tâche, avis d'un persona), pas de l'utilisateur.
  const moi = u && !/^\s*\[/.test(m.texte || '');
  return h('article', { class: `msg ${u ? 'user' : 'agent'}${classes ? ` ${classes}` : ''}` },
    h('header', null, h('b', null, u ? (moi ? t('conversation.vous') : 'GoldenBrain') : t('conversation.agent')), m.horodatage ? h('time', null, heure(m.horodatage)) : null,
      // INV-RETOUR-1 : un message envoyé par GoldenBrain (relié à son tour) se modifie ; detail.js porte le geste.
      moi && m.tour ? h('button', { type: 'button', class: 'msg-modifier', 'data-tour': m.tour, title: t('conversation.modifier_titre') }, t('conversation.modifier')) : null),
    m.texte ? rendreMd(h('div', { class: 'md' }), m.texte) : null,
    (m.outils || []).length ? h('div', { class: 'outils' }, resumeOutils(m.outils)) : null,
    // INV-RETOUR-1 : « Répondre à partir d'ici » sur une réponse de l'IA ; detail.js porte le geste.
    !u && m.texte && (m.suite || m.dernier) ? h('button', { type: 'button', class: 'msg-repondre', 'data-suite': m.suite || '', title: t('conversation.repondre_titre') }, t('conversation.repondre')) : null);
}

// Une étape = un message intermédiaire qui porte du texte, ou un appel d'outil (du message final comme des autres).
const nbEtapes = (msgs, final) => msgs.reduce((s, m) => s + (m !== final && m.texte?.trim() ? 1 : 0) + (m.outils || []).length, 0);

function compteur(n, tour, i, deplies) {
  const lib = (ouvert) => ouvert ? tn('conversation.etapes_ouvert', n) : tn('conversation.etapes_masquees', n);
  const b = h('button', { class: 'etapes-n', type: 'button', 'aria-expanded': String(deplies.has(i)) }, lib(deplies.has(i)));
  b.addEventListener('click', () => {
    const ouvert = tour.classList.toggle('deplie');
    if (ouvert) deplies.add(i); else deplies.delete(i);
    b.setAttribute('aria-expanded', String(ouvert));
    b.textContent = lib(ouvert);
  });
  return b;
}

const ligneActivite = () => h('div', { class: 'activite', role: 'status' }, h('span', { class: 'tourne' }), h('span', { class: 'act-t' }, t('conversation.travaille')));

function blocTour(msgs, i, direct, deplies) {
  const tour = h('div', { class: `tour-c${direct ? ' live' : ''}${deplies.has(i) ? ' deplie' : ''}` });
  if (direct) { ajouter(tour, msgs.map((m) => elMsg(m, 'etape')), ligneActivite()); return tour; }
  const final = [...msgs].reverse().find((m) => m.texte?.trim() && !m.secondaire) || [...msgs].reverse().find((m) => m.texte?.trim());
  const n = nbEtapes(msgs, final);
  ajouter(tour, n ? compteur(n, tour, i, deplies) : null, msgs.map((m) => elMsg(m, m === final ? 'final' : 'etape')));
  return tour;
}

// Historique -> nœuds. `direct` : le dernier tour est en cours (ligne d'activité au lieu d'une réponse finale).
// `n0` : numéro du premier tour (rendu en deux temps : la fin d'abord, le début ensuite, voir detail.js).
export function rendreConversation(msgs, direct, deplies, n0 = 0) {
  const sortie = [];
  let suite = [], n = n0;
  const vider = (dernier) => {
    if (suite.length || (dernier && direct)) sortie.push(blocTour(suite, n++, dernier && direct, deplies));
    suite = [];
  };
  for (const m of msgs) {
    if (m.role === 'utilisateur' || m.role === 'systeme') { vider(false); sortie.push(elMsg(m)); } else suite.push(m);
  }
  vider(true);
  return sortie;
}

// Nombre de tours (groupes de messages de l'agent) que `rendreConversation` numérote dans `msgs`.
export function nbTours(msgs) {
  let n = 0, ouvert = false;
  for (const m of msgs) {
    if (m.role === 'utilisateur' || m.role === 'systeme') { if (ouvert) n++; ouvert = false; } else ouvert = true;
  }
  return n + (ouvert ? 1 : 0);
}

// --- direct (SSE) ---
const premiereLigne = (tk) => String(tk || '').split('\n').find((x) => x.trim()) || '';

// Groupe du tour en cours, créé à la demande ; renvoie aussi l'article qui accumule le texte et les outils du direct.
export function groupeDirect(conv) {
  let g = conv.querySelector(':scope > .tour-c.live');
  if (!g) { conv.querySelector('.vide')?.remove(); g = h('div', { class: 'tour-c live' }, ligneActivite()); conv.append(g); }
  return g;
}
function articleDirect(g) {
  let a = g.querySelector('.msg.live');
  if (!a) { a = elMsg({ role: 'assistant', texte: '', outils: [], horodatage: new Date().toISOString() }, 'etape live'); g.querySelector('.activite').before(a); }
  return a;
}
// Applique un événement `tour_texte` ou `tour_outil` au direct de la conversation `conv`.
export function evenementDirect(conv, e) {
  const g = groupeDirect(conv), a = articleDirect(g);
  if (e.type === 'tour_texte') ajouter(a, rendreMd(h('div', { class: 'md' }), e.texte));
  else {
    ajouter(a, h('div', { class: 'outils' }, e.texte));
    g.querySelector('.act-t').textContent = t('conversation.travaille_outil', { outil: premiereLigne(e.texte) });
  }
}
