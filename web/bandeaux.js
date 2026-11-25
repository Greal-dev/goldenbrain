// Rôle : pile des bandeaux d'information (INV-REACTIVITE-1) — un seul bandeau fin à la fois, les autres derrière un compteur « +N » ;
// le bandeau tronqué se lit en entier au clic ou au toucher. Sans cela, quatre bandeaux empilés mangeaient 100 à 120 px de fil.
// Frontières : DOM seulement ; les bandeaux restent dessinés par leurs modules (bandeau.js, version.js, maj-auto.js, app.js,
// discussion.js) qui posent `hidden` ; ce module ne masque que par la classe `bandeau-masque` (jamais par `hidden`).
import { $, h } from './dom.js';
import { t } from './langues.js';

// Du plus urgent au moins urgent : une alerte passe devant une information.
const ORDRE = ['#banniere', '#reseau-perdu', '#vigie-alertes', '.bulle-discussion', '#redemarrage-differe', '#maj-serveur', '#poste-reserve', '#maj-auto', '#maj-dispo'];
const etroit = matchMedia('(max-width: 480px)');
const GESTES = ['button', 'a', 'input', 'select'];
let zone, plus, rang = 0, planifie = false;

const visible = (el) => !el.hidden && !(etroit.matches && el.id === 'maj-dispo'); // telephone.css masque « mise à jour disponible » au téléphone

function appliquer() {
  planifie = false;
  const tous = ORDRE.flatMap((s) => [...zone.querySelectorAll(`:scope > ${s}`)]);
  const vus = tous.filter(visible);
  if (rang >= vus.length) rang = 0;
  for (const el of tous) el.classList.toggle('bandeau-masque', !vus.includes(el) || vus.indexOf(el) !== rang);
  const reste = vus.length - 1;
  if (plus.hidden !== reste < 1) plus.hidden = reste < 1; // une écriture identique relancerait l'observateur
  if (reste >= 1) {
    // N'écrire que si le compteur change : sa propre mise à jour ne doit pas relancer l'observateur (boucle de microtâches).
    const texte = `+${reste}`;
    if (plus.textContent !== texte) { plus.textContent = texte; plus.title = t('bandeaux.plus_titre', { n: reste }); plus.setAttribute('aria-label', plus.title); }
  }
}
const planifier = () => { if (!planifie) { planifie = true; queueMicrotask(appliquer); } };

export function initBandeaux() {
  zone = $('#bandeaux');
  plus = h('button', { type: 'button', id: 'bandeaux-plus', class: 'btn petit', hidden: true, onclick: () => { rang += 1; appliquer(); } });
  zone.append(plus);
  // Un bandeau tronqué se déplie au clic ou au toucher sur son texte ; boutons et liens gardent leur geste.
  zone.addEventListener('click', (e) => {
    const b = e.target.closest('#bandeaux > *');
    if (b && b !== plus && !GESTES.some((g) => e.target.closest(g))) b.classList.toggle('deploye');
  });
  new MutationObserver(planifier).observe(zone, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden'] });
  etroit.addEventListener('change', planifier);
  appliquer();
}
