// Rôle : accueil d'un nouvel arrivant — parcours en 3 écrans (choisir, relire, valider) qui reprend ses projets et ses conversations.
// Frontières : GET /api/accueil, POST /api/accueil/{proposer,valider,plus-tard} (poste seulement, INV-ACCUEIL-1). Rien n'est écrit avant
// l'écran 3 (INV-ACCUEIL-2) : les corrections (renommer, décocher, glisser-déposer) ne vivent que dans le plan en mémoire du navigateur.
// INV-WEB-1 : aucun HTML injecté, tout passe par h(). Ouvert à la première arrivée (arbre vide) ou par « Relancer l'accueil » (Réglages).
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit } from './store.js';
import { t, tn, LANGUES, LANGUE, changerLangue } from './langues.js';

const RAISONS = {
  questions: t('accueil.raison_questions'),
  conversations: t('accueil.raison_conversations'),
  dossier: t('accueil.raison_dossier'),
  vault: t('accueil.raison_vault'),
};
const HARNAIS = { claude: 'Claude Code', codex: 'Codex' };
let E = null; // { ecran, plan, exclu:Set, bilan, dispo, vault, src }
let boite = null;

const lib = (s) => (s || '').split(', ').map((x) => ({ questions: t('accueil.source_questions'), conversations: t('accueil.source_conversations'), dossier: t('accueil.source_dossier'), vault: t('accueil.source_vault') }[x] || x)).join(' + ');

export async function ouvrirAccueil() {
  let d;
  try { d = await api('/accueil'); } catch (e) { erreur(e.message); return; }
  E = { ecran: 1, plan: null, exclu: new Set(), bilan: null, dispo: d.conversations || {}, vault: d.vault,
    vide: !!d.vide, obsidian: !!d.obsidian,
    src: { questions: { actif: !!d.vide, metier: '', roles: '', projets: '' }, conversations: { actif: false, harnais: Object.keys(d.conversations || {}).filter((k) => d.conversations[k]) },
      dossier: { actif: false, chemin: '' }, vault: { actif: false } } };
  boite?.remove();
  boite = h('div', { class: 'accueil', role: 'dialog', 'aria-modal': 'true', 'aria-label': t('accueil.titre'), 'data-id': 'accueil' });
  document.body.append(boite);
  dessiner();
}

export async function initAccueil() {
  try { if ((await api('/accueil')).propose) await ouvrirAccueil(); } catch { /* serveur distant ou injoignable : pas d'accueil */ }
}

// Langue (accueil et Réglages → Affichage) : réglage du poste ([interface] langue de config.toml, INV-LANGUE-1) ; la page se recharge dans la langue choisie.
export function choixLangue() {
  return h('select', { 'data-id': 'langue', 'aria-label': t('langue.titre'),
    onchange: (e) => changerLangue(e.target.value).catch((err) => erreur(err.message)) },
  Object.entries(LANGUES).map(([v, l]) => h('option', { value: v, selected: v === LANGUE ? true : null }, l)));
}

// La boîte est modale : le guide s'ouvre dans un nouvel onglet, sans perdre le parcours en cours.
const aide = () => h('a', { class: 'btn aide', href: '/#guide=organiser-votre-second-cerveau', target: '_blank', rel: 'noopener',
  title: t('accueil.guide'), 'aria-label': t('accueil.guide'), 'data-id': 'accueil-guide' }, '?');

function fermer() { boite?.remove(); boite = null; E = null; }
const pas = (n) => h('ol', { class: 'ac-pas' }, [t('accueil.pas_choisir'), t('accueil.pas_relire'), t('accueil.pas_valider')].map((x, i) => h('li', { class: i + 1 === E.ecran ? 'en-cours' : i + 1 < E.ecran ? 'fait' : null }, `${i + 1}. ${x}`)));

function dessiner() {
  if (!boite || !E) return;
  const corps = E.ecran === 1 ? ecranChoisir() : E.ecran === 2 ? ecranRelire() : ecranValider();
  remplacer(boite, h('div', { class: 'ac-carte' }, h('h2', null, t('accueil.bienvenue'), ' ', aide()), E.ecran === 1 ? h('label', { class: 'ac-langue' }, t('langue.titre'), ' ', choixLangue()) : null, pas(), corps));
}

