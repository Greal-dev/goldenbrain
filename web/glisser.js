// Rôle : arbre libre, code partagé par le volet gauche et la cascade — glisser-déposer, « monter d'un niveau »,
// « Déplacer vers… » au clavier, ligne d'information avec annulation, menu d'un dépôt tâche sur tâche.
// Frontières : l'admissibilité d'un geste est calculée sur l'arbre en mémoire (aucun appel serveur au survol) ;
// seul le dépôt agit : une tâche par POST /arbre/deplacer ou /arbre/monter (la réponse {noeuds} remplace S.arbre) ;
// un projet ou une opération par le plan de alignement-plan.js (son dossier se déplace, INV-ARBRE-2).
// INV-WEB-1 : aucun HTML injecté, tout passe par h().
import { t, tn } from './langues.js';
import { h, remplacer } from './dom.js';
import { S, emit, erreur, cleNoeud as cle, chemin } from './store.js';
import { ouvert } from './interface.js';
import { post } from './api.js';
import { lier } from './liens.js';
import { rafraichirEcarts } from './alignement.js';
import { voirPlan } from './alignement-plan.js';
import { info } from './info.js';
import { reduire } from './transfo.js';
import { nouvelleRoutine } from './routines.js';
import { lancerChaine } from './chaines.js';

const enc = encodeURIComponent;
const norm = (s) => (s || '').normalize('NFD').replace(/\p{M}/g, '').toLowerCase();
const TYPE = { casquette: t('glisser.type_casquette'), operation: t('glisser.type_operation'), conteneur: t('glisser.type_projet'), tache: t('glisser.type_tache') };

// Index de l'arbre complet (jamais la copie filtrée d'une vue) : clé -> {n, parent}.
function indexer() {
  const m = new Map();
  const visiter = (ns, parent) => { for (const n of ns) { m.set(cle(n), { n, parent }); visiter(n.enfants || [], n); } };
  visiter(S.arbre, null);
  return m;
}
const filDe = (en, idx) => {
  const fil = [];
  for (let p = en.parent; p; p = idx.get(cle(p))?.parent) fil.unshift(p.titre);
  return fil;
};

// Tableau des gestes du contrat (lot 4) : une tâche ne se dépose que sur une tâche ou un conteneur ;
// jamais sur soi-même ni sur un descendant ; déposer là où l'élément est déjà n'a aucun effet.
export function admis(src, cible, idx) {
  if (!src.deplacable || cle(src) === cle(cible)) return false;
  if (src.type !== 'tache' && !ouvert('alignement')) return false; // un projet se déplace avec son dossier : geste d'alignement
  // Par clé : la tâche ouverte dans le volet droit n'est pas toujours l'objet même de l'arbre.
  for (let p = idx.get(cle(cible))?.parent; p; p = idx.get(cle(p))?.parent) if (cle(p) === cle(src)) return false;
  if (idx.get(cle(src))?.parent === cible) return false;
  return src.type === 'tache' ? (cible.type === 'tache' || cible.type === 'conteneur') : cible.type !== 'tache';
}

// --- gestes ---
const retrouver = (n, idParent) => {
  const direct = chemin(S.arbre, (x) => x.id === n.id && x.type === n.type)?.at(-1);
  if (direct) return direct;
  // Une opération change d'identifiant avec son chemin : on la retrouve sous son nouveau parent.
  const p = idParent ? chemin(S.arbre, (x) => x.id === idParent)?.at(-1) : null;
  return p?.enfants?.find((x) => x.type === n.type && x.titre === n.titre) ?? null;
};

// INV-ARBRE-2 : un projet ou une opération se déplace avec son dossier — plan à blanc affiché, puis application
// (point de restauration git, tout ou rien). Une tâche garde le geste direct.
async function geste(o) {
  if (o.n.type !== 'tache') {
    voirPlan(null, { corps: o.corps, titre: o.annulation ? t('glisser.remettre', { titre: o.n.titre }) : t('glisser.deplacer_titre', { titre: o.n.titre }),
      fini: () => { rafraichirEcarts(); apres(o); } });
    return;
  }
  try { S.arbre = (await post(`/arbre/${o.route}?toutes=${S.toutes ? 1 : 0}`, o.corps)).noeuds; } catch (e) { erreur(e.message); return; } // 409 : l'arbre reste intact
  apres(o);
}

