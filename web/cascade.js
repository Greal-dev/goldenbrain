// Rôle : vue en cascade du volet droit — sous-arbre des tâches en tableau indenté repliable,
// compteurs-filtres par statut, activité en direct, tours en compact (les propositions vivent dans leur déroulant, INV-DEROULANT-1).
// Frontières : lit S (arbre, état, filtres) ; replis et portée sont de l'affichage ; ouvrir une tâche passe par store.ouvrir.
// Performance : le squelette est construit une fois (défilement conservé) ; les lignes sont refaites d'un bloc (~120)
// et seule l'activité en direct est patchée sur place (un clic en cours ne se perd pas pendant un flux SSE).
import { t, tn } from './langues.js';
import { h, remplacer, libelleStatut, nomLisible, majCourt, depuis, groupeStatut, ORDRE_STATUTS } from './dom.js';
import { STATUTS_COURTS, statutsActifs, passeStatut, basculerStatut, effacerStatuts, comptesStatut } from './filtres.js';
import { barreLot, caseLigne, caseTout, majLot, basculerSel } from './lot.js';
import { deroulant } from './deroulant.js';
import { S, on, ouvrir, ouvrirVue, ouvrirNote, parcourir, chemin, fixerToutes, cleNoeud as cle } from './store.js';
import { cheminContexte } from './ponts.js';
import { majBascule } from './arbre.js';
import { brancher, actionsLigne } from './glisser.js';
import { reduire } from './transfo.js';
import { rendreChangeable } from './statut.js';
import { celluleEcheance, cellulePriorite, comparer } from './temps.js';
import { repereIA, compteIA, surOccupees } from './verrou.js';
import { pastilleMoi } from './executant.js';
import { boutonConversation, majConversation } from './pilotage.js';
import { majReglageConteneur } from './execution.js';
import { ouvrirAccueil } from './accueil.js';

const CLE = 'orch.cascade.replis';
let replis = (() => { try { return JSON.parse(localStorage.getItem(CLE) || '{}'); } catch { return {}; } })(); // {cle: true} = replié
let tri = { col: null, sens: 1 }; // tri des tâches sœurs par échéance ou priorité (un clic : croissant, deux : décroissant, trois : arbre d'origine)
let coque = null, ref = {}, visibles = new Map(), cleFocus = null, porteeAff, topSauve = 0, sigTours = null;

const sauver = () => localStorage.setItem(CLE, JSON.stringify(replis));
const filtreActif = () => statutsActifs().length > 0;
const estOuvert = (n) => filtreActif() || !replis[cle(n)];
const point = (s) => h('span', { class: `pastille st-${s || 'inconnu'}`, 'aria-hidden': 'true' });
const tourDe = (id) => S.etat.tours.find((x) => x.tache === id);
const derniere = (x) => (x.dernier || '').split('\n').filter((l) => l.trim()).at(-1) || t('cascade.demarrage');

function compter(ns) {
  const c = {};
  for (const n of parcourir(ns)) if (n.type === 'tache') { const g = groupeStatut(n.statut); c[g] = (c[g] || 0) + 1; }
  return c;
}
// Une tâche qui ne correspond pas mais porte une descendante qui correspond reste, en grisé (contexte).
function filtrer(ns) {
  const r = [];
  for (const n of ns) {
    const enf = filtrer(n.enfants || []);
    const ok = n.type === 'tache' && passeStatut(n);
    if (ok || enf.length) r.push({ ...n, enfants: enf, ctx: n.type === 'tache' && !ok });
  }
  return r;
}
// Seules les tâches sœurs se réordonnent, aux places qu'elles occupaient : projets et opérations ne bougent pas.
function trier(ns) {
  const sorties = ns.map((n) => ({ ...n, enfants: n.enfants ? trier(n.enfants) : n.enfants }));
  if (!tri.col) return sorties;
  const places = sorties.flatMap((n, i) => (n.type === 'tache' ? [i] : []));
  const triees = places.map((i) => sorties[i]).sort(comparer(tri.col, tri.sens));
  places.forEach((i, k) => { sorties[i] = triees[k]; });
  return sorties;
}
function aplatir(ns, niveau, out) {
  for (const n of ns) {
    out.push({ n, niveau });
    if (n.enfants.length && estOuvert(n)) aplatir(n.enfants, niveau + 1, out);
  }
  return out;
}