// ── Écran 1 : choisir les sources, de la moins à la plus intrusive ──────────────────────────────
function source(cle, titre, ...champs) {
  const s = E.src[cle];
  return h('fieldset', { class: 'ac-source', 'data-id': `src-${cle}` },
    h('label', { class: 'case' }, h('input', { type: 'checkbox', 'data-id': `actif-${cle}`, checked: s.actif ? true : null, onchange: (e) => { s.actif = e.target.checked; dessiner(); } }), h('b', null, titre)),
    h('div', { class: 'note' }, RAISONS[cle]), s.actif ? champs : null);
}

function ecranChoisir() {
  const q = E.src.questions, c = E.src.conversations, d = E.src.dossier;
  const ligne = (etiq, cle, obj, ph) => h('label', { class: 'ac-champ' }, etiq, h('input', { type: 'text', 'data-id': `${cle}`, value: obj[cle.split('-')[1]], placeholder: ph, oninput: (e) => { obj[cle.split('-')[1]] = e.target.value; } }));
  const harnais = Object.entries(E.dispo).map(([k, n]) => h('label', { class: 'case' },
    h('input', { type: 'checkbox', 'data-id': `harnais-${k}`, disabled: n ? null : true, checked: n && c.harnais.includes(k) ? true : null,
      onchange: (e) => { c.harnais = e.target.checked ? [...new Set([...c.harnais, k])] : c.harnais.filter((x) => x !== k); } }), ` ${HARNAIS[k] || k} ${tn('accueil.trouvees', n)}`));
  return [
    E.vide ? h('p', { 'data-id': 'accueil-vide' }, t('accueil.vide')) : null,
    h('p', null, t('accueil.cochez')),
    source('questions', t('accueil.questions'), ligne(t('accueil.roles'), 'q-roles', q, t('accueil.roles_ph')), ligne(t('accueil.projets'), 'q-projets', q, t('accueil.projets_ph')), ligne(t('accueil.metier'), 'q-metier', q, t('accueil.metier_ph'))),
    source('dossier', t('accueil.dossier'), ligne(t('accueil.chemin'), 'd-chemin', d, t('accueil.chemin_ph'))),
    source('conversations', t('accueil.conversations'), h('div', null, harnais)),
    source('vault', t('accueil.vault'), h('div', { class: 'note' }, t('accueil.vault_note', { vault: E.vault })), E.obsidian ? h('div', { class: 'note', 'data-id': 'accueil-obsidian' }, t('accueil.obsidian')) : null),
    h('p', { class: 'note' }, t('accueil.agenda')),
    h('div', { class: 'ac-actions' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'accueil-plus-tard', onclick: async () => { try { await post('/accueil/plus-tard', {}); } catch (e) { erreur(e.message); } fermer(); } }, t('accueil.plus_tard')),
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'accueil-proposer', onclick: proposer }, t('accueil.proposer'))),
  ];
}

async function proposer() {
  const s = E.src, corps = {};
  for (const k of Object.keys(s)) if (s[k].actif) corps[k] = { ...s[k] };
  const liste = (x) => (x || '').split(',').map((y) => y.trim()).filter(Boolean);
  if (corps.questions) { corps.questions.roles = liste(s.questions.roles); corps.questions.projets = liste(s.questions.projets); }
  if (!Object.keys(corps).length) { erreur(t('accueil.une_source')); return; }
  const aff = boite.querySelector('[data-id="accueil-proposer"]'); if (aff) aff.disabled = true;
  try { E.plan = await post('/accueil/proposer', { sources: corps }); } catch (e) { erreur(e.message); dessiner(); return; }
  E.exclu = new Set(); E.ecran = 2; dessiner();
}

