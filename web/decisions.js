// Rôle : page « Décisions » — tout ce qui attend l'utilisateur, la question en clair, tranché sur place.
// Frontières : lit GET /decisions (tri fait par le serveur, INV-DECISIONS-1) ; chaque geste passe par une route
// existante (valider, renvoyer, messages, temps, propositions) ou par les lots /decisions/valider|fermer|agents ; « Scanner le système » par /decisions/scan (INV-SCAN-1 : propositions en attente, rien d'appliqué) ; « Rouvrir » par /validation-auto/rouvrir.
import { h, remplacer, pastille, nomLisible } from './dom.js';
import { api, post } from './api.js';
import { ouvrir, emit, erreur, titreTache } from './store.js';
import { formulaire } from './dialogue.js';
import { description } from './propositions.js';
import { libelleEcheance } from './temps.js';
import { ligneAgent, lotAgents } from './decisions-agents.js';
import { boutonAide } from './guide.js';
import { t, tn } from './langues.js';

let coque = null, version = 0, donnees = null;
const reponses = new Map();   // brouillons de réponse, conservés d'un redessin à l'autre
const cochees = new Set();    // lignes « à valider » cochées pour le lot
const fermetures = new Set(); // fermetures de revue cochées (n de proposition)
const repliees = new Set();   // projets repliés
let seulementRapides = false;

const recharger = () => { emit('recharger'); return actualiser(); };
async function geste(fn) {
  try { await fn(); } catch (e) { erreur(e.message); }
  await recharger();
}
async function documenter(d) {
  await geste(() => post('/decisions/documenter', { tache: d.tache }));
}
const lot = async (chemin, corps) => {
  const r = await post(chemin, corps);
  if (r.echecs.length) erreur(t('decisions.refuses', { n: r.echecs.length, liste: r.echecs.map((e) => e.erreur).join(' ; ') }));
};

async function refuser(d) {
  const v = await formulaire({ titre: t('decisions.refuser_titre', { titre: d.titre }), valider: t('decisions.renvoyer'),
    champs: [{ nom: 'texte', label: t('decisions.motif_renvoi'), type: 'textarea', requis: true }] });
  if (v) await geste(() => post(`/taches/${d.tache}/renvoyer`, { texte: v.texte.trim() }));
}

function reporter(d) {
  const date = h('input', { type: 'date', 'aria-label': t('decisions.reporter_a'), value: d.echeance || '' });
  return h('span', { class: 'dc-report' }, date,
    h('button', { class: 'btn petit', type: 'button', onclick: () => date.value && geste(() => post(`/taches/${d.tache}/temps`, { echeance: date.value })) }, t('decisions.reporter')));
}

function repondre(d) {
  const zone = h('textarea', { rows: 2, placeholder: t('decisions.reponse_invite'), 'aria-label': t('decisions.reponse'), oninput: () => reponses.set(d.id, zone.value) }, reponses.get(d.id) || '');
  return h('div', { class: 'dc-rep' }, zone,
    h('button', { class: 'btn primaire petit', type: 'button', onclick: () => zone.value.trim() && geste(async () => {
      await post(`/taches/${d.tache}/messages`, { texte: zone.value.trim() });
      reponses.delete(d.id);
    }) }, t('decisions.repondre')));
}

// « De quoi il s'agit » et « Ce qui a été fait » : deux lignes ; sinon « Fiche muette » et la consigne à l'agent.
function fiche(d) {
  if (d.genre === 'revue' || d.genre === 'scan') return null;
  const l = (titre, texte) => h('p', { class: `dc-l${texte ? '' : ' manque'}` }, h('b', null, t('decisions.ligne_titre', { titre })), texte || t('decisions.non_renseigne'));
  return h('div', { class: 'dc-fiche' }, l(t('decisions.de_quoi'), d.sujet), l(t('decisions.ce_qui_fait'), d.fait),
    d.muette ? h('p', { class: 'dc-muette' }, h('span', { class: 'tag muette' }, t('decisions.fiche_muette')), ' ',
      h('button', { class: 'btn petit', type: 'button', 'data-documenter': '', title: t('decisions.documenter_titre'), onclick: () => documenter(d) }, t('decisions.faire_documenter'))) : null);
}

