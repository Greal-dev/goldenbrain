// Rôle : volet droit — vue graphe du second cerveau : graphe local (voisinage d'une note ou d'une tâche) et graphe global filtrable.
// Frontières : API GET /vault/graphe, /vault/graphe/facettes ; ouvre par store.js (tâche, note) ou notes.js (dossier). N'écrit rien.
// Sobriété (INV-GRAPHE-2) : canvas 2D natif, forces calculées seulement jusqu'à stabilisation ; au repos, aucune boucle :
// on ne redessine que sur geste (zoom, déplacement, survol, recherche).
import { h, remplacer } from './dom.js';
import { ouvrir, ouvrirGraphe, ouvrirNote } from './store.js';
import { api } from './api.js';
import { voirDossier } from './notes.js';
import { t, tn } from './langues.js';

const enc = encodeURIComponent;
// Jetons du thème (clair/sombre) ; la valeur de repli vaut tant que la feuille de style ne les définit pas.
const JETON = { note: ['--accent', '#1f55b3'], tache: ['--c-attente', '#d97706'], conteneur: ['--c-validee', '#2e8b57'],
  lien: ['--texte-2', '#586170'], alimente: ['--c-attente', '#d97706'], prerequis: ['--c-bloque', '#c62828'],
  voir_aussi: ['--c-agent', '#7a4fc7'], appartient: ['--c-validee', '#2e8b57'] };
const OPACITE = { lien: 0.45, alimente: 0.6, prerequis: 0.6, voir_aussi: 0.5, appartient: 0.25 };
const couleurs = () => {
  const st = getComputedStyle(document.documentElement);
  return Object.fromEntries(Object.entries(JETON).map(([g, [v, d]]) => [g, st.getPropertyValue(v).trim() || d]));
};
const sobre = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const GENRES = { note: t('graphe.genre_note'), tache: t('graphe.genre_tache'), conteneur: t('graphe.genre_conteneur') };
const sansAccent = (s) => String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
let G = null; // état de la vue courante
// Changement de thème (Réglages pose data-theme sur <html>, ou bascule de l'OS) : un seul redessin, aucun coût au repos.
const retheme = () => { if (G && !G.anime) dessiner(G); };
new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', retheme);

function filtresDe() {
  try { return JSON.parse(localStorage.getItem('orch.graphe.filtres') || '{}'); } catch { return {}; }
}

export async function dessinerGraphe(el, centre) {
  const filtres = filtresDe();
  const profondeur = Number(localStorage.getItem('orch.graphe.profondeur') || 1);
  G = { el, centre, filtres, profondeur, terme: '', vue: { x: 0, y: 0, k: 1 }, survol: -1, anime: false };
  const etat = G;
  remplacer(el, h('p', { class: 'vide' }, t('graphe.chargement')));
  try {
    const q = centre ? `centre=${enc(centre)}&profondeur=${profondeur}`
      : Object.entries(filtres).filter(([, v]) => v).map(([k, v]) => `${k}=${enc(v)}`).join('&');
    const [d, f] = await Promise.all([api(`/vault/graphe?${q}`), centre ? null : api('/vault/graphe/facettes')]);
    if (G !== etat) return;
    etat.d = d; etat.facettes = f;
    afficher(etat);
  } catch (e) { if (G === etat) remplacer(el, h('p', { class: 'vide' }, e.message)); }
}

function choix(nom, libelle, options, valeur, surChange) {
  const s = h('select', { 'aria-label': libelle, 'data-filtre': nom },
    h('option', { value: '' }, libelle), options.map(([v, lib]) => h('option', { value: v }, lib)));
  s.value = valeur || '';
  s.onchange = () => surChange(s.value);
  return s;
}