// --- cellules ---
function activite(n) {
  const tr = tourDe(n.id);
  if (tr) return [h('span', { class: 'tourne', title: t('cascade.seance_titre') }), h('span', { class: 'act-txt' }, derniere(tr))];
  switch (n.etat_execution) {
    case 'en_cours': return [h('span', { class: 'tourne', title: t('cascade.seance_titre') }), h('span', { class: 'act-txt' }, t('cascade.seance'))];
    case 'en_file': return [h('span', { class: 'file', title: t('cascade.file_titre') }), h('span', { class: 'act-txt' }, t('cascade.file'))];
    case 'interrompu': return [h('span', { class: 'interrompu', title: t(n.reprise_auto ? 'cascade.reprise_auto_titre' : 'cascade.interrompu_titre') }, '!'), h('span', { class: 'act-txt' }, t(n.reprise_auto ? 'cascade.reprise_auto' : 'cascade.interrompu'))];
    case 'en_pause': return [h('span', { class: 'echec', title: t('cascade.quota_titre') }, '⏸'), h('span', { class: 'act-txt' }, S.etat.pauses?.[n.id] || t('cascade.pause_quota'))];
    default: return n.echec ? [h('span', { class: 'echec', title: t('cascade.echec_titre', { motif: n.echec }) }, '!'), h('span', { class: 'act-txt' }, t('cascade.echec'))] : [];
  }
}
const sigActivite = (n) => { const tr = tourDe(n.id); return tr ? `t${derniere(tr)}` : `${n.etat_execution || ''}${n.reprise_auto ? 'r' : ''}${n.echec ? 'e' : ''}`; };
const texteActivite = (n) => { const tr = tourDe(n.id); return tr ? derniere(tr) : ''; };

function compteursGroupe(n) {
  const c = compter(n.enfants);
  const tours = [...parcourir(n.enfants)].filter((x) => x.type === 'tache' && (x.etat_execution === 'en_cours' || tourDe(x.id))).length;
  const items = ORDRE_STATUTS.filter((s) => c[s]);
  const lib = [...items.map((s) => t('cascade.n_statut', { n: c[s], statut: libelleStatut(s).toLowerCase() })), tours ? tn('cascade.seances_n', tours) : null].filter(Boolean).join(', ');
  return h('div', { class: 'c-groupe', role: 'gridcell', 'aria-label': lib || t('cascade.aucune_tache') },
    items.map((s) => h('span', { class: 'gc-i', title: t('cascade.n_statut', { n: c[s], statut: libelleStatut(s).toLowerCase() }), 'aria-hidden': 'true' }, point(s), c[s])),
    tours ? h('span', { class: 'gc-i', title: tn('cascade.seances_n', tours), 'aria-hidden': 'true' }, h('span', { class: 'tourne' }), tours) : null,
    items.length ? null : h('span', { class: 'gc-vide' }, t('cascade.aucune_tache')));
}