// ── Écran 2 : relire, corriger (renommer, décocher, glisser-déposer) ────────────────────────────
let porte = null; // { genre, id } de l'élément en cours de glissé
const coche = (id) => h('input', { type: 'checkbox', 'aria-label': t('accueil.garder'), 'data-id': `garde-${id}`, checked: E.exclu.has(id) ? null : true, onchange: (e) => { e.target.checked ? E.exclu.delete(id) : E.exclu.add(id); dessiner(); } });
const nom = (o, cle, id) => h('input', { type: 'text', class: 'ac-nom', 'data-id': `nom-${id}`, value: o[cle], 'aria-label': t('accueil.renommer'), onchange: (e) => { o[cle] = e.target.value; } });
const src = (o) => h('span', { class: 'ac-src', title: t('accueil.origine') }, lib(o.source));
function cible(el, accepte, depose) {
  el.addEventListener('dragover', (e) => { if (porte && accepte(porte)) { e.preventDefault(); el.classList.add('survol'); } });
  el.addEventListener('dragleave', () => el.classList.remove('survol'));
  el.addEventListener('drop', (e) => { if (porte && accepte(porte)) { e.preventDefault(); e.stopPropagation(); depose(porte); porte = null; dessiner(); } });
  return el;
}
function glissable(el, genre, id) {
  el.draggable = true;
  el.addEventListener('dragstart', (e) => { porte = { genre, id }; e.dataTransfer?.setData('text/plain', id); e.stopPropagation(); });
  el.addEventListener('dragend', () => { porte = null; });
  return el;
}

function ligneTache(tk) {
  return glissable(h('li', { class: 'ac-tache', 'data-id': `tache-${tk.id}` }, coche(tk.id), nom(tk, 'titre', tk.id), src(tk),
    tk.harnais ? h('span', { class: 'note' }, ` ${HARNAIS[tk.harnais] || tk.harnais}`) : null), 'tache', tk.id);
}
function ligneProjet(p) {
  const p0 = E.plan, taches = p0.taches.filter((tk) => tk.projet === p.id);
  const li = h('li', { class: 'ac-projet' + (p.existe ? ' existe' : ''), 'data-id': `projet-${p.id}` },
    h('div', { class: 'ac-ligne' }, coche(p.id), nom(p, 'nom', p.id), src(p), p.existe ? h('span', { class: 'note' }, t('accueil.deja')) : null),
    p.resume ? h('div', { class: 'note' }, p.resume) : null, h('ul', null, taches.map(ligneTache)));
  glissable(li, 'projet', p.id);
  return cible(li, (g) => g.genre === 'tache', (g) => { p0.taches.find((tk) => tk.id === g.id).projet = p.id; });
}
function blocCasquette(c) {
  const p0 = E.plan, ops = p0.operations.filter((o) => o.casquette === c.id), libres = p0.projets.filter((p) => p.casquette === c.id && !p.operation);
  const el = h('section', { class: 'ac-casquette', 'data-id': `casquette-${c.id}` },
    h('div', { class: 'ac-ligne' }, coche(c.id), nom(c, 'nom', c.id), src(c)),
    ops.map((o) => cible(h('div', { class: 'ac-operation', 'data-id': `operation-${o.id}` },
      h('div', { class: 'ac-ligne' }, nom(o, 'nom', o.id), h('span', { class: 'note' }, t('accueil.operation')), src(o)),
      h('ul', null, p0.projets.filter((p) => p.operation === o.id).map(ligneProjet))), (g) => g.genre === 'projet', (g) => {
      const p = p0.projets.find((x) => x.id === g.id); p.operation = o.id; p.casquette = o.casquette; })),
    h('ul', null, libres.map(ligneProjet)));
  return cible(el, (g) => g.genre === 'projet', (g) => { const p = p0.projets.find((x) => x.id === g.id); p.operation = null; p.casquette = c.id; });
}