function barre(etat) {
  const { centre, d } = etat;
  const changer = (k, v) => { etat.filtres[k] = v; localStorage.setItem('orch.graphe.filtres', JSON.stringify(etat.filtres)); dessinerGraphe(etat.el, null); };
  const recherche = h('input', { type: 'search', class: 'g-recherche', placeholder: t('graphe.mettre_en_evidence'), 'aria-label': t('graphe.rechercher') });
  recherche.oninput = () => { etat.terme = sansAccent(recherche.value.trim()); dessiner(etat); };
  const compte = h('span', { class: 'g-compte', 'data-id': 'graphe-compte' },
    t('graphe.compte', { noeuds: d.tronque ? tn('graphe.noeuds_tronque', d.noeuds.length, { total: d.total }) : tn('graphe.noeuds', d.noeuds.length), liens: tn('graphe.liens', d.liens.length) }));
  if (centre) {
    const prof = choix('profondeur', t('graphe.profondeur'), [['1', t('graphe.voisins_directs')], ['2', t('graphe.voisins_2')]], String(etat.profondeur), (v) => {
      localStorage.setItem('orch.graphe.profondeur', v || '1'); dessinerGraphe(etat.el, centre);
    });
    return h('div', { class: 'g-barre' }, prof, recherche, compte, recentrer(etat),
      h('button', { class: 'btn petit', type: 'button', onclick: () => ouvrirGraphe(null) }, t('graphe.global')));
  }
  const f = etat.facettes || {};
  const jours = [['7', t('graphe.jours_7')], ['30', t('graphe.jours_30')], ['90', t('graphe.jours_90')], ['365', t('graphe.jours_365')]];
  return h('div', { class: 'g-barre' },
    choix('casquette', t('graphe.casquette'), (f.casquettes || []).map((c) => [c, c]), etat.filtres.casquette, (v) => changer('casquette', v)),
    choix('projet', t('graphe.projet'), (f.projets || []).map((p) => [p.id, p.titre || p.id]), etat.filtres.projet, (v) => changer('projet', v)),
    choix('genre', t('graphe.genre'), Object.entries(GENRES), etat.filtres.genre, (v) => changer('genre', v)),
    choix('type', t('graphe.type'), (f.types || []).map((x) => [x, x]), etat.filtres.type, (v) => changer('type', v)),
    choix('tag', t('graphe.tag'), (f.tags || []).map((x) => [x, `#${x}`]), etat.filtres.tag, (v) => changer('tag', v)),
    choix('jours', t('graphe.periode'), jours, etat.filtres.jours, (v) => changer('jours', v)),
    recherche, compte, recentrer(etat));
}

function legende() {
  return h('div', { class: 'g-legende', 'aria-hidden': 'true' },
    Object.entries(GENRES).map(([g, lib]) => h('span', null, h('i', { style: `background:var(${JETON[g][0]}, ${JETON[g][1]})`, class: `g-forme-${g}` }), lib)));
}

function afficher(etat) {
  const { d, centre } = etat;
  const titreCentre = centre ? (d.noeuds.find((n) => n.id === d.centre)?.titre || centre) : null;
  etat.canvas = h('canvas', { class: 'g-canvas', role: 'img', 'aria-label': centre ? t('graphe.aria_local', { titre: titreCentre }) : t('graphe.aria_global'), tabindex: '0' });
  const liste = h('details', { class: 'g-liste' }, h('summary', null, t('graphe.liste')),
    h('ul', null, d.noeuds.slice(0, 300).map((n) => h('li', null, h('button', { class: 'lien-titre', type: 'button', 'data-noeud': n.id, onclick: () => ouvrirNoeud(n) }, n.titre || n.id), h('span', { class: 'n-chemin' }, ` ${GENRES[n.genre]}`)))));
  remplacer(etat.el, h('div', { class: 'vue-graphe' },
    h('div', { class: 'd-tete' }, h('h2', { class: 'd-titre' }, centre ? t('graphe.titre_local', { titre: titreCentre }) : t('graphe.titre_global')), barre(etat), legende()),
    d.noeuds.length ? etat.canvas : h('p', { class: 'vide' }, centre ? t('graphe.noeud_introuvable') : t('graphe.aucun_noeud')), liste));
  if (!d.noeuds.length) return;
  initialiser(etat);
  gestes(etat);
  new ResizeObserver(() => { ajuster(etat); dessiner(etat); }).observe(etat.canvas);
  ajuster(etat);
  demarrerSimulation(etat);
}

function ajuster(etat) {
  const c = etat.canvas, r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  c.width = Math.max(1, Math.round(r.width * dpr)); c.height = Math.max(1, Math.round(r.height * dpr));
  etat.l = r.width; etat.ht = r.height; etat.dpr = dpr;
}

function initialiser(etat) {
  const n = etat.d.noeuds.length, rayon = 30 * Math.sqrt(n);
  etat.p = etat.d.noeuds.map((x, i) => {
    // Spirale déterministe : même graphe, même dessin d'une visite à l'autre.
    const a = i * 2.399963, r = rayon * Math.sqrt((i + 0.5) / n);
    return { x: x.id === etat.d.centre ? 0 : r * Math.cos(a), y: x.id === etat.d.centre ? 0 : r * Math.sin(a), vx: 0, vy: 0, fixe: x.id === etat.d.centre };
  });
  etat.voisins = etat.d.noeuds.map(() => []);
  for (const [a, b] of etat.d.liens) { etat.voisins[a].push(b); etat.voisins[b].push(a); }
  etat.vue.k = Math.min(1.5, 300 / (rayon + 40));
}