function ligne({ n, niveau }) {
  const k = cle(n), enf = n.enfants.length > 0, ouvert = enf && estOuvert(n), tache = n.type === 'tache';
  const titre = h('div', { class: 'c-titre', role: 'gridcell', style: `padding-left:${niveau * 16 + 4}px` },
    tache && !n.ctx ? caseLigne(n) : null,
    h('span', { class: `chev${enf ? (ouvert ? ' ouvert' : '') : ' vide'}`, 'aria-hidden': 'true' }),
    n.type === 'conteneur' ? h('span', { class: 'ico-projet', role: 'img', 'aria-label': t('cascade.projet'), title: t('cascade.projet') }) : null,
    h('span', { class: 'c-t', title: nomLisible(n.titre) }, nomLisible(n.titre)), tache ? repereIA(n.id) : null, tache ? pastilleMoi(n) : null, compteIA(n));
  const cells = [titre];
  let cell = null;
  if (tache) {
    cell = h('div', { class: 'c-act', role: 'gridcell' }, activite(n));
    cell._sig = sigActivite(n);
    cell.title = texteActivite(n);
    const nl = n.liens || 0;
    cells.push(
      h('div', { class: 'c-st', role: 'gridcell' }, rendreChangeable(h('span', { class: 'st-lien' }, point(n.statut), h('span', null, libelleStatut(n.statut))), n),
        n.a_valider ? h('span', { class: 'tag', title: t('cascade.valider_titre') }, t('cascade.a_valider')) : null),
      cell,
      h('div', { class: 'c-sit', role: 'gridcell', title: n.situation || null }, n.situation || ''),
      h('div', { class: 'c-mot', role: 'gridcell', title: [n.harnais, n.modele].filter(Boolean).join(' · ') || t('cascade.moteur_defaut') }, [n.harnais, n.modele].filter(Boolean).join(' · ') || '—'),
      celluleEcheance(n), cellulePriorite(n),
      h('div', { class: 'c-lien', role: 'gridcell', title: nl ? tn('cascade.liens', nl) : null, 'aria-label': tn('cascade.liens', nl) }, nl ? `⇄ ${nl}` : ''),
      h('div', { class: 'c-maj', role: 'gridcell', title: n.maj || null }, majCourt(n.maj)));
  } else cells.push(compteursGroupe(n));
  cells.push(actionsLigne(n));
  const el = h('div', {
    class: `cl t-${n.type}${n.ctx ? ' ctx' : ''}${k === S.marque ? ' marque' : ''}`, role: 'row', draggable: n.deplacable ? 'true' : null, 'data-cle': k, 'data-niveau': niveau, 'aria-level': niveau + 1,
    'aria-expanded': enf ? String(ouvert) : null, tabindex: k === cleFocus ? '0' : '-1',
  }, cells);
  visibles.set(k, { n, el, cell });
  return el;
}

// --- rendu ---
function cheminPortee() { return S.portee ? chemin(S.arbre, (n) => cle(n) === S.portee) : null; }