function apres({ corps, n, origine, nouveauParent, phrase, depuis, annulation }) {
  const nv = retrouver(n, nouveauParent?.id ?? corps.sous);
  if (nv) {
    if (S.portee === cle(n)) S.portee = cle(nv);
    S.marque = cle(nv);
    clearTimeout(geste.t); geste.t = setTimeout(() => { S.marque = null; document.querySelectorAll('.ligne.marque, .cl.marque').forEach((x) => x.classList.remove('marque')); }, 4000);
  }
  emit('arbre');
  if (nv) emit('deplace', { cle: cle(nv), depuis });
  if (annulation || !origine || !nv) { if (annulation) info(t('glisser.revenu', { titre: n.titre })); return; }
  info(phrase, [{ libelle: t('glisser.annuler'), action: () => deplacer(nv, origine, indexer(), depuis, true) }]);
}

export function deplacer(n, cible, idx, depuis, annulation = false) {
  return geste({ route: 'deplacer', corps: { noeud: n.id, sous: cible.id }, n, origine: idx.get(cle(n))?.parent, nouveauParent: cible,
    phrase: t('glisser.maintenant_sous', { titre: n.titre, cible: cible.titre }), depuis, annulation });
}
export function monter(n, idx, depuis) {
  const origine = idx.get(cle(n))?.parent;
  return geste({ route: 'monter', corps: { noeud: n.id }, n, origine, nouveauParent: origine ? idx.get(cle(origine))?.parent : null,
    phrase: t('glisser.remonte', { titre: n.titre }), depuis });
}

// Dépôt d'une tâche sur une tâche : existant, le geste n'agit pas seul (déplacer ≠ lier).
async function faireEnfant(idTache, cible) {
  try { await post(`/taches/${enc(idTache)}/deplacer`, { parent: cible.id }); emit('recharger'); } catch (e) { erreur(e.message); }
}
function menuDepot(x, y, source, cible) {
  const retour = document.activeElement;
  const fermer = () => { menu.remove(); document.removeEventListener('pointerdown', dehors, true); retour?.focus?.(); };
  const dehors = (e) => { if (!menu.contains(e.target)) fermer(); };
  const agir = (f) => async () => { fermer(); await f(); };
  const lierVers = (type) => async () => { if (await lier(source.id, type, cible.id)) emit('recharger'); };
  const item = (txt, f) => h('button', { class: 'menu-item', role: 'menuitem', type: 'button', onclick: agir(f) }, txt);
  const menu = h('div', { class: 'menu-depot', role: 'menu', 'aria-label': t('glisser.deposer', { source: source.titre, cible: cible.titre }),
    onkeydown: (e) => {
      const l = [...menu.querySelectorAll('.menu-item')], i = l.indexOf(document.activeElement);
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); fermer(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); l[(i + 1) % l.length].focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); l[(i - 1 + l.length) % l.length].focus(); }
      else if (e.key === 'Tab') { e.preventDefault(); l[(i + (e.shiftKey ? -1 : 1) + l.length) % l.length].focus(); }
    } },
  h('div', { class: 'menu-tete' }, h('b', null, source.titre), t('glisser.menu_sur'), h('b', null, cible.titre)),
  item(t('glisser.enfant'), () => faireEnfant(source.id, cible)),
  ...(ouvert('liens') ? [item(t('glisser.lier_alimente'), lierVers('alimente')), item(t('glisser.lier_prerequis'), lierVers('prerequis')), item(t('glisser.lier_voir_aussi'), lierVers('voir_aussi'))] : []),
  item(t('glisser.annuler'), async () => {}));
  document.body.append(menu);
  menu.style.left = `${Math.max(4, Math.min(x, innerWidth - menu.offsetWidth - 4))}px`;
  menu.style.top = `${Math.max(4, Math.min(y, innerHeight - menu.offsetHeight - 4))}px`;
  menu.querySelector('.menu-item').focus();
  document.addEventListener('pointerdown', dehors, true);
}

