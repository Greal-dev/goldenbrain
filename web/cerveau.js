// Rôle : « Configurer votre second cerveau » — premier écran de tout premier lancement, plein écran : choisir le dossier du vault
// (un dossier Markdown/Obsidian existant, repris en place sans copie, ou un dossier neuf), sans jamais éditer config.toml ; puis
// passe la main aux premiers pas (assistant IA) et à l'accueil (rôles, projets, classement). Rouvert par Réglages ; « Plus tard »
// laisse un rappel visible.
// Frontières : GET/POST /api/accueil/cerveau{,/examiner,/dossiers,/appliquer,/plus-tard} (poste seulement, INV-ACCUEIL-1) ; rien
// n'est écrit avant « Continuer » (INV-CERVEAU-2). INV-WEB-1 : aucun HTML injecté, tout passe par h().
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { t, tn } from './langues.js';
import { attendreRetour } from './version.js';

let E = null; // { chemin, examen, nav, occupe, suite, maison }
let boite = null;
let minuteur = null;

/** Premier lancement : ouvre le parcours s'il est proposé, sinon montre le rappel éventuel, puis passe la main à `apres`. */
export async function initCerveau(apres) {
  let d = null;
  try { d = await api('/accueil/cerveau'); } catch { /* serveur distant ou injoignable : pas de parcours */ }
  if (d?.propose) { ouvrirCerveau(apres, d); return; }
  if (d?.rappel) rappel();
  apres?.();
}

export async function ouvrirCerveau(apres = null, d = null) {
  try { d = d || await api('/accueil/cerveau'); } catch (e) { erreur(e.message); return; }
  E = { chemin: d.vault || d.defaut || '', examen: null, nav: null, occupe: false, suite: apres, maison: d.maison };
  boite?.remove();
  boite = h('div', { class: 'accueil plein', role: 'dialog', 'aria-modal': 'true', 'aria-label': t('cerveau.titre'), 'data-id': 'cerveau' });
  document.body.append(boite);
  dessiner();
  examiner();
}

function rappel() {
  if (document.querySelector('[data-id="cerveau-rappel"]')) return;
  document.body.prepend(h('div', { class: 'cerveau-rappel', role: 'status', 'data-id': 'cerveau-rappel' }, h('span', null, t('cerveau.rappel')),
    h('button', { type: 'button', class: 'btn petit primaire', 'data-id': 'cerveau-configurer', onclick: () => { document.querySelector('[data-id="cerveau-rappel"]')?.remove(); ouvrirCerveau(null); } }, t('cerveau.configurer'))));
}

async function plusTard() {
  try { await post('/accueil/cerveau/plus-tard', {}); } catch { /* le parcours se reproposera au prochain passage */ }
  boite?.remove(); boite = null; E = null;
  rappel();
}

async function examiner() {
  const chemin = E.chemin.trim();
  clearTimeout(minuteur);
  if (!chemin) { E.examen = null; dessiner(); return; }
  try { E.examen = await post('/accueil/cerveau/examiner', { chemin }); } catch (e) { E.examen = { ok: false, erreur: e.message }; }
  dessiner();
}

async function parcourir(chemin) {
  try { E.nav = await post('/accueil/cerveau/dossiers', { chemin }); } catch (e) { erreur(e.message); return; }
  dessiner();
}

function navigateur() {
  const n = E.nav;
  const lien = (nom, chemin, id) => h('button', { class: 'btn petit', type: 'button', 'data-id': id, onclick: () => parcourir(chemin) }, nom);
  return h('div', { class: 'cv-nav', 'data-id': 'cerveau-nav' },
    h('div', { class: 'cv-chemin', 'data-id': 'cerveau-nav-chemin' }, n.chemin),
    h('div', { class: 'cv-barre' },
      n.parent ? lien(t('cerveau.dossier_parent'), n.parent, 'cerveau-parent') : null,
      lien(t('cerveau.dossier_perso'), n.maison, 'cerveau-maison'),
      n.racines.length > 1 || n.racines[0] !== '/' ? n.racines.map((r) => lien(r, r, `cerveau-racine-${r}`)) : null,
      h('button', { type: 'button', class: 'btn petit primaire', 'data-id': 'cerveau-ici', onclick: () => { E.chemin = n.chemin; E.nav = null; examiner(); } }, t('cerveau.choisir_ici'))),
    h('ul', { class: 'cv-liste' }, n.dossiers.length ? n.dossiers.map((d) => h('li', null, h('button', { class: 'btn petit', type: 'button', 'data-dossier': d.nom, onclick: () => parcourir(d.chemin) }, d.nom)))
      : h('li', { class: 'note' }, t('cerveau.aucun_sous_dossier'))),
    n.tronque ? h('p', { class: 'note' }, t('cerveau.tronque')) : null);
}