function entete(c, racines) {
  const compte = compter(racines);
  const total = Object.values(compte).reduce((a, b) => a + b, 0);
  const crumb = (txt, f) => h('span', null, h('button', { class: 'crumb', type: 'button', onclick: f }, txt));
  remplacer(ref.fil, c ? [crumb(t('cascade.ensemble'), () => ouvrirVue('cascade', null)),
    ...c.slice(0, -1).map((a) => crumb(nomLisible(a.titre), () => ouvrirVue('cascade', cle(a)))), h('span', { 'aria-current': 'location' }, nomLisible(c.at(-1).titre))] : null);
  ref.fil.hidden = !c;
  const cont = c?.at(-1);
  ref.noteBtn.classList.add('f-notes'); ref.reduireBtn.classList.add('f-transformations'); ref.supprimerBtn.classList.add('danger');
  ref.noteBtn.hidden = cont?.type !== 'conteneur';
  ref.noteBtn.onclick = cont?.type === 'conteneur' ? () => ouvrirNote(cheminContexte(cont.id)) : null;
  ref.reduireBtn.hidden = cont?.type !== 'conteneur';
  ref.reduireBtn.onclick = cont?.type === 'conteneur' ? () => reduire(cont) : null;
  ref.supprimerBtn.hidden = cont?.type !== 'conteneur'; // INV-SUPPR-1 : en-tête de la vue, jamais dans les lignes de l'arbre
  ref.supprimerBtn.onclick = cont?.type === 'conteneur' ? () => import('./suppression.js').then((m) => m.supprimer({ conteneur: cont.id })) : null;
  ref.titre.textContent = c ? nomLisible(c.at(-1).titre) : t('cascade.vue_ensemble');
  majConversation(ref.chatBtn, ref.chat, cont);
  majReglageConteneur(ref.execution, cont); // INV-REGROUPE-1
  ref.total.textContent = tn(S.toutes ? 'cascade.total_toutes' : 'cascade.total_ouvertes', total);
  // INV-DEROULANT-1 : la pastille « Statut » dit le filtre actif et le compte ; les puces de statut se déroulent.
  const actifs = statutsActifs();
  remplacer(ref.stBtn, h('span', null, t('filtres.statut')), actifs.length
    ? h('b', { class: 'casc-st-actifs' }, actifs.map((k) => STATUTS_COURTS.find(([c]) => c === k)?.[1] || k).join(', ')) : null, ' ▾');
  ref.stBtn.classList.toggle('actif', filtreActif());
  remplacer(ref.nsurn, filtreActif() ? t('filtres.n_sur_n', { n: compterFiltrees(racines), total }) : '');
  ref.racines = racines;
  ref.stDer.redessiner();
}
function puces(corps) {
  const cs = comptesStatut(ref.racines || S.arbre), actifs = statutsActifs();
  const chip = ([k, l]) => h('button', { class: 'chip-st', type: 'button', 'data-statut': k, 'aria-pressed': String(actifs.includes(k)), title: t('cascade.filtrer_titre', { statut: l }),
    onclick: () => basculerStatut(k) },
  point(k === 'a-moi' || k === 'a-valider' ? 'retour' : k), l, ' ', h('span', { class: 'n' }, cs[k] || 0));
  const liste = STATUTS_COURTS.filter(([k]) => cs[k] || actifs.includes(k));
  remplacer(corps, h('div', { class: 'casc-chips', role: 'group', 'aria-label': t('cascade.filtre_statut_groupe') }, liste.length ? liste.map(chip) : h('p', { class: 'vide' }, t('cascade.aucune')),
    filtreActif() ? h('button', { class: 'btn-discret', type: 'button', onclick: effacerStatuts }, t('cascade.effacer_filtre')) : null));
}
const compterFiltrees = (racines) => [...parcourir(racines)].filter((x) => x.type === 'tache' && passeStatut(x)).length;

function pastilleTour(x) {
  return h('button', { class: 'live-i', type: 'button', 'data-tour': x.tache, title: x.titre, onclick: () => ouvrir(x.tache) },
    h('span', { class: 'tourne' }), h('b', null, x.titre), h('span', { class: 'live-act' }, derniere(x)), h('span', { class: 'live-t' }, depuis(x.depuis)));
}
function majLive() {
  const tours = S.etat.tours || [];
  const sig = tours.map((x) => x.tache).join('|');
  if (sig === sigTours) {
    for (const x of tours) {
      const el = ref.live.querySelector(`[data-tour="${CSS.escape(x.tache)}"]`);
      if (!el) continue;
      el.querySelector('.live-act').textContent = derniere(x);
      el.querySelector('.live-t').textContent = depuis(x.depuis);
    }
    return;
  }
  sigTours = sig;
  ref.live.hidden = !tours.length;
  remplacer(ref.live, tours.length ? [h('span', { class: 'b-lib' }, t('cascade.en_direct')), ...tours.map(pastilleTour)] : null);
}

// Vault vide (premier lancement après « Plus tard ») : trois gestes plutôt qu'un « Chargement… » sans fin (audit L3, A1).
function videGuide() {
  const clic = (sel) => () => document.querySelector(sel)?.click();
  return h('div', { class: 'vide-guide', 'data-id': 'vide-guide' },
    h('strong', {}, t('cascade.vide_titre')),
    h('span', {}, t('cascade.vide_texte')),
    h('div', { class: 'vide-actions' },
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'vide-creer', onclick: clic('#btn-nouvelle') }, t('cascade.vide_creer')),
      h('button', { class: 'btn', type: 'button', 'data-id': 'vide-importer', onclick: () => ouvrirAccueil() }, t('cascade.vide_importer'))),
    h('small', {}, t('cascade.vide_vault')));
}

