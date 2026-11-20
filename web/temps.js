// Rôle : le temps d'une tâche côté interface — libellés d'échéance et de priorité, cellules, tri, édition en place.
// Frontières : lit ce que le serveur calcule (`retard`, `echeance`, `priorite`) ; n'écrit que par POST /taches/{id}/temps.
import { h } from './dom.js';
import { post } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

export const PRIORITES = [['haute', t('temps.haute')], ['moyenne', t('temps.moyenne')], ['basse', t('temps.basse')]];
const RANG = { haute: 0, moyenne: 1, normale: 1, basse: 2 }; // `normale` existe déjà dans le vault : lue comme `moyenne`
export const rangPriorite = (p) => RANG[p] ?? 3;
export const libellePriorite = (p) => PRIORITES.find(([k]) => k === p)?.[1] || (p ? p[0].toUpperCase() + p.slice(1) : '');

// Écart en jours entre aujourd'hui (heure locale) et une date AAAA-MM-JJ : négatif = passée.
export function ecartJours(iso) {
  const [a, m, j] = iso.split('-').map(Number);
  const tk = new Date();
  return Math.round((Date.UTC(a, m - 1, j) - Date.UTC(tk.getFullYear(), tk.getMonth(), tk.getDate())) / 86400000);
}
function dateCourte(iso) {
  const jm = `${iso.slice(8)}/${iso.slice(5, 7)}`;
  return +iso.slice(0, 4) === new Date().getFullYear() ? jm : `${jm}/${iso.slice(2, 4)}`;
}
export function libelleEcheance(iso, retard) {
  if (!iso) return '';
  const e = ecartJours(iso);
  if (e === 0) return t('temps.aujourdhui');
  if (e === 1) return t('temps.demain');
  if (retard) return t('temps.retard', { n: -e });
  return dateCourte(iso);
}

export const celluleEcheance = (n) => h('div', { class: `c-ech${n.retard ? ' retard' : ''}`, role: 'gridcell', title: n.echeance ? (n.retard ? t('temps.echeance_retard', { date: n.echeance }) : t('temps.echeance', { date: n.echeance })) : null },
  libelleEcheance(n.echeance, n.retard));
export const celluleCle = (p) => (p ? h('span', { class: `prio prio-${p}` }, libellePriorite(p)) : null);
export const cellulePriorite = (n) => h('div', { class: 'c-prio', role: 'gridcell' }, celluleCle(n.priorite));

// Clé de tri d'une colonne : les valeurs absentes passent toujours en dernier, quel que soit le sens.
export const CLES_TRI = {
  echeance: (n) => n.echeance || null,
  priorite: (n) => (n.priorite ? rangPriorite(n.priorite) : null),
};
export function comparer(col, sens) {
  const cle = CLES_TRI[col];
  return (a, b) => {
    const x = cle(a), y = cle(b);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    return (x < y ? -1 : x > y ? 1 : 0) * sens;
  };
}

// Édition en place (détail d'une tâche) : date et priorité ; vide = retirer.
export function editeurTemps(tk, appliquer) {
  const poser = async (corps, el, ancien) => {
    try { appliquer(await post(`/taches/${encodeURIComponent(tk.id)}/temps`, corps)); } catch (e) { erreur(e.message); el.value = ancien; }
  };
  const date = h('input', { type: 'date', 'aria-label': t('temps.echeance_label'), value: tk.echeance || '', class: tk.retard ? 'retard' : null,
    title: tk.retard ? t('temps.depassee') : t('temps.vider'), onchange: (e) => poser({ echeance: e.target.value }, e.target, tk.echeance || '') });
  const connues = PRIORITES.map(([k]) => k);
  const options = [['', t('temps.priorite')], ...PRIORITES, ...(tk.priorite && !connues.includes(tk.priorite) ? [[tk.priorite, libellePriorite(tk.priorite)]] : [])];
  const prio = h('select', { 'aria-label': t('temps.priorite'), title: t('temps.priorite'), onchange: (e) => poser({ priorite: e.target.value }, e.target, tk.priorite || '') },
    options.map(([k, l]) => h('option', { value: k, selected: k === (tk.priorite || '') ? true : null }, l)));
  return h('span', { class: 'temps-edit' }, date, prio);
}
