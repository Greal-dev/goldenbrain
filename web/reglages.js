// Rôle : page « Réglages » du volet droit — réglages regroupés par intention en sections repliables (<details>), chacune
//        titrée d'un résumé d'une ligne de son état ; ancre #reglages/<section> qui l'ouvre ; champ de recherche qui ouvre
//        la section concernée. Bascule Simple / Avancé, un interrupteur par famille, politique des propositions.
// Frontières : lit S.interface, écrit par PUT /api/interface (interface.js) ; le serveur reste maître des valeurs effectives.
//        Les sections spécialisées (simultanes.js, economie.js…) gardent leurs données et annoncent leur résumé par
//        l'événement 'resume' ; cette page ne connaît que leur titre, leur phrase d'aide et leur groupe.
// Visible dans les deux modes : sans elle, un mode simple ne laisserait aucun moyen d'en sortir.
// INV-REGLAGES-1 : un événement 'etat' ne redessine que les parties qui en dépendent (moteurs, version, résumés) ;
//        la page entière ne se reconstruit qu'à l'ouverture ou au changement de mode, et garde alors sections ouvertes,
//        recherche, champ en cours de saisie et focus.
import { sectionRangement } from './lignes.js';
import { h, remplacer } from './dom.js';
import { S, on, erreur } from './store.js';
import { FAMILLES, changerInterface, simple, ouvert } from './interface.js';
import { sectionSimultanes } from './simultanes.js';
import { sectionMiseAJour } from './maj-auto.js';
import { sectionEconomie } from './economie.js';
import { sectionCompactage } from './compactage.js';
import { sectionApprendre } from './apprendre.js';
import { sectionIntegration } from './integration.js';
import { sectionEvitable } from './evitable.js';
import { sectionExecuteurs } from './executeurs.js';
import { sectionInstallation } from './installation.js';
import { sectionAppareils } from './appareils.js';
import { sectionTelegram } from './telegram.js';
import { boutonAide } from './guide.js';
import { t, tn } from './langues.js';
import { sectionEtoile } from './etoile.js';
import { sectionAccueil, choixLangue } from './accueil.js';
import { sectionPremiersPas, titreSectionPremiersPas } from './premiers-pas.js';
import { sectionSignaler } from './signaler.js';
import { sectionReflexes } from './reflexes.js';

const PHRASES = {
  equipe: [t('reglages.famille_equipe_nom'), t('reglages.famille_equipe_phrase')],
  liens: [t('reglages.famille_liens_nom'), t('reglages.famille_liens_phrase')],
  alignement: [t('reglages.famille_alignement_nom'), t('reglages.famille_alignement_phrase')],
  jardinage: [t('reglages.famille_jardinage_nom'), t('reglages.famille_jardinage_phrase')],
  moteurs: [t('reglages.famille_moteurs_nom'), t('reglages.famille_moteurs_phrase')],
  notes: [t('reglages.famille_notes_nom'), t('reglages.famille_notes_phrase')],
  transformations: [t('reglages.famille_transformations_nom'), t('reglages.famille_transformations_phrase')],
  conseil: [t('reglages.famille_conseil_nom'), t('reglages.famille_conseil_phrase')],
};
const POLITIQUES = [
  ['montrer', t('reglages.politique_montrer')],
  ['accepter', t('reglages.politique_accepter')],
  ['ignorer', t('reglages.politique_ignorer')],
];
const THEMES = [['systeme', t('reglages.theme_systeme')], ['clair', t('reglages.theme_clair')], ['sombre', t('reglages.theme_sombre')]];

// Résumés annoncés par les sections spécialisées (événement 'resume' : [clé, texte]) ; conservés d'un dessin à l'autre.
const RESUMES = {};
const theme = () => document.documentElement.dataset.theme || 'systeme';
const agir = async (corps) => { try { await changerInterface(corps); } catch (e) { erreur(e.message); } };
const parts = (...cles) => cles.map((c) => RESUMES[c]).filter(Boolean).join(' · ');

function versionTexte() {
  const v = S.etat?.version;
  return !v ? '' : v.a_jour === false ? t('reglages.version_recente') : t('reglages.version_ajour');
}

