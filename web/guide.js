// Rôle : écran « Guide » — rendu de docs/GUIDE.md (GET /api/guide) avec sommaire, recherche dans la page et
// ancres par section ; bouton « ? » contextuel des autres écrans.
// Frontières : lit le guide, n'écrit rien ; le rendu Markdown est celui de md.js. INV-GUIDE-1 : les ancres
// sont calculées comme `ancre()` de src/orchestrateur/guide.py, que la porte vérifie contre le registre.
import { h, remplacer } from './dom.js';
import { rendreMd } from './md.js';
import { S, ouvrirVue, erreur } from './store.js';
import { t, tn, LANGUE } from './langues.js';

const PREFIXE = 'guide-';
let voulue = '';  // ancre à atteindre au prochain rendu (« ? » contextuel ou #guide=<ancre>)

export const ancre = (x) => x.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
export const hashGuide = () => (voulue ? `#guide=${encodeURIComponent(voulue)}` : '#guide');

export function ouvrirGuide(a = '') {
  voulue = a;
  if (S.vue === 'guide' && !S.selection) { atteindre(); history.replaceState(null, '', hashGuide()); return true; }
  return ouvrirVue('guide');
}
export function fixerAncre(a) { voulue = a || ''; }

export const boutonAide = (a) => h('button', { type: 'button', class: 'btn aide', title: t('guide.aide_ecran_titre'),
  'aria-label': t('guide.aide_ecran'), onclick: () => ouvrirGuide(a) }, '?');

function atteindre() {
  const cible = voulue && document.getElementById(PREFIXE + voulue);
  if (cible) cible.scrollIntoView({ block: 'start' });
}

// Regroupe le rendu par section de niveau ## (h4) pour que la recherche masque ce qui ne correspond pas.
function sections(corps) {
  const groupes = [];
  for (const n of [...corps.children]) {
    if (n.tagName === 'H4' || !groupes.length) groupes.push(h('section', { class: 'guide-section' }));
    groupes.at(-1).append(n);
  }
  remplacer(corps, groupes);
  return groupes;
}

export async function dessinerGuide(el) {
  const corps = h('div', { class: 'md guide-corps' });
  const sommaire = h('nav', { class: 'guide-sommaire', 'aria-label': t('guide.sommaire') });
  const compte = h('span', { class: 'discret' });
  const champ = h('input', { type: 'search', class: 'guide-recherche', placeholder: t('guide.chercher_place'), 'aria-label': t('guide.chercher') });
  remplacer(el, h('div', { class: 'guide' }, h('div', { class: 'eq-tete' }, h('h2', null, t('guide.titre')), champ, compte), sommaire, corps));
  let texte;
  try {
    const r = await fetch(`/api/guide?langue=${LANGUE}`);
    if (!r.ok) throw new Error(t('guide.indisponible', { statut: r.status }));
    texte = await r.text();
  } catch (e) { erreur(e.message); return; }
  if (!el.contains(corps)) return; // l'utilisateur est parti entre-temps
  rendreMd(corps, texte);
  const titres = [...corps.querySelectorAll('h4, h5')];
  // INV-LANGUE-1 : un guide traduit (ou un titre reformulé) fixe l'ancre stable au bout du titre (`{#ancre}`), retirée de l'affichage.
  for (const x of titres) {
    const m = x.textContent.match(/\s*\{#([\w-]+)\}\s*$/);
    if (m) x.textContent = x.textContent.slice(0, m.index);
    x.id = PREFIXE + (m ? m[1] : ancre(x.textContent));
  }
  remplacer(sommaire, h('ul', null, titres.map((x) => h('li', { class: x.tagName === 'H5' ? 'sous' : null },
    h('a', { href: `#guide=${x.id.slice(PREFIXE.length)}`, onclick: (ev) => { ev.preventDefault(); ouvrirGuide(x.id.slice(PREFIXE.length)); } }, x.textContent)))));
  const groupes = sections(corps);
  champ.addEventListener('input', () => {
    const q = champ.value.trim().toLowerCase();
    let n = 0;
    for (const g of groupes) { const vu = !q || g.textContent.toLowerCase().includes(q); g.hidden = !vu; n += vu; }
    compte.textContent = q ? tn('guide.sections', n) : '';
  });
  atteindre();
}
