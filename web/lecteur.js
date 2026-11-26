// Rôle : lecteur de fichiers intégré (INV-LECTEUR-1) — un clic sur un lien vers un fichier ouvre, pour les formats lisibles, un volet
// de lecture (Markdown rendu, texte, tableaux, données indentées, HTML/SVG/images/PDF en cadre isolé) ; les autres formats sont confiés
// par le serveur à l'application du poste. Adresse partageable `#f=<chemin>` ; Échap ferme ; plein écran ; feuille au téléphone.
// Frontières : API /lecteur seule ; le serveur décide du mode, des racines autorisées et de l'isolement ; aucun HTML de fichier n'est
// jamais injecté ici (le Markdown passe par md.js, qui échappe tout ; le HTML vit dans un <iframe sandbox> sans script).
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { md } from './md.js';
import { t } from './langues.js';

const enc = encodeURIComponent;
const brut = (chemin, externe) => `/api/lecteur/brut?chemin=${enc(chemin)}${externe ? '&externe=true' : ''}`;
const lang = () => document.documentElement.lang || undefined;
const taille = (o) => {
  const [v, unite] = o >= 1048576 ? [o / 1048576, 'megabyte'] : o >= 1024 ? [o / 1024, 'kilobyte'] : [o, 'byte'];
  return new Intl.NumberFormat(lang(), { style: 'unit', unit: unite, unitDisplay: 'short', maximumFractionDigits: 1 }).format(v);
};
let ouvert = null, avant = '';

/** Clic sur un lien de fichier : le serveur dit « lecteur » ou « application » ; rien n'est deviné ici. */
export async function ouvrirFichier(chemin) {
  let i;
  try { i = await api(`/lecteur/info?chemin=${enc(chemin)}`); } catch { return false; } // hors racines ou absent : l'appelant a son repli
  if (i.mode === 'application') await ouvrirApplication(i);
  else await volet(i);
  return true;
}

async function ouvrirApplication(i) {
  if (!i.application) { erreur(t('lecteur.poste_seul'), 'info'); return; }
  try { erreur((await post('/lecteur/ouvrir', { chemin: i.chemin })).message, 'info'); } catch (e) { erreur(e.message); }
}

// --- formats ---
export function lignesCsv(texte) {
  const sep = texte.split('\n', 1)[0].split('\t').length > texte.split('\n', 1)[0].split(',').length ? '\t' : texte.split('\n', 1)[0].split(';').length > texte.split('\n', 1)[0].split(',').length ? ';' : ',';
  const rows = [];
  let ligne = [], cur = '', guil = false;
  for (let k = 0; k < texte.length; k++) {
    const c = texte[k];
    if (guil) { if (c === '"') { if (texte[k + 1] === '"') { cur += '"'; k++; } else guil = false; } else cur += c; }
    else if (c === '"') guil = true;
    else if (c === sep) { ligne.push(cur); cur = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && texte[k + 1] === '\n') k++; ligne.push(cur); rows.push(ligne); ligne = []; cur = ''; }
    else cur += c;
  }
  if (cur || ligne.length) { ligne.push(cur); rows.push(ligne); }
  return rows;
}
const tableauCsv = (rows, avecTete = true) => h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl-note' },
  avecTete && rows.length ? h('thead', null, h('tr', null, rows[0].map((c) => h('th', null, c)))) : null,
  h('tbody', null, rows.slice(avecTete ? 1 : 0).map((r) => h('tr', null, r.map((c) => h('td', null, c)))))));

function indenterXml(x) {
  let niveau = 0;
  return x.replace(/>\s*</g, '><').replace(/<[^>]+>|[^<]+/g, (m) => {
    if (m.startsWith('</')) niveau = Math.max(0, niveau - 1);
    const sortie = '  '.repeat(niveau) + m + '\n';
    if (/^<[^!?/][^>]*[^/]>$/.test(m) && !m.startsWith('</')) niveau++;
    return sortie;
  }).trim();
}
export function mettreEnForme(ext, texte) {
  try {
    if (ext === 'json') return JSON.stringify(JSON.parse(texte), null, 2);
    if (ext === 'xml') return indenterXml(texte);
  } catch { /* illisible : tel quel */ }
  return texte;
}

// Frontmatter replié : `---` … `---` en tête du fichier.
export function separerFrontmatter(texte) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(texte);
  return m ? { tete: m[1], corps: texte.slice(m[0].length) } : { tete: '', corps: texte };
}