// --- « Déplacer vers… » (clavier) : recherche dans l'arbre en mémoire, cibles admises seulement ---
function dialogueVers(n, idx, depuis) {
  const cands = [...idx.values()].filter((e) => admis(n, e.n, idx)).map((e) => {
    const fil = filDe(e, idx);
    return { n: e.n, fil: fil.join(' › '), q: norm(`${e.n.titre} ${fil.join(' ')} ${TYPE[e.n.type]}`) };
  });
  let vue = [], actif = 0;
  const champ = h('input', { type: 'text', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'vers-liste', 'aria-autocomplete': 'list',
    autocomplete: 'off', placeholder: t('glisser.chercher'), 'aria-label': t('glisser.cible_label') });
  const liste = h('ul', { id: 'vers-liste', class: 'resultats', role: 'listbox', 'aria-label': t('glisser.cibles_label') });
  const statut = h('p', { class: 'note', 'aria-live': 'polite' });
  const dlg = h('dialog', { class: 'dlg', 'aria-label': t('glisser.deplacer_label', { titre: n.titre }) });
  const marquer = () => {
    [...liste.children].forEach((li, i) => { li.setAttribute('aria-selected', String(i === actif)); li.classList.toggle('actif', i === actif); });
    if (vue.length) { champ.setAttribute('aria-activedescendant', `vers-${actif}`); liste.children[actif]?.scrollIntoView({ block: 'nearest' }); }
  };
  const choisir = (c) => { dlg.close(); deplacer(n, c.n, idx, depuis); };
  const filtrer = () => {
    const mots = norm(champ.value).split(/\s+/).filter(Boolean);
    const tous = cands.filter((c) => mots.every((m) => c.q.includes(m)));
    vue = tous.slice(0, 40); actif = 0;
    statut.textContent = tous.length ? tn(tous.length > 40 ? 'glisser.cibles_limite' : 'glisser.cibles', tous.length) : t('glisser.aucune_cible');
    remplacer(liste, vue.map((c, i) => h('li', { id: `vers-${i}`, role: 'option', 'aria-selected': 'false', onmousedown: (e) => { e.preventDefault(); choisir(c); } },
      h('span', { class: 'res-titre' }, c.n.titre), h('span', { class: 'badge-type' }, TYPE[c.n.type]), h('span', { class: 'fil-mini' }, c.fil))));
    marquer();
  };
  champ.addEventListener('input', filtrer);
  champ.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && vue.length) { e.preventDefault(); actif = (actif + 1) % vue.length; marquer(); }
    else if (e.key === 'ArrowUp' && vue.length) { e.preventDefault(); actif = (actif - 1 + vue.length) % vue.length; marquer(); }
    else if (e.key === 'Enter') { e.preventDefault(); if (vue[actif]) choisir(vue[actif]); }
  });
  dlg.append(h('form', { method: 'dialog', class: 'dlg-form' }, h('h3', null, t('glisser.deplacer_vers_titre', { titre: n.titre })),
    h('div', { class: 'champ' }, champ, liste, statut),
    h('div', { class: 'dlg-actions' }, h('button', { type: 'button', class: 'btn', onclick: () => dlg.close() }, t('glisser.annuler')))));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  filtrer();
  dlg.showModal();
  champ.focus();
}

// Ouvre « Déplacer vers… » pour un élément : nœud de l'arbre, ou nœud minimal d'une tâche absente de l'arbre filtré.
export const deplacerVers = (n, depuis = null) => dialogueVers(n, indexer(), depuis);

// Boutons de ligne, visibles au survol et au focus (CSS) ; les clics sont captés par `brancher`.
export function actionsLigne(n) {
  const projet = n.type === 'conteneur';
  const fixe = projet && !ouvert('alignement'); // le dossier d'un projet ne suit plus l'arbre : ni monter ni déplacer
  if (!n.deplacable && !n.montable && !projet) return null;
  const b = (act, glyphe, titre) => h('button', { type: 'button', class: 'act-ligne', 'data-act': act, tabindex: '-1', title: titre, 'aria-label': `${titre.split(' — ')[0]} : ${n.titre}` }, glyphe);
  return h('span', { class: 'actions-ligne' },
    n.montable && !fixe ? b('monter', '↰', t('glisser.monter')) : null,
    n.deplacable && !fixe ? b('vers', '↳', t('glisser.vers')) : null,
    projet && ouvert('transformations') ? b('reduire', '⊟', t('glisser.reduire')) : null,
    projet ? b('routine', '⏰', t('glisser.routine')) : null,
    projet ? b('chaine', '⛓', t('glisser.chaine')) : null);
}

