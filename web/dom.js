// Rôle : fabrique de nœuds DOM sûre (jamais d'innerHTML ici), libellés et temps relatif.
import { t, LOCALE } from './langues.js';
export function h(tag, attrs, ...enfants) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const e of enfants.flat(Infinity)) {
    if (e == null || e === false) continue;
    el.append(e.nodeType ? e : document.createTextNode(String(e)));
  }
  return el;
}
// append()/replaceChildren() natifs écrivent « null » pour un null : tout passe par ces deux fonctions.
const noeuds = (l) => l.flat(Infinity).filter((e) => e != null && e !== false);
export const remplacer = (el, ...enfants) => el.replaceChildren(...noeuds(enfants));
export const ajouter = (el, ...enfants) => el.append(...noeuds(enfants));
export const $ = (s, r = document) => r.querySelector(s);
export const dossierDe = (c) => (c.includes('/') ? c.slice(0, c.lastIndexOf('/')) : '');
export const nomDe = (c) => c.slice(c.lastIndexOf('/') + 1);

// Libellés du contrat (lot 3) ; `confier-agent` est affiché comme `a-faire` (même statut pour l'humain).
// INV-STATUT-1 : le statut de retour (« En attente ») est réglé par le serveur (`[vault] statut_retour`).
export let RETOUR = 'retour-humain';
export const STATUTS = {
  'a-faire': t('statut.a_faire'), 'confier-agent': t('statut.a_faire'), 'en-cours': t('statut.en_cours'), [RETOUR]: t('statut.retour'),
  bloque: t('statut.bloque'), fait: t('statut.fait'), cloture: t('statut.cloture'), abandonne: t('statut.abandonne'),
};
export const ORDRE_STATUTS = ['a-faire', 'en-cours', RETOUR, 'bloque', 'fait', 'cloture', 'abandonne'];
export function reglerRetour(nom) {
  if (!nom || nom === RETOUR) return;
  delete STATUTS[RETOUR];
  STATUTS[nom] = t('statut.retour');
  ORDRE_STATUTS[ORDRE_STATUTS.indexOf(RETOUR)] = nom;
  RETOUR = nom;
}
export const groupeStatut = (s) => (s === 'confier-agent' ? 'a-faire' : s);
export const libelleStatut = (s) => STATUTS[s] || s || '—';
// « À moi » = en attente + terminée à valider.
export const pourMoi = (n) => n.statut === RETOUR || !!n.a_valider;
// Classe CSS générique `st-retour`, quel que soit le nom réglé.
export const pastille = (s) => h('span', { class: `pastille st-${s === RETOUR ? 'retour' : s || 'inconnu'}`, title: libelleStatut(s), role: 'img', 'aria-label': libelleStatut(s) });

export function depuis(iso) {
  const ms = Date.parse(iso);
  if (!ms) return '';
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return t('duree.s', { n: s });
  if (s < 3600) return t('duree.min', { n: Math.floor(s / 60) });
  if (s < 86400) return t('duree.h', { n: Math.floor(s / 3600) });
  return t('duree.j', { n: Math.floor(s / 86400) });
}
// `updated` du vault : date seule (jj/mm) ou horodatage ISO (temps relatif).
export function majCourt(v) {
  if (!v) return '';
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return `${s.slice(8)}/${s.slice(5, 7)}`;
  return depuis(s) || s;
}
export function heure(iso) {
  const d = new Date(iso);
  return isNaN(d) ? '' : d.toLocaleString(LOCALE, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