// --- volet ---
async function volet(i) {
  fermer();
  const dlg = h('dialog', { class: 'lecteur', 'data-id': 'lecteur', 'aria-label': t('lecteur.titre', { nom: i.nom }) });
  const corps = h('div', { class: 'lec-corps', 'data-id': 'lecteur-corps', 'data-genre': i.genre });
  const bouton = (cle, f, attrs = {}) => h('button', { class: 'btn petit', type: 'button', onclick: f, ...attrs }, t(cle));
  const etat = { source: false, pleine: false };
  let rendre = () => {};
  const bSource = i.genre === 'md' ? bouton('lecteur.voir_source', () => { etat.source = !etat.source; bSource.textContent = t(etat.source ? 'lecteur.voir_rendu' : 'lecteur.voir_source'); rendre(); }, { 'data-id': 'lecteur-source' }) : null;
  const bPlein = bouton('lecteur.plein_ecran', () => { etat.pleine = !etat.pleine; dlg.classList.toggle('plein', etat.pleine); bPlein.setAttribute('aria-pressed', String(etat.pleine)); }, { 'data-id': 'lecteur-plein', 'aria-pressed': 'false' });
  const tete = h('header', { class: 'lec-tete' },
    h('div', { class: 'lec-id' }, h('b', { class: 'lec-nom' }, i.nom),
      h('span', { class: 'lec-meta', title: i.chemin }, `${i.chemin} · ${taille(i.taille)} · ${new Date(i.date).toLocaleString(lang(), { dateStyle: 'medium', timeStyle: 'short' })}`)),
    h('div', { class: 'lec-actions' },
      i.application ? bouton('lecteur.ouvrir_application', () => ouvrirApplication(i), { 'data-id': 'lecteur-appli' }) : null,
      i.application ? bouton('lecteur.afficher_dossier', async () => { try { erreur((await post('/lecteur/dossier', { chemin: i.chemin })).message, 'info'); } catch (e) { erreur(e.message); } }) : null,
      bouton('lecteur.copier_chemin', async () => { try { await navigator.clipboard.writeText(i.chemin); erreur(t('lecteur.chemin_copie'), 'info'); } catch { erreur(i.chemin, 'info'); } }),
      bSource, bPlein,
      h('button', { class: 'btn petit lec-fermer', type: 'button', 'aria-label': t('lecteur.fermer'), title: t('lecteur.fermer'), onclick: fermer }, '×')));
  dlg.append(tete, corps);
  dlg.addEventListener('click', (e) => { if (e.target === dlg || e.target.closest('a.wl')) fermer(); }); // fond ou lien interne : on referme
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); fermer(); }); // Échap
  document.body.append(dlg);
  avant = location.hash;
  history.replaceState(null, '', `#f=${enc(i.chemin)}`);
  ouvert = dlg;
  dlg.showModal();
  if (['html', 'image', 'pdf'].includes(i.genre)) corps.append(...cadre(i));
  else rendre = await texte(i, corps, etat);
}

function cadre(i) {
  if (i.genre === 'image') return [h('img', { class: 'lec-image', src: brut(i.chemin), alt: i.nom })];
  const f = h('iframe', { class: 'lec-cadre', title: i.nom, src: brut(i.chemin), 'data-id': 'lecteur-cadre' });
  if (i.genre === 'html') f.setAttribute('sandbox', ''); // INV-LECTEUR-1 : ni script, ni formulaire, ni origine de GoldenBrain
  if (i.genre === 'pdf') return [f];
  const ext = h('input', { type: 'checkbox', 'data-id': 'lecteur-externe', onchange: () => { f.src = brut(i.chemin, ext.checked); } });
  return [h('label', { class: 'case lec-externe' }, ext, ' ', t('lecteur.externe')), f];
}

async function texte(i, corps, etat) {
  let tout = '', suite = true, debut = 0, occupe = false;
  const zone = h('div', { class: 'lec-texte' });
  const bSuite = h('button', { class: 'btn', type: 'button', 'data-id': 'lecteur-suite', hidden: true, onclick: () => page() }, t('lecteur.charger_suite'));
  corps.append(zone, bSuite);
  const dessiner = () => {
    const { tete, corps: c } = i.genre === 'md' && !etat.source ? separerFrontmatter(tout) : { tete: '', corps: tout };
    if (i.genre === 'md' && !etat.source) {
      const el = h('div', { class: 'note-corps lec-md' });
      el.innerHTML = md(c, { depuis: i.vault ? i.vault.split('/').slice(0, -1).join('/') : undefined }); // md() échappe tout (INV-WEB-1)
      remplacer(zone, tete ? h('details', { class: 'lec-front' }, h('summary', null, t('lecteur.frontmatter')), h('pre', null, tete)) : null, el);
    } else if (i.genre === 'csv') remplacer(zone, tableauCsv(lignesCsv(tout)));
    else remplacer(zone, h('pre', { class: 'lec-pre' }, suite ? tout : mettreEnForme(i.ext, tout)));
    bSuite.hidden = !suite;
  };
  async function page() {
    if (occupe) return;
    occupe = true;
    try {
      const r = await api(`/lecteur/page?chemin=${enc(i.chemin)}&debut=${debut}`);
      tout += r.texte; debut = r.fin; suite = r.suite;
      dessiner();
    } catch (e) { erreur(e.message); } finally { occupe = false; }
  }
  await page();
  return dessiner;
}

export function fermer() {
  if (!ouvert) return;
  const d = ouvert;
  ouvert = null;
  if (d.open) d.close();
  d.remove();
  if (location.hash.startsWith('#f=')) history.replaceState(null, '', avant || location.pathname + location.search);
}

/** Adresse d'arrivée `#f=…` (lien partagé) et saisie d'une telle adresse. */
export function initLecteur() {
  const depuisUrl = () => { const m = /^#f=(.+)$/.exec(location.hash); if (m) { let c = m[1]; try { c = decodeURIComponent(c); } catch { /* tel quel */ } ouvrirFichier(c); } else fermer(); };
  window.addEventListener('hashchange', depuisUrl);
  if (location.hash.startsWith('#f=')) depuisUrl();
}