function corps(d) {
  switch (d.genre) {
    case 'validation':
      return [h('p', { class: `dc-q${d.resultat ? '' : ' manque'}` }, h('b', null, t('decisions.resultat')), d.resultat || d.fait || t('decisions.non_indique')),
        d.essai ? h('p', { class: 'dc-essai' }, h('b', null, t('decisions.essai')), d.essai) : null,
        d.auto ? h('p', { class: 'dc-auto', 'data-auto': d.auto.issue }, h('b', null, t('decisions.non_close_auto')), d.auto.motif) : null];
    case 'scan':
    case 'proposition': return [h('p', { class: 'dc-q' }, description(d.proposition)), d.proposition.motif ? h('p', { class: 'dc-essai' }, d.proposition.motif) : null];
    case 'revue': return h('ul', { class: 'dc-ferm' }, d.fermetures.map((f) => h('li', null,
      h('label', null, h('input', { type: 'checkbox', checked: fermetures.has(f.n) ? true : null, onchange: (e) => (e.target.checked ? fermetures.add(f.n) : fermetures.delete(f.n)) }),
        ' ', h('b', null, f.titre), ' ' + (f.statut === 'abandonne' ? t('decisions.abandonnee') : t('decisions.cloturee')), f.motif ? ` — ${f.motif}` : ''))));
    default: return h('p', { class: `dc-q${d.question ? '' : ' manque'}`, title: d.source ? t('decisions.source', { source: d.source }) : '' }, d.question || t('decisions.aucune_question'));
  }
}

function actions(d) {
  switch (d.genre) {
    case 'validation': return [
      h('button', { class: 'btn primaire petit', type: 'button', onclick: () => geste(() => post(`/taches/${d.tache}/valider`, {})) }, t('decisions.valider')),
      h('button', { class: 'btn petit', type: 'button', onclick: () => refuser(d) }, t('decisions.refuser_pts')), reporter(d)];
    case 'scan':
    case 'proposition': return [
      h('button', { class: 'btn primaire petit', type: 'button', onclick: () => geste(() => post(`/propositions/${d.proposition.n}/accepter`)) }, t('decisions.accepter')),
      h('button', { class: 'btn petit', type: 'button', onclick: () => geste(() => post(`/propositions/${d.proposition.n}/refuser`)) }, t('decisions.refuser'))];
    case 'revue': return [h('button', { class: 'btn primaire petit', type: 'button', 'data-appliquer': '',
      onclick: () => {
        const n = d.fermetures.map((f) => f.n).filter((x) => fermetures.has(x));
        if (!n.length) return;
        n.forEach((x) => fermetures.delete(x));
        geste(() => lot('/decisions/fermer', { numeros: n }));
      } }, t('decisions.appliquer_fermetures'))];
    case 'routine': return [ // INV-ROUTINE-4 : la ligne disparaît à la prochaine exécution réussie
      h('button', { class: 'btn primaire petit', type: 'button', onclick: () => geste(() => post(`/routines/${encodeURIComponent(d.tache)}/executer`)) }, t('decisions.relancer')),
      h('button', { class: 'btn petit', type: 'button', onclick: () => geste(() => post(`/routines/${encodeURIComponent(d.tache)}/modifier`, { pause: true })) }, t('decisions.mettre_en_pause'))];
    default: return [repondre(d), reporter(d)];
  }
}

// Propositions restantes : une entrée repliée par tâche émettrice (et projet), une ligne chacune, motif au dépli.
function regrouper(liste) {
  const sortie = [], par = new Map();
  for (const d of liste) {
    if (d.genre !== 'proposition') { sortie.push(d); continue; }
    const de = d.proposition.de || d.proposition.tache, cle = `${d.projet}|${de}`;
    if (!par.has(cle)) { par.set(cle, { genre: 'lot', projet: d.projet, de, ds: [] }); sortie.push(par.get(cle)); }
    par.get(cle).ds.push(d);
  }
  return sortie;
}

