// Rôle : curseur « Performance ↔ Économie de jetons » — section des Réglages (cinq positions, famille par défaut,
// position effective et motif par harnais, quotas, consommation sur 7 jours), repère discret de l'en-tête,
// moteur prévu d'une tâche et bascule proposée (INV-ECO-1, INV-ECO-2).
// Frontières : GET/PUT /api/economie, GET /api/taches/{id}/economie ; accepter une bascule passe par POST /taches/{id}/moteur.
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { erreur, emit } from './store.js';
import { t, tn, LOCALE } from './langues.js';

const FAMILLES = [['rapide', t('economie.famille_rapide')], ['sonnet', 'Sonnet'], ['opus', 'Opus']];
const pct = (x) => `${Math.round(100 * x)} %`;
const nombre = (n) => Math.round(n).toLocaleString(LOCALE);
let zone = null;
let repere = null;

async function regler(corps) {
  try { remplir(await api('/economie', { methode: 'PUT', corps })); } catch (e) { erreur(e.message); recharger(); }
}

function quotas(s) {
  const lignes = Object.entries(s.quotas).flatMap(([hn, fs]) => fs.map((f) => h('li', null,
    t('economie.quota', { assistant: hn, nom: f.nom, part: pct(f.part), date: new Date(f.renouvellement * 1000).toLocaleString(LOCALE) }),
    f.rythme != null ? t('economie.rythme', { v: f.rythme.toFixed(2) }) : t('economie.rythme_nul'))));
  return lignes.length ? h('ul', { class: 'note', 'data-id': 'eco-quotas' }, lignes)
    : h('p', { class: 'note', 'data-id': 'eco-quotas' }, t('economie.aucun_quota'));
}

function conso(s) {
  const rangs = Object.entries(s.conso);
  if (!rangs.length) return h('p', { class: 'note', 'data-id': 'eco-conso' }, t('economie.aucune_conso'));
  return h('table', { class: 'eco-conso', 'data-id': 'eco-conso' },
    h('tr', null, [t('economie.col_assistant'), t('economie.col_seances'), t('economie.col_entree'), t('economie.col_sortie'), t('economie.col_cout')].map((x) => h('th', null, x))),
    rangs.map(([hn, c]) => h('tr', null, h('td', null, hn), h('td', null, nombre(c.tours || 0)),
      h('td', null, nombre(c.entree || 0)), h('td', null, nombre(c.sortie || 0)), h('td', null, (c.cout || 0).toFixed(2)))));
}

function libelle(s) {
  const lib = (s.positions.find(([p]) => p === s.position) || [])[1] || s.position;
  const motifs = Object.values(s.motifs || {});
  return { lib, motif: motifs.find((m) => !m.includes('neutre :') && !m.startsWith('pas de donnée')) || motifs[0] || '' };
}

function dessinerRepere(s) {
  if (!repere) return;
  const { lib, motif } = libelle(s);
  repere.textContent = `⚖ ${lib}`;
  repere.title = motif ? t('economie.curseur_motif', { motif }) : t('economie.curseur');
  repere.hidden = false;
}

function remplir(s) {
  dessinerRepere(s);
  emit('resume', ['economie', libelle(s).lib]);
  if (!zone?.isConnected) return;
  const i = s.positions.findIndex(([p]) => p === s.position);
  const { motif } = libelle(s);
  remplacer(zone,
    h('label', { class: 'rg-champ eco-curseur' }, t('economie.libelle'),
      h('input', { type: 'range', min: 0, max: s.positions.length - 1, step: 1, value: i, 'data-id': 'eco-position', 'aria-label': t('economie.curseur'),
        'aria-valuetext': s.positions[i][1], onchange: (e) => regler({ position: s.positions[Number(e.target.value)][0] }) }),
      t('economie.performance')),
    h('p', { class: 'eco-graduations' }, s.positions.map(([p, l]) => h('span', { class: p === s.position ? 'actif' : null }, l))),
    h('p', { class: 'note', 'data-id': 'eco-motif' }, motif ? t('economie.position_motif', { position: s.positions[i][1], motif }) : t('economie.position', { position: s.positions[i][1] })),
    h('label', { class: 'rg-champ' }, t('economie.famille_defaut'),
      h('select', { 'data-id': 'eco-famille', onchange: (e) => regler({ famille_defaut: e.target.value }) },
        FAMILLES.map(([v, l]) => h('option', { value: v, selected: v === s.famille_defaut ? true : null }, l)))),
    quotas(s), conso(s),
    h('p', { class: 'note' }, t('economie.note')));
}

export function recharger() {
  api('/economie').then(remplir).catch((e) => erreur(e.message));
}

export function sectionEconomie() {
  zone = h('div', { 'data-id': 'economie' }, h('p', { class: 'note' }, t('economie.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('economie.titre')), zone];
}

export function initEconomie() {
  const bouton = document.getElementById('btn-reglages');
  if (!bouton) return;
  repere = h('span', { class: 'eco-repere', id: 'eco-repere', 'data-id': 'eco-repere', hidden: true });
  (bouton.closest('.b-menu-zone') || bouton).before(repere); // le repère reste sur la rangée, le bouton est dans le menu (INV-DISCUSSION-1)
  recharger();
}

// Moteur prévu d'une tâche : famille et motif ; bascule proposée pour une conversation commencée.
export function blocEconomie(tache, surBascule) {
  const el = h('span', { class: 'eco-tache', 'data-id': 'eco-tache' });
  api(`/taches/${encodeURIComponent(tache.id)}/economie`).then((d) => {
    remplacer(el, h('span', { title: d.motif }, t('economie.prevu', { choix: d.harnais + (d.modele ? ` · ${d.modele}` : ''), motif: d.motif })),
      d.bascule ? h('button', { class: 'btn', type: 'button', 'data-id': 'eco-bascule', title: d.bascule.motif,
        onclick: () => surBascule(d.bascule.vers) }, t('economie.basculer', { vers: d.bascule.vers })) : null);
  }).catch(() => el.remove());
  return el;
}
