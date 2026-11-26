// Rôle : largeur réglable du volet des tâches (INV-DISCUSSION-1) — une poignée sur son bord droit se tire à la souris ou au doigt,
// se pilote au clavier (← → par pas de 16 px, Début = largeur d'origine) et se remet d'origine d'un double-clic.
// Frontières : DOM et localStorage seulement ; ne pose que la variable CSS `--l-arbre`, lue par la grille (style.css, discussion.css,
// manager.css). Rien au téléphone (≤ 480 px : le volet y est plein écran) ; choix mémorisé par navigateur (`gb.largeur-arbre`).
import { h } from './dom.js';
import { t } from './langues.js';

const CLE = 'gb.largeur-arbre', MIN = 200, PAS = 16;
const max = () => Math.max(MIN, Math.min(760, Math.round(innerWidth * 0.6)));
const borner = (px) => Math.max(MIN, Math.min(max(), Math.round(px)));
const racine = document.documentElement;

function poser(px, memoriser = true) {
  if (px == null) racine.style.removeProperty('--l-arbre'); else racine.style.setProperty('--l-arbre', `${borner(px)}px`);
  if (!memoriser) return;
  try { if (px == null) localStorage.removeItem(CLE); else localStorage.setItem(CLE, String(borner(px))); } catch { /* stockage indisponible : vaut pour la séance */ }
}

export function initLargeurVolet() {
  const volet = document.getElementById('volet-gauche'), corps = document.getElementById('volet-gauche-corps');
  if (!volet || !corps) return;
  let memo = null;
  try { memo = parseInt(localStorage.getItem(CLE), 10) || null; } catch { /* idem */ }
  if (memo) poser(memo, false);
  const poignee = h('div', { class: 'poignee-arbre', 'data-id': 'poignee-arbre', role: 'separator', tabindex: '0', 'aria-orientation': 'vertical',
    'aria-label': t('index.poignee_arbre'), title: t('index.poignee_arbre') });
  volet.append(poignee);
  const largeur = () => corps.getBoundingClientRect().width;
  poignee.addEventListener('pointerdown', (e) => {
    if (e.button) return;
    e.preventDefault();
    const x0 = e.clientX, l0 = largeur();
    poignee.setPointerCapture(e.pointerId);
    document.body.classList.add('tire-arbre'); // pas de sélection de texte ni de transition pendant le geste
    const bouge = (ev) => poser(l0 + ev.clientX - x0, false);
    const fin = (ev) => {
      poignee.removeEventListener('pointermove', bouge);
      document.body.classList.remove('tire-arbre');
      if (ev.type === 'pointerup') poser(l0 + ev.clientX - x0);
    };
    poignee.addEventListener('pointermove', bouge);
    poignee.addEventListener('pointerup', fin, { once: true });
    poignee.addEventListener('pointercancel', fin, { once: true });
  });
  poignee.addEventListener('dblclick', () => poser(null));
  poignee.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); poser(largeur() + (e.key === 'ArrowRight' ? PAS : -PAS)); }
    else if (e.key === 'Home') { e.preventDefault(); poser(null); }
  });
  addEventListener('resize', () => { if (racine.style.getPropertyValue('--l-arbre')) poser(parseInt(racine.style.getPropertyValue('--l-arbre'), 10), false); });
}