// Groupes par intention : id (ancre), titre, phrase d'aide, résumé, sous-sections [ancre, titre, aide, contenu].
// Une sous-section sans titre porte le sien (Telegram).
const GROUPES = [
  { id: 'affichage', titre: t('reglages.affichage'), aide: t('reglages.affichage_aide'),
    resume: () => `${simple() ? t('reglages.mode_simple') : t('reglages.mode_avance')} · ${{ systeme: t('reglages.resume_theme_systeme'), clair: t('reglages.resume_theme_clair'), sombre: t('reglages.resume_theme_sombre') }[theme()]}`,
    sous: () => [
      ['mode', t('reglages.niveau'), t('reglages.niveau_aide'), blocMode()],
      ['langue', t('langue.titre'), t('langue.aide'), choixLangue()],
      ['theme', t('reglages.theme'), t('reglages.theme_aide'), blocTheme()],
      ['etoile', null, null, sectionEtoile()]] },
  { id: 'fonctions', titre: t('reglages.fonctions'), aide: t('reglages.fonctions_aide'),
    resume: () => t('reglages.resume_fonctions', { n: FAMILLES.filter(ouvert).length, total: FAMILLES.length }),
    sous: () => [['familles', null, null, h('ul', { class: 'rg-liste' }, FAMILLES.map(interrupteur))]] },
  { id: 'agents', titre: t('reglages.agents'), aide: t('reglages.agents_aide'),
    resume: () => parts('simultanes', 'economie', 'compactage', 'apprendre', 'reflexes'),
    sous: () => [
      ['simultanes', t('reglages.simultanes'), t('reglages.simultanes_aide'), sectionSimultanes()[1]],
      ['economie', t('reglages.economie'), t('reglages.economie_aide'), sectionEconomie()[1]],
      ['compactage', t('reglages.compactage'), t('reglages.compactage_aide'), sectionCompactage()[1]],
      ['apprendre', t('apprendre.titre'), null, sectionApprendre()[1]],
      ['reflexes', t('reflexes.titre'), t('reflexes.aide'), sectionReflexes()],
      ['rangement', t('lignes.rangement'), t('lignes.rangement_aide'), sectionRangement()],
      ['moteurs', t('reglages.moteurs'), t('reglages.moteurs_aide'), h('div', { 'data-id': 'moteurs' }, moteursParRole())]] },
  { id: 'validation', titre: t('reglages.validation'), aide: t('reglages.validation_aide'),
    resume: () => (POLITIQUES.find(([v]) => v === (S.interface?.propositions ?? 'montrer')) || POLITIQUES[0])[1],
    sous: () => [
      ['propositions', t('reglages.propositions'), t('reglages.propositions_aide'), blocPropositions()],
      ['evitable', t('evitable.titre'), t('reglages.evitable_aide'), sectionEvitable()[1]],
      ['integration', t('integration.titre'), t('reglages.integration_aide'), sectionIntegration()[1]]] },
  { id: 'connexions', titre: t('reglages.connexions'), aide: t('reglages.connexions_aide'),
    resume: () => parts('telegram', 'appareils', 'executeurs'),
    sous: () => [
      ['telegram', null, null, sectionTelegram()],
      ['appareils', t('reglages.appareils'), t('reglages.appareils_aide'), sectionAppareils()[1]],
      ['executeurs', t('reglages.executeurs'), t('reglages.executeurs_aide'), sectionExecuteurs()[1]]] },
  { id: 'installation', titre: t('reglages.installation'), aide: t('reglages.installation_aide'),
    resume: () => [RESUMES.installation, versionTexte()].filter(Boolean).join(' · '),
    sous: () => [
      ['installation', t('installation.titre'), t('reglages.installation_bloc_aide'), sectionInstallation()[1]],
      ['version', t('reglages.version'), t('reglages.version_aide'), h('p', { class: 'note', 'data-id': 'rg-version' }, versionTexte())],
      ['maj-auto', t('reglages.maj_auto'), t('reglages.maj_auto_aide'), sectionMiseAJour()[1]],
      ['signaler', t('reglages.signaler'), t('reglages.signaler_aide'), sectionSignaler()],
      ['premiers-pas', titreSectionPremiersPas(), null, h('div', null, ...sectionPremiersPas())],
      ['accueil', t('accueil.titre'), null, h('div', null, ...sectionAccueil().slice(1))]] },
];
// Sous-section → groupe, pour l'ancre #reglages/<sous-section>.
const ANCRES = { mode: 'affichage', theme: 'affichage', familles: 'fonctions', simultanes: 'agents', economie: 'agents', compactage: 'agents', apprendre: 'agents', reflexes: 'agents', rangement: 'agents',
  moteurs: 'agents', propositions: 'validation', telegram: 'connexions', appareils: 'connexions', executeurs: 'connexions',
  installation: 'installation', langue: 'affichage', version: 'installation', etoile: 'affichage', evitable: 'validation', integration: 'validation',
  'maj-auto': 'installation', signaler: 'installation', accueil: 'installation', 'premiers-pas': 'installation' };