function corps(racines) {
  const top = ref.defile.scrollTop;
  const actif = ref.defile.contains(document.activeElement) ? document.activeElement.dataset?.cle : null;
  const arbre = trier(filtreActif() ? filtrer(racines) : racines);
  const rows = aplatir(arbre, 0, []);
  visibles = new Map();
  if (!rows.some((r) => cle(r.n) === cleFocus)) cleFocus = rows[0] ? cle(rows[0].n) : null;
  remplacer(ref.corps, rows.map(ligne));
  ref.vide.hidden = rows.length > 0;
  if (!filtreActif() && !S.arbre.length && S.arbreCharge) remplacer(ref.vide, videGuide());
  else remplacer(ref.vide, filtreActif() ? t('cascade.aucune_correspondance') : (S.arbre.length ? t('cascade.aucune') : t('cascade.chargement')));
  ref.defile.scrollTop = top;
  if (actif) visibles.get(actif)?.el.focus({ preventScroll: true });
}

function majTout() {
  const c = cheminPortee();
  if (S.portee && !c && S.arbre.length) S.portee = null; // la portée a disparu de l'arbre
  const racines = (S.portee && c) ? c.at(-1).enfants : S.arbre;
  if (S.portee !== porteeAff) { porteeAff = S.portee; topSauve = 0; ref.defile.scrollTop = 0; }
  entete(c, racines); majEnteteTri(); majLive(); corps(racines); majLot(); // INV-DEROULANT-1 : les propositions se lisent dans le déroulant de la barre, plus en zone permanente
}

function majActivite() {
  majLive();
  for (const { n, cell } of visibles.values()) {
    if (!cell) continue;
    const sig = sigActivite(n);
    if (cell._sig === sig) continue;
    cell._sig = sig; cell.title = texteActivite(n);
    remplacer(cell, activite(n));
  }
}

// --- interactions ---
function basculer(n) {
  const k = cle(n);
  if (filtreActif()) return;
  if (replis[k]) delete replis[k]; else replis[k] = true;
  sauver(); majTout();
}
function toutBasculer(replier) {
  const racines = cheminPortee()?.at(-1).enfants ?? S.arbre;
  replis = {};
  if (replier) for (const n of parcourir(racines)) if ((n.enfants || []).length) replis[cle(n)] = true;
  sauver(); majTout();
}
const noeudDe = (el) => visibles.get(el?.dataset?.cle)?.n;

function surTouche(e) {
  const rows = [...ref.corps.querySelectorAll('.cl')];
  const i = rows.indexOf(document.activeElement);
  if (i < 0) return;
  const n = noeudDe(rows[i]), niv = +rows[i].dataset.niveau, enf = n.enfants.length > 0;
  const aller = (j) => { if (rows[j]) { rows[j].focus(); e.preventDefault(); } };
  switch (e.key) {
    case 'ArrowDown': return aller(i + 1);
    case 'ArrowUp': return aller(i - 1);
    case 'Home': return aller(0);
    case 'End': return aller(rows.length - 1);
    case 'ArrowRight':
      e.preventDefault();
      if (enf && !estOuvert(n)) basculer(n); else if (enf) rows[i + 1]?.focus();
      return;
    case 'ArrowLeft':
      e.preventDefault();
      if (enf && estOuvert(n) && !filtreActif()) basculer(n);
      else for (let j = i - 1; j >= 0; j--) if (+rows[j].dataset.niveau < niv) { rows[j].focus(); break; }
      return;
    case 'x': if (n.type === 'tache' && !n.ctx) { e.preventDefault(); basculerSel(n.id); } return; // sélection en bloc au clavier
    case 'Enter': e.preventDefault(); if (n.type === 'tache') ouvrir(n.id); else basculer(n); return;
    case ' ': e.preventDefault(); if (enf) basculer(n); else if (n.type === 'tache') ouvrir(n.id);
  }
}

