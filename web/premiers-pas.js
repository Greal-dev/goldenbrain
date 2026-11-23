// Rôle : premiers pas d'un nouvel arrivant, en 2 écrans — 1. quels assistants IA sont prêts sur ce poste (et comment installer celui
// qui manque : page officielle, commande à copier, « Vérifier à nouveau ») ; 2. une tâche de démonstration qui répond en une ou deux minutes.
// Frontières : GET /api/accueil/premiers-pas(/assistants), POST /api/accueil/premiers-pas/fait (poste seulement), GET /api/modeles,
// POST /api/taches ; réflexes de l'agent (`reflexes.js`, proposés au 2e écran). N'installe rien (INV-PREMIERS-PAS-1) ; enchaîne sur l'accueil existant (`suite`) sans le refaire. INV-WEB-1 : tout passe par h().
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit, ouvrir } from './store.js';
import { t } from './langues.js';
import { sectionReflexes } from './reflexes.js';

const NODE = 'https://nodejs.org/';
const DEMO = 'premiere-tache';
let E = null; // { ecran, assistants, defaut, choix }
let boite = null;
let suite = null;

/** Premier lancement : ouvre les premiers pas s'ils sont proposés, puis passe la main à `apres` (l'accueil). */
export async function initPremiersPas(apres) {
  let propose = false;
  try { propose = (await api('/accueil/premiers-pas')).propose; } catch { /* serveur distant ou injoignable */ }
  if (propose) ouvrirPremiersPas(apres); else apres?.();
}

export function ouvrirPremiersPas(apres = null) {
  suite = apres;
  E = { ecran: 1, assistants: null, defaut: '', choix: '' };
  boite?.remove();
  boite = h('div', { class: 'accueil', role: 'dialog', 'aria-modal': 'true', 'aria-label': t('premiers-pas.titre'), 'data-id': 'premiers-pas' });
  document.body.append(boite);
  dessiner();
  verifier();
}

async function verifier() {
  E.assistants = null; dessiner();
  try { const r = await api('/accueil/premiers-pas/assistants'); E.assistants = r.assistants; E.defaut = r.defaut; } catch (e) { erreur(e.message); E.assistants = []; }
  const prets = pilotables();
  if (!prets.some((a) => a.id === E.choix)) E.choix = (prets.find((a) => a.id === E.defaut) || prets[0])?.id || '';
  dessiner();
}

const pilotables = () => (E?.assistants || []).filter((a) => a.pilotable);

// « Plus tard » clôt tout le parcours : un second dialogue de bienvenue juste après serait une double demande (audit L3, A2).
async function plusTard() {
  try { await post('/accueil/plus-tard', {}); } catch { /* l'accueil se reproposera au prochain passage */ }
  suite = null;
  await fermer();
}

async function fermer() {
  try { await post('/accueil/premiers-pas/fait', {}); } catch { /* l'état « fait » se reposera au prochain passage */ }
  boite?.remove(); boite = null; E = null;
  const s = suite; suite = null; s?.();
}

function dessiner() {
  if (!boite || !E) return;
  const pas = h('ol', { class: 'ac-pas' }, [t('premiers-pas.pas_assistant'), t('premiers-pas.pas_tache')].map((x, i) => h('li', { class: i + 1 === E.ecran ? 'en-cours' : i + 1 < E.ecran ? 'fait' : null }, `${i + 1}. ${x}`)));
  remplacer(boite, h('div', { class: 'ac-carte' }, h('h2', null, t('premiers-pas.titre')), pas, E.ecran === 1 ? ecranAssistants() : ecranDemo()));
}

function copiable(texte, cle) {
  const code = h('code', { 'data-id': `pp-commande-${cle}` }, texte);
  const b = h('button', { class: 'btn', type: 'button', 'data-id': `pp-copier-${cle}`, onclick: async () => {
    try { await navigator.clipboard.writeText(texte); b.textContent = t('premiers-pas.copie'); } catch { getSelection()?.selectAllChildren(code); }
  } }, t('premiers-pas.copier'));
  return h('div', { class: 'pp-commande' }, code, b);
}