const groupeDe = (cle) => GROUPES.find((g) => g.id === (ANCRES[cle] || cle));

// Sections ouvertes : par visiteur (ce navigateur) ; la première seule par défaut.
const CLE_OUVERTS = 'orch.reglages.ouverts';
function ouverts() {
  try { const v = JSON.parse(localStorage.getItem(CLE_OUVERTS)); if (Array.isArray(v)) return new Set(v); } catch { /* valeur illisible : défaut */ }
  return new Set([GROUPES[0].id]);
}
function memoriser(racine) {
  if (requete) return; // une ouverture due à la recherche n'est pas un choix du visiteur
  const ids = [...racine.querySelectorAll('details.rg-groupe[open]')].map((d) => d.dataset.groupe);
  try { localStorage.setItem(CLE_OUVERTS, JSON.stringify(ids)); } catch { /* stockage refusé : non mémorisé */ }
}

// Ancre #reglages/<groupe ou sous-section> : posée par l'URL, appliquée une fois au dessin suivant.
let ancre = null, aAppliquer = false;
export function fixerAncreReglages(a) { ancre = a || null; aAppliquer = !!ancre; }
export const hashReglages = () => `#reglages${ancre ? `/${ancre}` : ''}`;
on('selection', () => { if (S.vue !== 'reglages' || S.selection) ancre = null; });

let requete = '';
const plier = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// Tours depuis le démarrage par harnais et par rôle (S.etat.roles, INV-MOTEUR-2) : ce qui part sur Antigravity se voit ici.
function moteursParRole() {
  const r = S.etat?.roles || { tours: [], replis: [], roles: {} };
  const lignes = r.tours.map((tr) => h('li', null, tn('reglages.seances', tr.tours, { assistant: tr.harnais, role: tr.role })));
  const regles = Object.entries(r.roles).map(([role, c]) => h('li', null, t('reglages.regle', { role: role + (c.famille ? ` (${c.famille})` : ''), choix: c.moteurs.map(([nom, modele]) => nom + (modele ? ` ${modele}` : '')).join(t('reglages.puis')) })));
  return [h('ul', { class: 'rg-liste', 'data-id': 'roles-reglage' }, regles.length ? regles : h('li', null, t('reglages.aucun_role'))),
    h('ul', { class: 'rg-liste', 'data-id': 'roles-tours' }, lignes.length ? lignes : h('li', null, t('reglages.aucune_seance'))),
    ...(r.replis.length ? [h('p', { class: 'note', 'data-id': 'roles-replis' }, t('reglages.replis', { liste: r.replis.map((x) => `${x.role} ${x.de}→${x.vers}`).join(' ; ') }))] : []),
    h('p', { class: 'note' }, t('reglages.regles_dans'))];
}

function blocMode() {
  const mode = (valeur, lib) => h('button', { class: 'btn', type: 'button', 'data-id': `mode-${valeur}`, 'aria-pressed': String((valeur === 'simple') === simple()),
    onclick: () => { if ((valeur === 'simple') !== simple()) agir({ mode: valeur }); } }, lib);
  return h('div', { class: 'rg-mode', role: 'group', 'aria-label': t('reglages.niveau') }, mode('simple', t('reglages.mode_simple')), mode('avance', t('reglages.mode_avance')));
}

// Thème : préférence du poste (localStorage), jamais dans config.toml ; appliqué avant rendu par theme.js.
function blocTheme() {
  const choisir = (v) => {
    if (v === 'systeme') { delete document.documentElement.dataset.theme; localStorage.removeItem('orch.theme'); }
    else { document.documentElement.dataset.theme = v; localStorage.setItem('orch.theme', v); }
    for (const b of document.querySelectorAll('[data-id^="theme-"]')) b.setAttribute('aria-pressed', String(b.dataset.id === `theme-${v}`));
    majResumes();
  };
  return h('div', { class: 'rg-mode', role: 'group', 'aria-label': t('reglages.theme') },
    THEMES.map(([v, lib]) => h('button', { class: 'btn', type: 'button', 'data-id': `theme-${v}`, 'aria-pressed': String(v === theme()), onclick: () => choisir(v) }, lib)));
}

function blocPropositions() {
  return [h('select', { 'data-id': 'propositions', 'aria-label': t('reglages.propositions'), onchange: (e) => agir({ propositions: e.target.value }) },
    POLITIQUES.map(([v, l]) => h('option', { value: v, selected: v === (S.interface?.propositions ?? 'montrer') ? true : null }, l))),
  h('p', { class: 'note' }, t('reglages.ecrits_dans'))];
}