function colonnes() {
  const col0 = (c, txt) => h('div', { role: 'columnheader', class: c, title: txt }, txt);
  const triable = (col, txt) => {
    const b = h('button', { class: 'tri', type: 'button', 'data-tri': col, title: t(col === 'echeance' ? 'cascade.trier_echeance' : 'cascade.trier_priorite'), onclick: () => basculerTri(col) }, txt, h('span', { class: 'tri-sens', 'aria-hidden': 'true' }));
    return h('div', { role: 'columnheader', class: 'c-th', 'data-col': col, 'aria-sort': 'none' }, b);
  };
  return h('div', { class: 'cl cl-tete', role: 'row' }, h('div', { role: 'columnheader', class: 'c-th-titre', title: t('cascade.col_titre') }, caseTout(() => [...ref.corps.querySelectorAll('.cl:not(.ctx) .c-sel')]), t('cascade.col_titre')), col0('', t('cascade.col_statut')), col0('', t('cascade.col_activite')), col0('', t('cascade.col_situation')), col0('', t('cascade.col_moteur')),
    triable('echeance', t('cascade.col_echeance')), triable('priorite', t('cascade.col_priorite')), col0('c-lien', t('cascade.col_liens')), col0('c-maj', t('cascade.col_maj')));
}
function basculerTri(col) {
  if (tri.col !== col) tri = { col, sens: 1 };
  else if (tri.sens === 1) tri.sens = -1;
  else tri = { col: null, sens: 1 };
  majTout();
}
function majEnteteTri() {
  for (const th of ref.defile.querySelectorAll('.c-th')) {
    const actif = th.dataset.col === tri.col;
    th.setAttribute('aria-sort', actif ? (tri.sens === 1 ? 'ascending' : 'descending') : 'none');
    th.querySelector('.tri-sens').textContent = actif ? (tri.sens === 1 ? '▲' : '▼') : '';
  }
}
function construire() {
  ref = {};
  ref.fil = h('nav', { class: 'fil casc-fil', 'aria-label': t('cascade.fil') });
  ref.titre = h('h2', { class: 'casc-titre' });
  ref.total = h('span', { class: 'casc-total' });
  ref.stBtn = h('button', { class: 'btn petit casc-st-btn', type: 'button', id: 'btn-statuts', title: t('cascade.filtre_statut_groupe') });
  const stPanneau = h('div', { class: 'panneau casc-st-panneau', id: 'panneau-statuts', hidden: true });
  ref.stDer = deroulant({ bouton: ref.stBtn, panneau: stPanneau, remplir: puces });
  ref.nsurn = h('span', { class: 'casc-nsurn', role: 'status' });
  ref.lot = barreLot();
  ref.chips = h('div', { class: 'casc-l2' }, h('span', { class: 'casc-st-zone' }, ref.stBtn, stPanneau), ref.nsurn, ref.lot);
  ref.live = h('div', { class: 'casc-live', 'aria-label': t('cascade.seances_label'), hidden: true });
  ref.corps = h('div', { role: 'rowgroup', class: 'casc-corps' });
  ref.vide = h('p', { class: 'vide', 'aria-live': 'polite' });
  ref.defile = h('div', { class: 'casc-defile', role: 'treegrid', 'aria-label': t('cascade.grille') }, colonnes(), ref.corps, ref.vide);
  ref.defile.addEventListener('scroll', () => { topSauve = ref.defile.scrollTop; });
  ref.defile.addEventListener('keydown', surTouche);
  brancher(ref.defile, ref.defile, 26);
  ref.defile.addEventListener('focusin', (e) => {
    const k = e.target.dataset?.cle;
    if (!k || k === cleFocus) return;
    ref.corps.querySelector('.cl[tabindex="0"]')?.setAttribute('tabindex', '-1');
    e.target.setAttribute('tabindex', '0');
    cleFocus = k;
  });
  ref.defile.addEventListener('click', (e) => {
    const row = e.target.closest('.cl[data-cle]');
    const n = noeudDe(row);
    if (!n || e.target.closest('.st-chg, .st-refus, .c-sel')) return;
    cleFocus = cle(n);
    if (e.target.classList.contains('chev')) basculer(n); else if (n.type === 'tache') ouvrir(n.id); else basculer(n);
  });
  const bascule = h('div', { class: 'bascule', role: 'group', 'aria-label': t('cascade.affichage') },
    h('button', { type: 'button', 'data-vue': 'ouvertes', onclick: () => fixerToutes(false) }, t('cascade.ouvertes')),
    h('button', { type: 'button', 'data-vue': 'toutes', onclick: () => fixerToutes(true) }, t('cascade.toutes')));
  ref.noteBtn = h('button', { class: 'btn petit', type: 'button', hidden: true, title: t('cascade.note_titre') }, t('cascade.note_btn'));
  ref.reduireBtn = h('button', { class: 'btn petit', type: 'button', hidden: true, title: t('cascade.reduire_titre') }, t('cascade.reduire'));
  ref.supprimerBtn = h('button', { class: 'btn petit', type: 'button', hidden: true, 'data-id': 'supprimer-projet', title: t('cascade.supprimer_titre') }, t('cascade.supprimer'));
  ref.chat = h('div', { class: 'casc-chat', hidden: true });
  ref.chatBtn = boutonConversation(ref.chat);
  ref.execution = h('span', { class: 'casc-execution' });
  const outils = h('div', { class: 'casc-outils' }, ref.chatBtn, ref.execution, ref.noteBtn, ref.reduireBtn, ref.supprimerBtn,
    h('button', { class: 'btn petit', type: 'button', onclick: () => toutBasculer(true) }, t('cascade.replier')),
    h('button', { class: 'btn petit', type: 'button', onclick: () => toutBasculer(false) }, t('cascade.deplier')), bascule);
  coque = h('div', { class: 'casc' },
    h('div', { class: 'casc-tete' }, ref.fil, h('div', { class: 'casc-l1' }, ref.titre, ref.total, ref.chips, outils), ref.chat),
    ref.live, ref.defile);
  sigTours = null;
}