function ligneLot(g) {
  const ps = g.ds.map((d) => d.proposition);
  const tout = (action) => geste(async () => {
    const echecs = [];
    for (const p of ps) { try { await post(`/propositions/${p.n}/${action}`); } catch (e) { echecs.push(e.message); } }
    if (echecs.length) erreur(t('decisions.refuses', { n: echecs.length, liste: echecs.join(' ; ') }));
  });
  return h('li', { class: 'dc dc-proposition', 'data-genre': 'proposition', 'data-de': g.de },
    h('details', { class: 'dc-lot' },
      h('summary', null, h('span', { class: 'tag' }, t('decisions.propositions_de', { de: titreTache(g.de) })), ' ', h('span', { class: 'n' }, ps.length)),
      h('ul', { class: 'dc-props' }, ps.map((p) => h('li', { class: 'dc-prop', 'data-n': p.n, title: p.motif || null },
        p.motif ? h('details', null, h('summary', null, description(p)), h('p', { class: 'dc-essai' }, p.motif)) : h('span', null, description(p)),
        p.echec ? h('p', { class: 'dc-essai manque' }, t('decisions.echec_office', { motif: p.echec })) : null,
        h('span', { class: 'dc-prop-btns' },
          h('button', { class: 'btn primaire petit', type: 'button', 'data-accepter': '', onclick: () => geste(() => post(`/propositions/${p.n}/accepter`)) }, t('decisions.accepter')),
          h('button', { class: 'btn petit', type: 'button', 'data-refuser': '', onclick: () => geste(() => post(`/propositions/${p.n}/refuser`)) }, t('decisions.refuser'))))))),
    h('div', { class: 'dc-actions' },
      h('button', { class: 'btn primaire petit', type: 'button', 'data-tout': 'accepter', onclick: () => tout('accepter') }, t('decisions.tout_accepter')),
      h('button', { class: 'btn petit', type: 'button', 'data-tout': 'refuser', onclick: () => tout('refuser') }, t('decisions.tout_refuser'))));
}

// INV-PROP-1 : journal des gestes appliqués d'office (7 derniers jours), replié, chacun annulable.
function office(liste) {
  if (!liste?.length) return null;
  return h('details', { class: 'dc-groupe dc-office' },
    h('summary', null, t('decisions.office'), ' ', h('span', { class: 'n' }, liste.length)),
    h('ul', { class: 'dc-liste' }, liste.map((p) => h('li', { class: 'dc dc-office-geste', 'data-n': p.n, title: p.motif || null },
      h('span', null, description(p)), ' ',
      h('span', { class: 'dc-motif' }, String(p.cree || '').slice(0, 16).replace('T', ' ')), ' ',
      h('button', { class: 'btn petit', type: 'button', 'data-annuler': '', onclick: () => geste(() => post(`/propositions/${p.n}/annuler`)) }, t('decisions.annuler'))))));
}

function ligne(d) {
  if (d.genre === 'lot') return ligneLot(d);
  if (d.genre === 'agent') return ligneAgent(d, { geste, lot, redessiner: dessiner });
  const lotable = d.genre === 'validation' && d.rapide;
  return h('li', { class: `dc dc-${d.genre}`, 'data-genre': d.genre, 'data-tache': d.tache },
    h('div', { class: 'dc-tete' },
      lotable ? h('input', { type: 'checkbox', class: 'dc-coche', 'aria-label': t('decisions.cocher', { titre: d.titre }), checked: cochees.has(d.tache) ? true : null,
        onchange: (e) => { (e.target.checked ? cochees.add(d.tache) : cochees.delete(d.tache)); dessiner(); } }) : pastille(d.statut),
      h('span', { class: 'tag' }, d.libelle),
      d.evitable ? h('span', { class: 'tag evitable', 'data-evitable': '', title: d.evitable.motif }, t('decisions.evitable')) : null,
      h('button', { class: 'dc-titre', type: 'button', title: t('decisions.ouvrir_fiche'), onclick: () => ouvrir(d.tache) }, d.titre),
      d.echeance ? h('span', { class: `au-ech${d.retard ? ' retard' : ''}` }, libelleEcheance(d.echeance, d.retard)) : null,
      h('span', { class: 'dc-motif', title: t('decisions.rang_motif_titre') }, t('decisions.rang', { rang: d.rang, motif: d.motif }))),
    fiche(d),
    h('div', { class: 'dc-corps' }, corps(d), d.evitable ? h('p', { class: 'dc-essai dc-evitable' }, h('b', null, t('decisions.evitable_ligne')), d.evitable.motif) : null),
    h('div', { class: 'dc-actions' }, actions(d)));
}

function groupes(liste) {
  const m = new Map();
  for (const d of liste) { if (!m.has(d.projet)) m.set(d.projet, []); m.get(d.projet).push(d); }
  return [...m].map(([projet, ds]) => h('details', { class: 'dc-groupe', open: repliees.has(projet) ? null : true,
    ontoggle: (e) => { (e.target.open ? repliees.delete(projet) : repliees.add(projet)); } },
  h('summary', null, nomLisible(projet), ' ', h('span', { class: 'n' }, ds.length)), h('ul', { class: 'dc-liste' }, ds.map(ligne))));
}