function ecranRelire() {
  const p = E.plan;
  return [
    h('p', null, t('accueil.voici')),
    p.squelette ? h('section', { class: 'ac-casquette', 'data-id': 'accueil-depart' },
      h('div', { class: 'ac-ligne' }, coche('squelette'), h('b', null, t('accueil.depart'))), h('div', { class: 'note' }, t('accueil.depart_aide')),
      h('div', { class: 'note' }, [...p.squelette.dossiers.map((d) => `${d}/`), ...p.squelette.notes].join(' · '))) : null,
    h('div', { class: 'ac-plan', 'data-id': 'accueil-plan' }, p.casquettes.map(blocCasquette)),
    p.laisses.length ? h('details', { class: 'ac-laisses', 'data-id': 'accueil-laisses' }, h('summary', null, tn('accueil.laisses', p.laisses.length)),
      h('ul', null, p.laisses.map((l) => h('li', null, `${l.titre} — ${l.pourquoi}`)))) : null,
    h('p', { class: 'note', 'data-id': 'accueil-confidentialite' }, p.confidentialite?.texte || ''),
    h('p', { class: 'note' }, t('accueil.lu', { lu: (p.lu || []).join(' ; ') })),
    h('div', { class: 'ac-actions' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'accueil-retour', onclick: () => { E.ecran = 1; dessiner(); } }, t('accueil.retour')),
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'accueil-suite', onclick: () => { E.ecran = 3; dessiner(); } }, t('accueil.continuer'))),
  ];
}

// Plan à envoyer : sans les éléments décochés, ni ce qui en dépend (tâches et notes d'un projet retiré, projets d'une casquette retirée).
function planGarde() {
  const p = E.plan, x = E.exclu;
  const casquettes = p.casquettes.filter((c) => !x.has(c.id));
  const cids = new Set(casquettes.map((c) => c.id));
  const projets = p.projets.filter((q) => !x.has(q.id) && cids.has(q.casquette));
  const pids = new Set(projets.map((q) => q.id));
  return { ...p, squelette: x.has('squelette') ? null : p.squelette, casquettes, operations: p.operations.filter((o) => cids.has(o.casquette)), projets,
    taches: p.taches.filter((tk) => !x.has(tk.id) && pids.has(tk.projet)),
    notes: p.notes.filter((n) => (n.projet ? pids.has(n.projet) : cids.has(n.casquette))) };
}

// ── Écran 3 : valider en un geste ───────────────────────────────────────────────────────────────
function ecranValider() {
  if (E.bilan) {
    const c = E.bilan.crees;
    return [h('p', { 'data-id': 'accueil-bilan' }, c.dossiers ? t('accueil.fait_dossiers', { dossiers: c.dossiers, casquettes: c.casquettes, projets: c.projets, taches: c.taches, notes: c.notes })
      : t('accueil.fait', { casquettes: c.casquettes, projets: c.projets, taches: c.taches, notes: c.notes })),
      E.bilan.ignores.length ? h('details', null, h('summary', null, tn('accueil.deja_la', E.bilan.ignores.length)), h('ul', null, E.bilan.ignores.map((i) => h('li', null, i)))) : null,
      h('div', { class: 'ac-actions' }, h('button', { class: 'btn primaire', type: 'button', 'data-id': 'accueil-fermer', onclick: fermer }, t('accueil.ouvrir')))];
  }
  const g = planGarde();
  const n = { casquettes: g.casquettes.length, operations: g.operations.length, projets: g.projets.filter((q) => !q.existe).length, taches: g.taches.length, notes: g.notes.length };
  return [
    h('p', { 'data-id': 'accueil-recap' }, g.squelette ? t('accueil.recap_depart', { ...n, dossiers: g.squelette.dossiers.length }) : t('accueil.recap', n)),
    h('p', { class: 'note' }, t('accueil.rejouer')),
    h('div', { class: 'ac-actions' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'accueil-retour', onclick: () => { E.ecran = 2; dessiner(); } }, t('accueil.retour')),
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'accueil-valider', onclick: valider }, t('accueil.valider'))),
  ];
}

async function valider() {
  try { E.bilan = await post('/accueil/valider', { plan: planGarde() }); } catch (e) { erreur(e.message); return; }
  emit('recharger-arbre'); dessiner();
}

export function sectionAccueil() {
  return [h('h3', null, t('accueil.titre')),
    h('p', { class: 'note' }, t('accueil.reprendre')),
    h('button', { class: 'btn', type: 'button', 'data-id': 'relancer-accueil', onclick: ouvrirAccueil }, t('accueil.relancer'))];
}