function verdict() {
  const x = E.examen;
  if (!x) return h('p', { class: 'note', 'data-id': 'cerveau-verdict' }, t('cerveau.saisir'));
  if (!x.ok) return h('p', { class: 'avertissement', role: 'alert', 'data-id': 'cerveau-verdict', 'data-etat': 'refus' }, x.erreur);
  const [cle, etat] = !x.existe ? ['cerveau.sera_cree', 'neuf'] : x.vide ? ['cerveau.vide', 'vide']
    : x.obsidian ? ['cerveau.obsidian', 'existant'] : ['cerveau.existant', 'existant'];
  return h('p', { class: 'note', 'data-id': 'cerveau-verdict', 'data-etat': etat }, x.vide ? t(cle) : tn(cle, x.notes), x.actuel ? ` ${t('cerveau.deja_actuel')}` : '');
}

function dessiner() {
  if (!boite || !E) return;
  const x = E.examen;
  remplacer(boite, h('div', { class: 'ac-carte' },
    h('h2', null, t('cerveau.titre')),
    h('ol', { class: 'ac-pas' }, [t('cerveau.pas_dossier'), t('cerveau.pas_assistant'), t('cerveau.pas_projets')].map((s, i) => h('li', { class: i === 0 ? 'en-cours' : null }, `${i + 1}. ${s}`))),
    h('p', null, t('cerveau.intro')),
    h('label', { class: 'ac-champ cv-champ' }, t('cerveau.dossier'),
      h('input', { type: 'text', 'data-id': 'cerveau-chemin', value: E.chemin, spellcheck: 'false', placeholder: t('cerveau.chemin_ph'),
        oninput: (e) => { E.chemin = e.target.value; clearTimeout(minuteur); minuteur = setTimeout(examiner, 350); } })),
    h('div', { class: 'ac-actions cv-bas' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'cerveau-parcourir', onclick: () => (E.nav ? (E.nav = null, dessiner()) : parcourir(E.chemin.trim() && x?.existe && x.dossier ? E.chemin.trim() : '')) }, t('cerveau.parcourir'))),
    E.nav ? navigateur() : null,
    verdict(),
    h('p', { class: 'note' }, t('cerveau.rien_ecrit')),
    h('div', { class: 'ac-actions' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'cerveau-plus-tard', onclick: plusTard }, t('cerveau.plus_tard')),
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'cerveau-continuer', disabled: x?.ok && !E.occupe ? null : true, onclick: appliquer }, t('cerveau.continuer')))));
}

async function appliquer(e) {
  e.target.disabled = true;
  const x = E.examen;
  let avant = '';
  try { avant = (await api('/etat')).version?.demarree || ''; } catch { /* sans repère : on attend le simple retour du serveur */ }
  let bilan;
  try { bilan = await post('/accueil/cerveau/appliquer', { chemin: E.chemin.trim(), creer: !x.existe }); } catch (err) { erreur(err.message); e.target.disabled = false; return; }
  if (!bilan.redemarrage) { const s = E.suite; boite?.remove(); boite = null; E = null; s ? s() : location.reload(); return; }
  // INV-CERVEAU-2 : le serveur repart sur le nouveau vault ; la page se recharge à son retour et le parcours continue (états rouverts).
  remplacer(boite, h('div', { class: 'ac-carte' }, h('h2', null, t('cerveau.titre')), h('p', { 'data-id': 'cerveau-redemarrage' }, t('cerveau.redemarrage'))));
  await attendreRetour(avant);
}

export const sectionCerveau = () => [h('p', { class: 'note' }, t('cerveau.reglage')),
  h('button', { class: 'btn', type: 'button', 'data-id': 'reconfigurer-cerveau', onclick: () => ouvrirCerveau(() => import('./premiers-pas.js').then((m) => m.initPremiersPas(() => import('./accueil.js').then((a) => a.initAccueil())))) }, t('cerveau.reconfigurer'))];