function ligne(a) {
  const etat = !a.installe ? t('premiers-pas.absent') : a.connexion === 'a_connecter' ? t('premiers-pas.a_connecter') : t('premiers-pas.pret');
  const aide = [];
  if (!a.installe) {
    if (a.attend?.includes('node')) aide.push(h('p', null, t('premiers-pas.dabord', { outil: 'Node.js' }), h('a', { href: NODE, target: '_blank', rel: 'noopener' }, NODE)));
    if (a.commande) aide.push(h('p', null, t('premiers-pas.terminal')), h('p', null, t('premiers-pas.coller')), copiable(a.commande, a.id));
    if (a.instructions) aide.push(h('p', null, a.instructions));
    if (a.lien) aide.push(h('p', null, h('a', { href: a.lien, target: '_blank', rel: 'noopener', 'data-id': `pp-lien-${a.id}` }, t('premiers-pas.page'))));
    aide.push(h('p', { class: 'note' }, t('premiers-pas.revenir')));
  } else if (a.connexion === 'a_connecter' && a.aide_connexion) aide.push(h('p', null, t('premiers-pas.connecter', { aide: a.aide_connexion })));
  return h('li', { class: 'pp-assistant', 'data-id': `pp-${a.id}`, 'data-etat': a.installe ? (a.connexion === 'a_connecter' ? 'a_connecter' : 'pret') : 'absent' },
    h('div', null, h('b', null, a.libelle), ` — ${etat}`),
    aide.length ? h('details', { open: !a.installe && !pilotables().length ? true : null }, h('summary', null, a.installe ? t('premiers-pas.connecter_titre') : t('premiers-pas.comment_installer')), aide) : null);
}

function ecranAssistants() {
  const liste = E.assistants;
  return [
    h('p', null, t('premiers-pas.intro')),
    h('p', { class: 'note', 'data-id': 'pp-prerequis' }, t('premiers-pas.prerequis')),
    liste ? h('ul', { class: 'pp-liste', 'data-id': 'pp-liste' }, liste.map(ligne)) : h('p', { class: 'note' }, t('premiers-pas.lecture')),
    liste && !pilotables().length ? h('p', { class: 'note', 'data-id': 'pp-aucun' }, t('premiers-pas.aucun')) : null,
    h('div', { class: 'ac-actions' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'pp-verifier', onclick: verifier }, t('premiers-pas.verifier')),
      h('button', { class: 'btn', type: 'button', 'data-id': 'pp-plus-tard', onclick: plusTard }, t('premiers-pas.plus_tard')),
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'pp-continuer', disabled: pilotables().length ? null : true, onclick: () => { E.ecran = 2; dessiner(); } }, t('premiers-pas.continuer'))),
  ];
}

function ecranDemo() {
  const prets = pilotables();
  return [
    h('p', null, t('premiers-pas.demo_intro')),
    h('label', { class: 'ac-champ' }, t('premiers-pas.avec'), h('select', { 'data-id': 'pp-choix', onchange: (e) => { E.choix = e.target.value; } },
      prets.map((a) => h('option', { value: a.id, selected: a.id === E.choix ? true : null }, a.libelle)))),
    h('p', { class: 'note' }, t('premiers-pas.ensuite')),
    h('p', { class: 'avertissement', role: 'note', 'data-id': 'pp-avertissement' }, t('premiers-pas.avertissement')),
    h('details', { 'data-id': 'pp-reflexes' }, h('summary', null, t('reflexes.titre')), h('p', null, t('reflexes.aide')), sectionReflexes()),
    h('div', { class: 'ac-actions' },
      h('button', { class: 'btn', type: 'button', 'data-id': 'pp-retour', onclick: () => { E.ecran = 1; dessiner(); } }, t('premiers-pas.retour')),
      h('button', { class: 'btn', type: 'button', 'data-id': 'pp-passer', onclick: fermer }, t('premiers-pas.passer')),
      h('button', { class: 'btn primaire', type: 'button', 'data-id': 'pp-lancer', onclick: lancerDemo }, t('premiers-pas.lancer'))),
  ];
}

async function lancerDemo(e) {
  e.target.disabled = true;
  try {
    const m = (await api('/modeles')).find((x) => x.id === DEMO);
    if (!m) throw new Error(t('premiers-pas.demo_absente', { id: DEMO }));
    const tache = await post('/taches', { titre: m.titre, description: m.mission, mission: m.mission, lancer: true, harnais: E.choix, forcer: true });
    suite = null; // la démonstration est la suite : l'accueil reste dans les Réglages
    await fermer();
    emit('recharger');
    ouvrir(tache.id);
  } catch (x) { erreur(x.message); e.target.disabled = false; }
}

export const titreSectionPremiersPas = () => t('premiers-pas.section_titre');

export function sectionPremiersPas() {
  return [h('p', { class: 'note' }, t('premiers-pas.section')),
    h('button', { class: 'btn', type: 'button', 'data-id': 'revoir-premiers-pas', onclick: () => ouvrirPremiersPas() }, t('premiers-pas.revoir'))];
}