// INV-VALID-2 : clôtures automatiques des 7 derniers jours, chacune réversible d'un clic.
function closAuto(liste) {
  if (!liste?.length) return null;
  return h('details', { class: 'dc-groupe dc-clos-auto', open: true },
    h('summary', null, t('decisions.clos_auto'), ' ', h('span', { class: 'n' }, liste.length)),
    h('ul', { class: 'dc-liste' }, liste.map((e) => h('li', { class: 'dc dc-clos', 'data-tache': e.tache },
      h('div', { class: 'dc-tete' }, h('span', { class: 'tag' }, t('decisions.clos_auto')),
        h('button', { class: 'dc-titre', type: 'button', title: t('decisions.ouvrir_fiche'), onclick: () => ouvrir(e.tache) }, e.titre),
        h('span', { class: 'dc-motif' }, String(e.date || '').slice(0, 16).replace('T', ' '))),
      h('p', { class: 'dc-essai' }, h('b', null, t('decisions.controle')), e.controle?.reference || '—', ' · ',
        h('b', null, t('decisions.revue')), [e.revue?.harnais, e.revue?.modele].filter(Boolean).join(' ') || '—'),
      h('div', { class: 'dc-actions' }, h('button', { class: 'btn petit', type: 'button', 'data-rouvrir': '',
        title: t('decisions.rouvrir_titre'), onclick: () => geste(() => post('/validation-auto/rouvrir', { tache: e.tache })) }, t('decisions.rouvrir')))))));
}

function dessiner() {
  if (!coque?.isConnected || !donnees) return;
  const tout = donnees.decisions;
  const liste = seulementRapides ? tout.filter((d) => d.rapide) : tout;
  const sel = [...cochees].filter((id) => tout.some((d) => d.tache === id && d.genre === 'validation'));
  const barre = h('div', { class: 'dc-barre' },
    h('label', null, h('input', { type: 'checkbox', id: 'dc-rapides', checked: seulementRapides ? true : null,
      onchange: (e) => { seulementRapides = e.target.checked; dessiner(); } }), t('decisions.rapides_seulement')),
    h('button', { class: 'btn primaire petit', id: 'dc-lot', type: 'button', disabled: sel.length ? null : true,
      onclick: () => { cochees.clear(); geste(() => lot('/decisions/valider', { taches: sel })); } }, t('decisions.valider_selection', { n: sel.length })),
    tout.some((d) => d.genre === 'agent') ? lotAgents(tout, { geste, lot }) : null,
    h('button', { class: 'btn petit', id: 'dc-scan', type: 'button', title: t('decisions.scan_titre'),
      onclick: () => geste(async () => {
        const r = await post('/decisions/scan', {});
        if (r.erreurs.length) erreur(t('decisions.ecartees', { n: r.erreurs.length, liste: r.erreurs.map((e) => e.erreur).join(' ; ') }));
      }) }, t('decisions.scanner')));
  remplacer(coque, h('h2', { class: 'casc-titre' }, t('decisions.titre'), ' ', boutonAide('decisions')),
    h('p', { class: 'au-date' }, tn('decisions.en_attente', tout.length) + (seulementRapides ? ' — ' + tn('decisions.rapides', liste.length) : '')),
    donnees.reprises?.length ? h('p', { class: 'dc-reprises', 'data-reprises': '' }, t('decisions.reprises', { liste: donnees.reprises.map((r) => r.titre).join(', ') })) : null, // INV-DECISIONS-2
    barre, liste.length ? groupes(regrouper(liste)) : h('p', { class: 'vide' }, t('decisions.rien')), closAuto(donnees.clos_auto), office(donnees.office));
}

// Un redessin tardif d'un appel périmé est ignoré (même garde que « Aujourd'hui »).
async function actualiser() {
  const moi = ++version;
  try {
    const d = await api('/decisions');
    if (moi !== version) return;
    donnees = d;
    dessiner();
  } catch (e) { erreur(e.message); }
}

export function dessinerDecisions(zone) {
  if (!coque || coque.parentNode !== zone) {
    coque = h('div', { class: 'decisions' }, h('p', { class: 'vide' }, t('decisions.chargement')));
    remplacer(zone, coque);
  }
  return actualiser();
}