export function dessinerCascade(racine) {
  if (!coque || coque.parentNode !== racine) {
    construire();
    remplacer(racine, coque);
    majBascule();
    majTout();
    ref.defile.scrollTop = topSauve;
    return;
  }
  majTout();
}
// Flux SSE : si l'ensemble des tours n'a pas changé, seule l'activité est patchée.
export function etatCascade(racine) {
  if (!coque || coque.parentNode !== racine) return dessinerCascade(racine);
  const sig = (S.etat.tours || []).map((x) => x.tache).join('|');
  if (sig !== sigTours) return majTout();
  majActivite();
}
export function initCascade() {
  on('filtre', () => { if (coque?.isConnected) majTout(); });
  surOccupees(() => { if (coque?.isConnected) majTout(); });
  on('deplier', (k) => { if (replis[k]) { delete replis[k]; sauver(); if (coque?.isConnected) majTout(); } });
  on('deplace', ({ cle: k, depuis }) => {
    if (!coque?.isConnected) return;
    const c = chemin(S.arbre, (n) => cle(n) === k);
    if (c) { c.slice(0, -1).forEach((n) => { delete replis[cle(n)]; }); sauver(); }
    cleFocus = k;
    majTout();
    const el = visibles.get(k)?.el;
    el?.scrollIntoView({ block: 'nearest' });
    if (depuis === ref.defile) el?.focus({ preventScroll: true });
  }); setInterval(() => { if (coque?.isConnected) majActivite(); }, 30000); }
