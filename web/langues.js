// Rôle : traduction de l'interface (INV-LANGUE-1) — choix de la langue, chargement de son seul dictionnaire, t().
// Frontières : lit GET /api/interface (langue réglée) et web/langues/<code>.json ; mémorise la langue détectée au premier
//        lancement par PUT /api/interface. Aucun rendu propre ; `traduireDom` pose les textes du HTML statique (data-t*).
// Chargé par `await` au premier import : tout module qui l'importe peut appeler t() dès son évaluation (constantes de libellés).
// Changer de langue recharge la page : chaque libellé, même calculé une fois, repart du bon dictionnaire.
export const LANGUES = { fr: 'Français', en: 'English', de: 'Deutsch', es: 'Español' };
const LOCALES = { fr: 'fr-FR', en: 'en-GB', de: 'de-DE', es: 'es-ES' };

// Première langue du navigateur que l'on sait parler, sinon l'anglais (le plus compris), sauf navigateur francophone.
export function detecter(prefs = globalThis.navigator?.languages || [globalThis.navigator?.language || '']) {
  for (const p of prefs) { const c = String(p || '').slice(0, 2).toLowerCase(); if (LANGUES[c]) return c; }
  return 'en';
}

async function lireJson(url, opts) {
  try { const r = await fetch(url, opts); return r.ok ? await r.json() : null; } catch { return null; }
}

async function charger() {
  const etat = await lireJson('/api/interface');
  let langue = etat?.langue;
  if (!LANGUES[langue]) {
    langue = detecter();
    // Premier lancement : la langue détectée devient le réglage (config.toml, [interface] langue).
    if (etat) lireJson('/api/interface', { method: 'PUT', headers: { 'X-Orchestrateur': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ langue }) });
  }
  const dict = (await lireJson(`/langues/${langue}.json`)) || (langue === 'fr' ? {} : await lireJson('/langues/fr.json')) || {};
  return { langue, dict, etat };
}

const { langue, dict, etat: etatInitial } = await charger();
let initial = etatInitial; // réglages lus pour choisir la langue : interface.js les adopte sans relire la route
export const etatInterfaceInitial = () => { const e = initial; initial = null; return e; };
export const LANGUE = langue;
export const LOCALE = LOCALES[langue];
document.documentElement.lang = langue;

// t('cle', { nom: valeur }) : texte de la clé dans la langue réglée, `{nom}` remplacés. Clé absente : la clé elle-même
// (la porte garantit qu'elle ne l'est jamais).
export function t(cle, params) {
  const s = dict[cle] ?? cle;
  return params ? s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : s;
}
// Accord simple au nombre : clé `<cle>.un` pour 1 (et 0 en français), `<cle>.plusieurs` sinon ; `{n}` disponible.
export function tn(cle, n, params) {
  const un = n === 1 || (n === 0 && (langue === 'fr'));
  return t(`${cle}.${un ? 'un' : 'plusieurs'}`, { n, ...params });
}

// HTML statique : data-t (texte), data-t-title, data-t-placeholder, data-t-aria-label, data-t-alt.
const ATTRIBUTS = ['title', 'placeholder', 'aria-label', 'alt'];
export function traduireDom(racine = document) {
  for (const el of racine.querySelectorAll('[data-t]')) el.textContent = t(el.dataset.t);
  for (const a of ATTRIBUTS) {
    for (const el of racine.querySelectorAll(`[data-t-${a}]`)) el.setAttribute(a, t(el.getAttribute(`data-t-${a}`)));
  }
}

export async function changerLangue(code) {
  if (!LANGUES[code] || code === langue) return;
  const r = await fetch('/api/interface', { method: 'PUT', headers: { 'X-Orchestrateur': '1', 'Content-Type': 'application/json' },
    body: JSON.stringify({ langue: code }) });
  if (!r.ok) throw new Error(t('langue.echec'));
  location.reload();
}