// Forces simples : répulsion entre toutes les paires, ressort sur chaque lien, rappel au centre.
// ponytail: répulsion en O(n²), ~10 ms par pas à 2 000 nœuds ; passer à une grille (Barnes-Hut) au-delà.
function pas(etat, alpha) {
  const p = etat.p, n = p.length;
  for (let i = 0; i < n; i++) {
    const a = p[i];
    for (let j = i + 1; j < n; j++) {
      const b = p[j]; let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
      if (d2 > 90000) continue; // au-delà de 300 px, la répulsion est négligeable
      if (d2 < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 1; }
      const f = (900 * alpha) / d2; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
  }
  for (const [i, j] of etat.d.liens) {
    const a = p[i], b = p[j], dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
    const f = ((d - 60) / d) * 0.05 * alpha; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
  }
  let mouvement = 0;
  for (const a of p) {
    a.vx -= a.x * 0.002 * alpha; a.vy -= a.y * 0.002 * alpha;
    if (a.fixe) { a.vx = a.vy = 0; continue; }
    a.vx *= 0.6; a.vy *= 0.6; a.x += a.vx; a.y += a.vy; mouvement += Math.abs(a.vx) + Math.abs(a.vy);
  }
  return mouvement / n;
}

// A14 : cadre l'ensemble des nœuds dans la zone visible ; suit la simulation tant que l'utilisateur n'a rien déplacé.
function cadrer(etat) {
  const p = etat.p; if (!p.length || !etat.l) return;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const a of p) { x0 = Math.min(x0, a.x); x1 = Math.max(x1, a.x); y0 = Math.min(y0, a.y); y1 = Math.max(y1, a.y); }
  const marge = 40, w = Math.max(1, x1 - x0), ht = Math.max(1, y1 - y0);
  etat.vue.k = Math.min(1.5, (etat.l - 2 * marge) / w, (etat.ht - 2 * marge) / ht);
  etat.vue.x = -(x0 + x1) / 2; etat.vue.y = -(y0 + y1) / 2;
}
const recentrer = (etat) => h('button', { class: 'btn petit', type: 'button', 'data-id': 'graphe-recentrer', onclick: () => { etat.manuel = false; cadrer(etat); dessiner(etat); } }, t('graphe.recentrer'));

function demarrerSimulation(etat) {
  let alpha = 1, tours = 0;
  etat.anime = true;
  const fixe = sobre(); // mouvement réduit : on calcule sans montrer, un seul dessin à la stabilisation
  const boucle = () => {
    if (G !== etat || !etat.canvas.isConnected) { etat.anime = false; return; }
    const m = pas(etat, alpha); alpha *= 0.985; tours++;
    if (!etat.manuel) cadrer(etat);
    if (!fixe) dessiner(etat);
    // Arrêt dès stabilisation (mouvement moyen < 0,05 px) ou au plus 400 pas : plus aucun calcul ensuite.
    if ((m < 0.05 && tours > 30) || tours > 400) { etat.anime = false; if (fixe) dessiner(etat); etat.canvas.dataset.stable = '1'; return; }
    requestAnimationFrame(boucle);
  };
  requestAnimationFrame(boucle);
}

const versEcran = (etat, q) => ({ x: etat.l / 2 + (q.x + etat.vue.x) * etat.vue.k, y: etat.ht / 2 + (q.y + etat.vue.y) * etat.vue.k });

function correspond(etat, i) {
  return !etat.terme || sansAccent(etat.d.noeuds[i].titre).includes(etat.terme) || sansAccent(etat.d.noeuds[i].id).includes(etat.terme);
}

function forme(ctx, genre, x, y, r) {
  ctx.beginPath();
  if (genre === 'conteneur') ctx.rect(x - r, y - r, 2 * r, 2 * r);
  else if (genre === 'tache') { ctx.moveTo(x, y - r * 1.2); ctx.lineTo(x + r * 1.2, y); ctx.lineTo(x, y + r * 1.2); ctx.lineTo(x - r * 1.2, y); ctx.closePath(); }
  else ctx.arc(x, y, r, 0, 2 * Math.PI);
}