// Branche glisser-déposer, boutons et raccourcis sur un conteneur de lignes [data-cle].
// `defile` : élément qui défile ; `haut` : hauteur d'un en-tête collant à ignorer pour le défilement automatique.
export function brancher(cont, defile, haut = 0) {
  let glisse = null, cleSurvol = null, minuteur = 0;
  const ligneDe = (x) => x.closest?.('[data-cle]');
  const effacer = () => {
    clearTimeout(minuteur); cleSurvol = null;
    cont.querySelectorAll('.cible-ok, .cible-ko').forEach((x) => x.classList.remove('cible-ok', 'cible-ko'));
  };
  const fin = () => { effacer(); cont.querySelectorAll('.glisse').forEach((x) => x.classList.remove('glisse')); glisse = null; };
  const defiler = (e) => {
    const r = defile.getBoundingClientRect(), zoneH = 40, haute = r.top + haut;
    if (e.clientY < haute + zoneH) defile.scrollTop -= Math.ceil((haute + zoneH - e.clientY) / zoneH * 18);
    else if (e.clientY > r.bottom - zoneH) defile.scrollTop += Math.ceil((e.clientY - (r.bottom - zoneH)) / zoneH * 18);
  };
  cont.addEventListener('dragstart', (e) => {
    const row = ligneDe(e.target), en = row && indexer().get(row.dataset.cle);
    if (!en || !en.n.deplacable) { e.preventDefault(); return; }
    glisse = { n: en.n, idx: indexer() };
    e.dataTransfer.setData('text/plain', en.n.id);
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => row.classList.add('glisse'), 0); // après la capture de l'image de glisse
  });
  cont.addEventListener('dragover', (e) => {
    if (!glisse) return;
    defiler(e);
    const row = ligneDe(e.target);
    if (row?.dataset.cle !== cleSurvol) {
      effacer(); cleSurvol = row?.dataset.cle ?? null;
      // Un groupe replié se déplie après ~700 ms de survol.
      if (row?.getAttribute('aria-expanded') === 'false') minuteur = setTimeout(() => emit('deplier', cleSurvol), 700);
    }
    if (!row) return;
    const en = glisse.idx.get(row.dataset.cle), ok = !!en && admis(glisse.n, en.n, glisse.idx);
    row.classList.remove('cible-ok', 'cible-ko');
    row.classList.add(ok ? 'cible-ok' : 'cible-ko');
    e.dataTransfer.dropEffect = ok ? 'move' : 'none';
    if (ok) e.preventDefault(); // sans preventDefault le navigateur affiche le curseur interdit
  });
  cont.addEventListener('dragleave', (e) => { if (!cont.contains(e.relatedTarget)) effacer(); });
  cont.addEventListener('drop', (e) => {
    if (!glisse) return;
    const g = glisse, row = ligneDe(e.target), en = row && g.idx.get(row.dataset.cle);
    fin();
    if (!en || !admis(g.n, en.n, g.idx)) return;
    e.preventDefault();
    if (g.n.type === 'tache' && en.n.type === 'tache') menuDepot(e.clientX, e.clientY, g.n, en.n);
    else deplacer(g.n, en.n, g.idx, cont);
  });
  cont.addEventListener('dragend', fin);

  // INV-ARBRE-3 : un projet neuf (vide) est absent de S.arbre ; son bouton agit quand même, sur l'id lu dans la clé de la ligne.
  const neuf = (k) => {
    const [type, ...id] = k.split(':');
    const titre = cont.querySelector(`[data-cle="${CSS.escape(k)}"] .titre`)?.textContent;
    return type === 'conteneur' && titre ? { n: { type, id: id.join(':'), titre } } : null;
  };
  const agir = (act, k) => {
    const idx = indexer(), en = idx.get(k) ?? neuf(k);
    if (!en) return;
    if (act === 'routine' && en.n.type === 'conteneur') { nouvelleRoutine(en.n.id); return; }
    if (act === 'chaine' && en.n.type === 'conteneur') { lancerChaine(en.n.id); return; }
    if (en.n.type !== 'tache' && !ouvert('alignement') && act !== 'reduire') return;
    if (act === 'monter' && en.n.montable) monter(en.n, idx, cont);
    else if (act === 'vers' && en.n.deplacable) dialogueVers(en.n, idx, cont);
    else if (act === 'reduire' && en.n.type === 'conteneur' && ouvert('transformations')) reduire(en.n);
  };
  // Capture : les boutons et raccourcis passent avant le clic de ligne et la navigation fléchée du module.
  cont.addEventListener('click', (e) => {
    const b = e.target.closest?.('.act-ligne');
    if (!b) return;
    e.stopPropagation(); e.preventDefault();
    agir(b.dataset.act, ligneDe(b)?.dataset.cle);
  }, true);
  cont.addEventListener('keydown', (e) => {
    const row = document.activeElement;
    if (!row?.matches?.('[data-cle]') || !cont.contains(row) || e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.shiftKey && e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); agir('monter', row.dataset.cle); }
    else if (!e.shiftKey && e.key === 'm') { e.preventDefault(); e.stopPropagation(); agir('vers', row.dataset.cle); }
  }, true);
}
