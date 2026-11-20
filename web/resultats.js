// Rôle : page de résultats de la recherche plein texte dans les notes (volet droit) — extraits, termes surlignés, n° de ligne.
// Frontières : API GET /vault/recherche ; ouvre une note par store.ouvrirNote ; aucun innerHTML (surlignage par nœuds <mark>).
import { h, remplacer, dossierDe } from './dom.js';
import { ouvrirNote } from './store.js';
import { ouvert } from './interface.js';
import { api } from './api.js';
import { voirDossier } from './notes.js';
import { t, tn } from './langues.js';

const LIMITE = 50;
let courant = null;

// Texte normalisé (sans accents ni casse) et table d'indices vers le texte d'origine : le surlignage suit la recherche du serveur.
function normaliser(s) {
  let n = '';
  const map = [];
  for (let i = 0; i < s.length; i++) {
    const c = s[i].normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
    for (let k = 0; k < c.length; k++) { n += c[k]; map.push(i); }
  }
  return { n, map };
}
export function termes(q) {
  const tk = [];
  for (const m of q.matchAll(/"([^"]+)"|(\S+)/g)) tk.push(normaliser(m[1] || m[2]).n);
  return tk.filter(Boolean);
}
export function surligner(texte, mots) {
  const { n, map } = normaliser(texte);
  const zones = [];
  for (const m of mots) for (let i = n.indexOf(m); i >= 0; i = n.indexOf(m, i + m.length)) zones.push([map[i], map[i + m.length - 1] + 1]);
  zones.sort((a, b) => a[0] - b[0]);
  const fusion = [];
  for (const z of zones) { const d = fusion.at(-1); if (d && z[0] <= d[1]) d[1] = Math.max(d[1], z[1]); else fusion.push([...z]); }
  const out = [];
  let p = 0;
  for (const [a, b] of fusion) { if (a > p) out.push(texte.slice(p, a)); out.push(h('mark', null, texte.slice(a, b))); p = b; }
  if (p < texte.length) out.push(texte.slice(p));
  return out;
}

function resultat(r, mots) {
  return h('li', { class: 'rs' },
    h('div', { class: 'rs-tete' },
      h('button', { class: 'lien-titre rs-titre', type: 'button', onclick: () => ouvrirNote(r.chemin) }, surligner(r.titre || r.chemin, mots)),
      h('button', { class: 'crumb rs-chemin', type: 'button', title: t('resultats.voir_dossier'), onclick: () => voirDossier(dossierDe(r.chemin)) }, r.chemin)),
    (r.extraits || []).length ? h('ul', { class: 'rs-extraits' }, r.extraits.map((x) => h('li', null,
      h('button', { class: 'rs-extrait', type: 'button', onclick: () => ouvrirNote(r.chemin), title: t('resultats.ouvrir', { chemin: r.chemin }) },
        h('span', { class: 'rs-ligne' }, x.ligne), h('span', { class: 'rs-texte' }, surligner(x.texte, mots)))))) : null);
}

export async function dessinerResultats(el, q) {
  courant = q;
  const mots = termes(q);
  remplacer(el, h('div', { class: 'resultats-page' }, h('h2', { class: 'd-titre' }, t('resultats.titre', { q })), h('p', { class: 'vide' }, t('resultats.recherche'))));
  let liste;
  if (!ouvert('notes')) { remplacer(el, h('div', { class: 'resultats-page' }, h('h2', { class: 'd-titre' }, t('resultats.titre', { q })), h('p', { class: 'vide' }, t('resultats.desactivees')))); return; }
  try { liste = await api(`/vault/recherche?q=${encodeURIComponent(q)}&limite=${LIMITE}`); } catch (e) {
    if (courant === q) remplacer(el, h('div', { class: 'resultats-page' }, h('h2', { class: 'd-titre' }, t('resultats.titre', { q })), h('p', { class: 'vide', role: 'alert' }, e.message)));
    return;
  }
  if (courant !== q) return;
  remplacer(el, h('div', { class: 'resultats-page' },
    h('h2', { class: 'd-titre' }, t('resultats.titre', { q })),
    h('p', { class: 'casc-total', role: 'status' }, liste.length ? (liste.length >= LIMITE ? tn('resultats.nombre_limite', liste.length, { limite: LIMITE }) : tn('resultats.nombre', liste.length)) : t('resultats.aucune')),
    h('ul', { class: 'rs-liste' }, liste.map((r) => resultat(r, mots)))));
}