function dessiner(etat) {
  if (!etat.p || !etat.canvas?.isConnected) return;
  const ctx = etat.canvas.getContext('2d'), { d, p } = etat;
  const proches = new Set(etat.survol >= 0 ? [etat.survol, ...etat.voisins[etat.survol]] : []);
  const texte = getComputedStyle(etat.canvas).color, COULEUR = couleurs();
  ctx.setTransform(etat.dpr, 0, 0, etat.dpr, 0, 0);
  ctx.clearRect(0, 0, etat.l, etat.ht);
  ctx.lineWidth = 1;
  for (const [a, b, g] of d.liens) {
    const A = versEcran(etat, p[a]), B = versEcran(etat, p[b]);
    const cl = OPACITE[g] ? g : 'lien';
    ctx.globalAlpha = (etat.survol >= 0 && !(proches.has(a) && proches.has(b)) ? 0.15 : 1) * OPACITE[cl];
    ctx.strokeStyle = COULEUR[cl];
    ctx.beginPath(); ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y); ctx.stroke();
  }
  ctx.font = '12px system-ui, sans-serif';
  const etiquettes = d.noeuds.length <= 80 || etat.vue.k >= 1.2;
  d.noeuds.forEach((n, i) => {
    const q = versEcran(etat, p[i]), r = Math.min(10, 3 + Math.sqrt(n.degre || 0)) * Math.max(0.6, Math.min(etat.vue.k, 2));
    const vu = correspond(etat, i) && (etat.survol < 0 || proches.has(i));
    ctx.globalAlpha = vu ? 1 : 0.2;
    ctx.fillStyle = COULEUR[n.genre] || COULEUR.note;
    forme(ctx, n.genre, q.x, q.y, r); ctx.fill();
    if (n.id === d.centre || (etat.terme && correspond(etat, i))) { ctx.strokeStyle = texte; ctx.lineWidth = 2; ctx.stroke(); ctx.lineWidth = 1; }
    if (etiquettes || i === etat.survol || n.id === d.centre || (etat.terme && correspond(etat, i))) {
      ctx.fillStyle = texte; ctx.fillText(n.titre.length > 40 ? `${n.titre.slice(0, 39)}…` : n.titre, q.x + r + 3, q.y + 4);
    }
  });
  ctx.globalAlpha = 1;
}

function sous(etat, x, y) {
  let meilleur = -1, best = 144; // 12 px de rayon de saisie
  etat.p.forEach((q, i) => { const e = versEcran(etat, q), dd = (e.x - x) ** 2 + (e.y - y) ** 2; if (dd < best) { best = dd; meilleur = i; } });
  return meilleur;
}

function ouvrirNoeud(n) {
  if (n.tache) ouvrir(n.tache);
  else if (n.id.endsWith('/')) voirDossier(n.id.slice(0, -1));
  else ouvrirNote(n.id);
}

function gestes(etat) {
  const c = etat.canvas;
  let glisse = null;
  const local = (e) => { const r = c.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  c.addEventListener('wheel', (e) => {
    e.preventDefault();
    etat.manuel = true;
    etat.vue.k = Math.min(6, Math.max(0.05, etat.vue.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    dessiner(etat);
  }, { passive: false });
  c.addEventListener('pointerdown', (e) => { glisse = { ...local(e), vx: etat.vue.x, vy: etat.vue.y, bouge: false }; });
  c.addEventListener('pointermove', (e) => {
    const m = local(e);
    if (glisse) {
      const dx = m.x - glisse.x, dy = m.y - glisse.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) { glisse.bouge = true; etat.manuel = true; }
      etat.vue.x = glisse.vx + dx / etat.vue.k; etat.vue.y = glisse.vy + dy / etat.vue.k;
      if (!etat.anime) dessiner(etat);
      return;
    }
    const i = sous(etat, m.x, m.y);
    if (i !== etat.survol) {
      etat.survol = i; c.style.cursor = i >= 0 ? 'pointer' : '';
      c.title = i >= 0 ? `${etat.d.noeuds[i].titre} — ${GENRES[etat.d.noeuds[i].genre]}` : '';
      if (!etat.anime) dessiner(etat);
    }
  });
  c.addEventListener('pointerup', (e) => {
    const g = glisse; glisse = null;
    if (!g || g.bouge) return;
    const m = local(e), i = sous(etat, m.x, m.y);
    if (i >= 0) ouvrirNoeud(etat.d.noeuds[i]);
  });
  c.addEventListener('pointerleave', () => { glisse = null; if (etat.survol >= 0) { etat.survol = -1; if (!etat.anime) dessiner(etat); } });
  // Pour les scénarios d'interface : position à l'écran d'un nœud (le canvas n'a pas de DOM par nœud).
  c.horsCadre = () => etat.p.filter((_, i) => { const q = versEcran(etat, etat.p[i]); return q.x < 0 || q.y < 0 || q.x > etat.l || q.y > etat.ht; }).length;
  c.positionNoeud = (id) => { const i = etat.d.noeuds.findIndex((n) => n.id === id); return i < 0 ? null : versEcran(etat, etat.p[i]); };
}