function interrupteur(f) {
  const [nom, phrase] = PHRASES[f];
  return h('li', { class: 'rg-fam' },
    h('label', { class: 'case' },
      h('input', { type: 'checkbox', 'data-id': f, checked: ouvert(f) ? true : null, onchange: (e) => agir({ familles: { [f]: e.target.checked } }) }),
      h('b', null, nom)),
    h('div', { class: 'rg-phrase' }, phrase));
}

function groupe(g, ouvertes, racine) {
  return h('details', { class: 'rg-groupe', 'data-groupe': g.id, id: `reglages-${g.id}`, open: ouvertes.has(g.id), ontoggle: () => memoriser(racine) },
    h('summary', null, h('span', { class: 'rg-titre' }, g.titre), h('span', { class: 'rg-resume', 'data-resume': g.id }, g.resume())),
    h('p', { class: 'rg-aide' }, g.aide),
    g.sous().map(([cle, titre, aide, contenu]) => h('section', { class: 'rg-bloc', 'data-ancre': cle },
      titre ? h('h3', null, titre) : null, aide ? h('p', { class: 'rg-aide' }, aide) : null, contenu)));
}

function majResumes() {
  for (const g of GROUPES) {
    const el = document.querySelector(`.reglages [data-resume="${g.id}"]`);
    if (el) el.textContent = g.resume();
  }
}
on('resume', ([cle, texte]) => { RESUMES[cle] = texte; majResumes(); });

// Recherche : ne garde que les groupes dont le texte contient chaque mot, et les ouvre (sans le mémoriser).
function filtrer(racine) {
  const mots = plier(requete).split(/\s+/).filter(Boolean);
  const etat = ouverts();
  for (const d of racine.querySelectorAll('details.rg-groupe')) {
    const ok = mots.every((m) => plier(d.textContent).includes(m));
    d.hidden = !ok;
    d.open = mots.length ? ok : etat.has(d.dataset.groupe);
  }
  const rien = racine.querySelector('[data-id=rg-aucun]');
  rien.hidden = !mots.length || !!racine.querySelector('details.rg-groupe:not([hidden])');
}

function appliquerAncre(racine) {
  if (!aAppliquer) return;
  aAppliquer = false;
  const g = groupeDe(ancre);
  if (!g) return;
  const d = racine.querySelector(`details[data-groupe="${g.id}"]`);
  d.open = true;
  const cible = racine.querySelector(`[data-ancre="${CSS.escape(ancre)}"]`) || d;
  requestAnimationFrame(() => cible.scrollIntoView({ block: 'start' }));
}

export function dessinerReglages(el) {
  // INV-REGLAGES-1 : saisie en cours et focus survivent au redessin (changement de mode, d'une famille).
  const actif = el.contains(document.activeElement) ? document.activeElement : null;
  const garde = actif?.dataset?.id ? { id: actif.dataset.id, valeur: actif.value, debut: actif.selectionStart, fin: actif.selectionEnd } : null;
  const racine = h('div', { class: 'equipe reglages' });
  const chercher = h('input', { type: 'search', class: 'rg-chercher', 'data-id': 'rg-chercher', placeholder: t('reglages.chercher_ph'),
    'aria-label': t('reglages.chercher'), value: requete, oninput: (e) => { requete = e.target.value; filtrer(racine); } });
  const ouvertes = ouverts();
  remplacer(racine,
    h('div', { class: 'eq-tete' }, h('h2', null, t('reglages.titre')), boutonAide('reglages')),
    chercher,
    h('p', { class: 'note', 'data-id': 'rg-aucun', hidden: true }, t('reglages.aucun')),
    GROUPES.map((g) => groupe(g, ouvertes, racine)));
  remplacer(el, racine);
  if (requete) filtrer(racine);
  appliquerAncre(racine);
  if (!garde) return;
  const cible = el.querySelector(`[data-id="${CSS.escape(garde.id)}"]`);
  if (!cible) return;
  if ('value' in cible && garde.valeur !== undefined && cible.type !== 'checkbox' && cible.type !== 'radio') cible.value = garde.valeur;
  cible.focus();
  try { if (garde.debut != null) cible.setSelectionRange(garde.debut, garde.fin); } catch { /* champ sans sélection (nombre) */ }
}

// Événement 'etat' (fréquent : chaque ligne d'activité d'un agent) : seules les parties qui en dépendent changent.
export function etatReglages(el) {
  const moteurs = el.querySelector('.reglages [data-id=moteurs]');
  if (!moteurs) { dessinerReglages(el); return; }
  remplacer(moteurs, moteursParRole());
  const v = el.querySelector('[data-id=rg-version]');
  if (v) v.textContent = versionTexte();
  majResumes();
}
