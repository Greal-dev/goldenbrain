// Rôle : palette de commandes Ctrl+K / Cmd+K — retrouver une tâche en tapant quelques lettres, lancer un geste courant.
// Frontières : lit S.arbre, GET /api/recherche (existante) et les bases récentes (localStorage) ; n'écrit que par les gestes existants (statut, renvoi à l'IA). Chargée à la demande (app.js, INV-REACTIVITE-1).
import { h, $, filLisible, libelleStatut, remplacer } from './dom.js';
import { t } from './langues.js';
import { api } from './api.js';
import { S, parcourir, chemin, ouvrir, ouvrirVue, erreur, emit, noeudTache } from './store.js';
import { groupesStatut, ecrireStatut } from './statut.js';
import { envoyerIA } from './main.js';
import { motsConnus, charger as chargerEtiquettes } from './etiquettes.js';
import { ouvert } from './interface.js';
import { charger } from './paresseux.js';

const MAX = 8, FERMES = new Set(['fait', 'cloture', 'abandonne']);
const norm = (s) => (s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
let dlg, champ, liste, choix = [], sel = 0, jeton = 0, minuteur = 0;

const tachesLocales = (mots) => {
  const trouvees = [];
  for (const n of parcourir(S.arbre)) {
    if (n.type !== 'tache' || !mots.every((m) => norm(n.titre).includes(m))) continue;
    const fil = chemin(S.arbre, (x) => x === n).slice(0, -1).map((x) => x.titre);
    trouvees.push({ id: n.id, titre: n.titre, fil: filLisible(fil).join(' › '), ferme: FERMES.has(n.statut) });
  }
  return trouvees.sort((a, b) => a.ferme - b.ferme).slice(0, MAX);
};

const changerStatut = (id, s) => ecrireStatut(id, s).then(() => emit('recharger'), (e) => erreur(e.message));

function commandes() {
  const cmds = [
    { libelle: t('palette.nouvelle'), agir: () => $('#btn-nouvelle').click() },
    { libelle: t('palette.decisions'), agir: () => ouvrirVue('decisions') },
    { libelle: t('palette.reglages'), agir: () => ouvrirVue('reglages') },
    { libelle: t('palette.mail'), agir: () => ouvrirVue('mail') },
    { libelle: t('palette.nouvelle_etiquette'), agir: () => charger('etiquette_trouver').then((m) => m.nouvelleEtiquette(), (e) => erreur(e.message)) }, // INV-ETIQUETTE-5
    ...motsConnus().map((m) => ({ libelle: t('palette.etiquette', { mot: m }), agir: () => ouvrirVue('etiquette', m) })), // INV-ETIQUETTE-4
  ];
  // Bases ouvertes récemment (base_table.js les note) : lues sans charger le module du tableau.
  let recents = [];
  try { recents = JSON.parse(localStorage.getItem('orch.bases.recents')) || []; } catch { /* liste illisible : aucune */ }
  if (ouvert('notes')) for (const d of recents) cmds.push({ libelle: t('palette.base', { dossier: d || '/' }), agir: () => ouvrirVue('base', d) });
  const id = S.selection, n = id && noeudTache(id);
  if (n) {
    cmds.push({ libelle: t('palette.renvoyer'), agir: () => envoyerIA(id, null) });
    for (const g of groupesStatut(n.statut).slice(1)) for (const s of g.statuts) cmds.push({ libelle: t('palette.statut', { statut: libelleStatut(s) }), agir: () => changerStatut(id, s) });
  }
  return cmds;
}

function rendre() {
  remplacer(liste, ...choix.map((c, i) => h('li', { role: 'option', class: `pal-ligne${i === sel ? ' actif' : ''}`, 'aria-selected': String(i === sel), 'data-id': c.id ? 'palette-tache' : 'palette-commande',
    onclick: () => executer(c) }, h('span', { class: 'pal-titre' }, c.titre ?? c.libelle), c.fil ? h('span', { class: 'pal-fil' }, c.fil) : null)));
  liste.children[sel]?.scrollIntoView({ block: 'nearest' });
}

async function actualiser() {
  const q = champ.value.trim(), mots = norm(q).split(/\s+/).filter(Boolean), mien = ++jeton;
  const cmds = commandes().filter((c) => mots.every((m) => norm(c.libelle).includes(m)));
  const locales = mots.length ? tachesLocales(mots) : [];
  choix = [...locales, ...cmds]; sel = 0; rendre();
  if (locales.length >= 3 || q.length < 3) return;
  try {
    const r = await api(`/recherche?q=${encodeURIComponent(q)}&limite=${MAX}`);
    if (mien !== jeton) return;
    const connus = new Set(locales.map((x) => x.id));
    const plus = r.filter((x) => !connus.has(x.id)).slice(0, MAX - locales.length).map((x) => ({ id: x.id, titre: x.titre, fil: filLisible(x.fil_ariane).join(' › ') }));
    choix = [...locales, ...plus, ...cmds]; rendre();
  } catch { /* la recherche locale suffit */ }
}

function executer(c) {
  if (!c) return;
  dlg.close();
  if (c.id) ouvrir(c.id); else c.agir();
}

function construire() {
  champ = h('input', { type: 'text', class: 'pal-champ', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'palette-liste', autocomplete: 'off', placeholder: t('palette.placeholder'), 'aria-label': t('palette.titre') });
  liste = h('ul', { id: 'palette-liste', role: 'listbox', class: 'pal-liste' });
  dlg = h('dialog', { class: 'dlg palette', id: 'palette', 'aria-label': t('palette.titre') }, champ, liste);
  champ.addEventListener('input', () => { clearTimeout(minuteur); minuteur = setTimeout(() => { minuteur = 0; actualiser(); }, 120); });
  champ.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (choix.length) { sel = (sel + (e.key === 'ArrowDown' ? 1 : choix.length - 1)) % choix.length; rendre(); } }
    else if (e.key === 'Enter') { e.preventDefault(); if (minuteur) { clearTimeout(minuteur); minuteur = 0; actualiser(); } executer(choix[sel]); } // pourquoi : Entrée juste après la frappe agit sur la liste du texte saisi, pas sur l'ancienne
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  document.body.append(dlg);
}

export function ouvrirPalette() {
  if (!dlg) construire();
  if (dlg.open) { champ.select(); return; }
  champ.value = ''; actualiser(); dlg.showModal(); champ.focus();
  chargerEtiquettes().then(() => { if (dlg.open) actualiser(); });
}
