// Rôle : bandeau haut — tours en cours, compteurs (dont « Aujourd'hui »), panneau de propositions, recherche, nouvelle tâche.
// Frontières : lit S ; les créations passent par l'API puis ouvrent la tâche.
import { t, tn } from './langues.js';
import { h, $, depuis, heure, remplacer, filLisible, libelleStatut } from './dom.js';
import { S, on, emit, ouvrir, ouvrirVue, erreur, parcourir } from './store.js';
import { ouvert, simple } from './interface.js';
import { post, api } from './api.js';
import { formulaire, champ } from './dialogue.js';
import { nouvelleRoutine } from './routines.js';
import { ouvrirChaines } from './chaines.js';
import { listePropositions, enAttente } from './propositions.js';
import { initRecherche } from './recherche.js';
import { PRIORITES } from './temps.js';
import { dessinerAlertes } from './vigie.js';
import { ouvrirGuide } from './guide.js';
import { galerieModeles } from './modeles.js';
import { dialogueRangement } from './lignes.js';
import { deroulant } from './deroulant.js';

function pastilleTour(x) {
  // INV-VIGIE-1 : phrase d'activité et fraîcheur ; un silence prolongé se dit à la place.
  const s = x.signe;
  const dernier = s?.silencieux ? t('bandeau.silencieux', { duree: depuis(s.depuis) }) : s ? t('bandeau.signe', { phrase: s.phrase, duree: depuis(s.depuis) })
    : (x.dernier || '').split('\n').filter(Boolean).at(-1) || t('bandeau.demarrage');
  return h('button', {
    class: `tour${S.selection === x.tache ? ' sel' : ''}${s?.silencieux ? ' silence' : ''}`, type: 'button', role: 'listitem',
    title: `${x.titre}\n${dernier}`, onclick: () => ouvrir(x.tache),
  }, x.pause_ram || s?.pause_manuelle ? h('span', { class: 'etat pause-ram' }, '⏸') : h('span', { class: 'tourne' }),
  h('span', { class: 'tour-txt' }, h('b', null, x.titre), h('span', { class: 'tour-act' }, s?.pause_manuelle ? t('bandeau.pause_manuelle') : x.pause_ram ? t('bandeau.pause_ram') : dernier)),
  h('span', { class: 'tour-t' }, depuis(x.depuis)));
}

// INV-POSTE-1 : bandeau discret tant que le poste est réservé (une porte lourde tourne, les épreuves des autres attendent).
function dessinerPoste(p) {
  const zone = $('#poste-reserve');
  zone.hidden = !p;
  if (!p) return;
  remplacer(zone, h('span', { class: 'maj-t' }, h('b', null, t('bandeau.poste_reserve')),
    t(p.motif ? 'bandeau.poste_par_motif' : 'bandeau.poste_par', { tache: p.tache, motif: p.motif, heure: heure(p.depuis) })
    + (p.file?.length ? t('bandeau.poste_file', { liste: p.file.map((e, i) => `${i + 1}. ${e.tache}`).join(', ') }) : '')),
  h('button', { type: 'button', class: 'btn petit', title: t('bandeau.liberer_titre'),
    onclick: () => post('/poste/liberer', {}).catch((x) => erreur(x.message)) }, t('bandeau.liberer')));
}

// INV-RESEAU-1 : bandeau tant qu'un fournisseur est injoignable (réseau perdu, ou un seul fournisseur en panne).
function dessinerReseau(r) {
  const zone = $('#reseau-perdu');
  const hors = Object.entries(r?.hors || {});
  zone.hidden = !hors.length;
  if (zone.hidden) return;
  const ags = tn('bandeau.agents_attente', r.en_attente || 0);
  remplacer(zone, h('span', { class: 'maj-t' }, r.perdu_depuis
    ? [h('b', null, t('bandeau.reseau_perdu', { heure: heure(r.perdu_depuis) })), t('bandeau.reseau_suite', { agents: ags })]
    : [h('b', null, t('bandeau.fournisseur', { noms: hors.map(([k]) => k).join(', ') })), t('bandeau.fournisseur_suite', { heure: heure(hors[0][1]), agents: ags })]));
}

export function dessinerBandeau() {
  const e = S.etat;
  $('#n-tours').textContent = e.tours.length;
  for (const [cle, n] of [['avalider', e.moi_valider], ['questions', e.moi_questions], ['afaire', e.moi_faire]]) { // INV-MAIN-4 : trois pastilles
    $(`#n-${cle}`).textContent = n || 0;
    $(`#btn-${cle}`).classList.toggle('alerte', n > 0);
  }
  $('#n-recent').textContent = e.recent || 0;
  $('#btn-recent').setAttribute('aria-pressed', String(!S.selection && S.vue === 'etiquette' && S.portee === 'recent'));
  $('#n-retard').textContent = e.en_retard || 0;
  $('#btn-aujourdhui').setAttribute('aria-pressed', String(!S.selection && S.vue === 'aujourdhui'));
  $('#btn-aujourdhui').classList.toggle('alerte', (e.en_retard || 0) > 0);
  $('#n-props').textContent = e.propositions;
  $('#n-decisions').textContent = e.decisions || 0;
  $('#btn-decisions').setAttribute('aria-pressed', String(!S.selection && S.vue === 'decisions'));
  $('#btn-decisions').classList.toggle('alerte', (e.decisions || 0) > 0);
  $('#btn-equipe').setAttribute('aria-pressed', String(!S.selection && S.vue === 'equipe'));
  $('#btn-guide').setAttribute('aria-pressed', String(!S.selection && S.vue === 'guide'));
  $('#btn-props').classList.toggle('alerte', e.propositions > 0);
  dessinerPoste(e.poste);
  dessinerAlertes($('#vigie-alertes'), e.alertes_vigie);
  dessinerReseau(e.reseau);
  const cont = $('#tours');
  remplacer(cont, e.tours.length ? e.tours.map(pastilleTour) : h('span', { class: 'aucun' }, t('bandeau.aucun_actif')));
  dessinerFile(e.file || []);
  props?.redessiner();
}

// INV-ORDO-1, INV-ORDO-2 : rang et motif de chaque tour en file, ou les prérequis qu'il attend.
function dessinerFile(file) {
  $('#lib-file').hidden = !file.length;
  $('#n-file').textContent = file.length;
  remplacer($('#file'), file.map((f) => {
    const rang = f.rang ? (f.rang === 1 ? t('bandeau.rang1') : t('bandeau.rang', { n: f.rang })) : '';
    const act = f.attend.length ? t('bandeau.attend', { liste: f.attend.join(', ') })
      : `${rang ? t('bandeau.rang_motif', { rang, motif: f.motif }) : t('bandeau.en_file')}${f.raison ? ` · ${f.raison}` : ''}`; // INV-VIGIE-2
    return h('button', { class: `tour file-tour${S.selection === f.tache ? ' sel' : ''}`, type: 'button', role: 'listitem',
      'data-id': f.tache, title: `${f.titre}
${act}`, onclick: () => ouvrir(f.tache) },
    h('span', { class: 'tour-txt' }, h('b', null, f.titre), h('span', { class: 'tour-act' }, act)));
  }));
}

// INV-DEROULANT-1 : « Propositions (n) » déroule le panneau compact, rien de permanent à l'écran.
let props = null;
const dessinerPanneau = (corps) => remplacer(corps, enAttente().length ? listePropositions(enAttente()) : h('p', { class: 'vide' }, t('bandeau.aucune_proposition')));

// INV-RAPPROCHEMENT-1 : tâches proches de la demande, avec « Compléter celle-ci » (message sur l'existante).
const DELAI_PROCHES = 350;
function carteProche(c, completer) {
  return h('li', { class: 'proche', 'data-id': c.id },
    h('span', { class: 'proche-titre' }, c.titre), ' ',
    h('span', { class: 'proche-meta' }, `${c.ouverte ? libelleStatut(c.statut) : t('bandeau.close_recemment')} · ${filLisible(c.fil_ariane).join(' › ')}${c.forte ? t('bandeau.tres_proche') : ''}`),
    h('button', { type: 'button', class: 'btn', 'data-completer': c.id, onclick: (e) => completer(c, e.currentTarget) }, t('bandeau.completer')));
}
function listeProches(completer) {
  const zone = h('div', { class: 'proches', 'data-id': 'proches', hidden: true, 'aria-live': 'polite' });
  let minuteur = 0; let seq = 0;
  const maj = (titre) => {
    clearTimeout(minuteur);
    minuteur = setTimeout(async () => {
      const mon = ++seq;
      if (titre.trim().length < 3) { zone.hidden = true; return; }
      try {
        const { candidates } = await api(`/rapprochement/proches?titre=${encodeURIComponent(titre)}`);
        if (mon !== seq) return; // une frappe plus récente a repris la main
        remplacer(zone, [h('p', { class: 'proche-entete' }, t('bandeau.proches')), h('ul', { class: 'props' }, candidates.map((c) => carteProche(c, completer)))]);
        zone.hidden = !candidates.length;
      } catch { zone.hidden = true; }
    }, DELAI_PROCHES);
  };
  return { zone, maj };
}

// « ＋ Nouveau projet… » : le projet qui manque naît sous un conteneur choisi, la tâche s'y range.
const NOUVEAU = '\u0001nouveau-groupe'; // jamais un id de conteneur
function champsGroupe(options) {
  const nom = champ({ nom: 'groupe_nom', label: t('bandeau.groupe_nom'), requis: true }, 'g');
  const dans = champ({ nom: 'groupe_dans', label: t('bandeau.groupe_dans'), type: 'select', requis: true,
    options: [{ valeur: '', libelle: t('bandeau.groupe_choisir') }, ...options] }, 'g');
  const ctrls = [nom, dans].map((c) => c.querySelector('input, select'));
  const zone = h('div', { class: 'nouveau-groupe', 'data-id': 'nouveau-groupe', hidden: true }, nom, dans);
  const montrer = (oui) => { zone.hidden = !oui; for (const c of ctrls) c.required = oui; }; // requis seulement visibles
  montrer(false);
  return { zone, montrer, valeurs: () => ({ nom: ctrls[0].value.trim(), dans: ctrls[1].value }) };
}

// `pre` : valeurs de départ { titre, description, conteneur } (barre de chat d'une note, emplacement pré-choisi de l'arbre)
// et `parent` {id, titre} pour une sous-tâche (« ＋ Nouvelle tâche » de l'arbre) ; rien n'est créé avant « Créer ».
// Rend {id, lancer} de la tâche créée (ou complétée), sinon rien ; `differer` : « Lancer » est rendu à l'appelant au lieu de partir
// avec la création (page Email : le mail se range avant le premier tour, INV-MAIL-2) ; `encart` : texte rappelant le mail joint, en tête du dialogue.
export async function nouvelleTache(pre = {}) {
  const parent = pre.parent || null;
  let conteneurs = [];
  const galerie = galerieModeles((m, carte) => {  // un modèle pré-remplit, rien n'est créé (INV-MODELES-1)
    const f = carte.closest('form');
    f.elements.titre.value = m.titre;
    f.elements.description.value = m.mission;
    f.elements.description.focus();
  });
  try { conteneurs = await api('/conteneurs'); } catch (e) { erreur(e.message); }
  const lieux = conteneurs.map((c) => ({ valeur: c.id, libelle: c.titre, groupe: [c.casquette, simple() ? '' : c.operation].filter(Boolean).join(' › ') }));
  const options = [{ valeur: '', libelle: t('bandeau.arrivee') }, ...lieux, { valeur: NOUVEAU, libelle: t('bandeau.nouveau_groupe'), fin: true }];
  const groupe = champsGroupe(lieux);
  let complete = null; // tâche complétée à la place d'une création
  const completer = async (c, bouton) => {
    const form = bouton.closest('form');
    const titre = form.elements.titre.value.trim();
    const texte = [titre, form.elements.description?.value.trim()].filter(Boolean).join('\n\n');
    try {
      await post(`/rapprochement/taches/${encodeURIComponent(c.id)}/completer`, { texte, titre });
      complete = c.id;
      bouton.closest('dialog').close();
    } catch (e) { erreur(e.message); }
  };
  const proches = listeProches(completer);
  const v = await formulaire({
    titre: t('bandeau.nouvelle_titre'), valider: t('bandeau.creer'), corps: await galerie,
    texte: [pre.encart, [...parcourir(S.arbre)].some((x) => x.type === 'tache') ? '' : t('premiers-pas.avertissement')].filter(Boolean).join('\n\n') || undefined, // encart du mail joint ; première tâche : on dit ce que l'assistant pourra faire (D4)
    champs: [
      { nom: 'titre', label: t('bandeau.titre'), requis: true, valeur: pre.titre, sous: proches.zone, surSaisie: proches.maj },
      { nom: 'description', label: t('bandeau.description'), type: 'textarea', valeur: pre.description, aide: t('bandeau.description_aide') },
      parent ? { nom: 'sous', label: t('bandeau.sous_tache'), lecture: true, valeur: parent.titre }
        : { nom: 'conteneur', label: simple() ? t('bandeau.projet') : t('bandeau.emplacement'), type: 'select', options, valeur: pre.conteneur, sous: groupe.zone, surSaisie: (x) => groupe.montrer(x === NOUVEAU) },
      { nom: 'echeance', label: t('bandeau.echeance'), type: 'date' },
      { nom: 'priorite', label: t('bandeau.priorite'), type: 'select', options: [{ valeur: '', libelle: t('bandeau.aucune') }, ...PRIORITES.map(([valeur, libelle]) => ({ valeur, libelle }))] },
      { nom: 'lancer', label: t('bandeau.lancer'), type: 'checkbox' },
    ],
  });
  if (complete) { emit('recharger'); ouvrir(complete); return { id: complete, lancer: false }; }
  if (!v) return;
  try {
    const corps = { titre: v.titre.trim(), lancer: v.lancer && !pre.differer };
    if (v.description.trim()) corps.description = v.description.trim();
    if (parent) corps.parent = parent.id;
    else if (v.conteneur === NOUVEAU) corps.nouveau_groupe = groupe.valeurs();
    else if (v.conteneur) corps.conteneur = v.conteneur;
    if (v.echeance) corps.echeance = v.echeance;
    if (v.priorite) corps.priorite = v.priorite;
    let nt;
    try { nt = await post('/taches', corps); } catch (e) {
      if (e.statut !== 409 || !(e.corps?.candidates || e.corps?.rangement)) throw e;
      nt = e.corps.candidates ? await confirmerDoublon(corps, e.corps.candidates) : await dialogueRangement(corps, e.corps.rangement);
      if (!nt) return;
    }
    emit('recharger');
    ouvrir(nt.id);
    return { id: nt.id, lancer: v.lancer && !corps.lancer, description: corps.description || '' };
  } catch (e) { erreur(e.message); }
}

// Correspondance forte au moment de créer : refus doux, « Créer quand même » ou « Compléter celle-ci ».
async function confirmerDoublon(corps, candidates) {
  let complete = null;
  const completer = async (c, bouton) => {
    try {
      await post(`/rapprochement/taches/${encodeURIComponent(c.id)}/completer`, { texte: [corps.titre, corps.description].filter(Boolean).join('\n\n'), titre: corps.titre });
      complete = c.id;
      bouton.closest('dialog').close();
    } catch (e) { erreur(e.message); }
  };
  const ok = await formulaire({
    titre: t('bandeau.doublon_titre'), texte: t('bandeau.doublon_texte'), valider: t('bandeau.creer_quand_meme'),
    corps: h('ul', { class: 'props proches', 'data-id': 'doublon' }, candidates.map((c) => carteProche(c, completer))),
  });
  if (complete) return { id: complete };
  if (!ok) return null;
  try { return await post('/taches', { ...corps, forcer: true }); } catch (e) {
    if (e.statut !== 409 || !e.corps?.rangement) throw e;
    return dialogueRangement(corps, e.corps.rangement);
  }
}

const RYTHMES = { 'a-la-demande': t('bandeau.rythme_demande'), quotidien: t('bandeau.rythme_quotidien'), hebdomadaire: t('bandeau.rythme_hebdo') };
export async function chargerRevue() {
  if (!ouvert('jardinage')) return;
  try {
    const j = await api('/jardinage');
    const q = (iso) => (iso ? heure(iso) : t('bandeau.jamais'));
    $('#btn-revue').title = t('bandeau.revue_titre', { rythme: RYTHMES[j.rythme] || j.rythme, derniere: q(j.derniere), prochaine: j.prochaine ? heure(j.prochaine) : t('bandeau.aucune_planifiee') });
  } catch (e) { erreur(e.message); }
}
async function lancerRevue() {
  if (!confirm(t('bandeau.revue_confirmer'))) return; // lance un assistant IA : coût et quota dits avant (audit L3, A3)
  const b = $('#btn-revue');
  b.disabled = true;
  try {
    const { tache } = await post('/jardinage');
    emit('recharger');
    if (tache) ouvrir(tache);
  } catch (e) { erreur(e.message); }
  b.disabled = false;
  chargerRevue();
}

export function initBandeau() {
  $('#btn-revue').addEventListener('click', lancerRevue);
  chargerRevue();
  $('#marque').addEventListener('click', () => ouvrir(null));
  $('#btn-nouvelle').addEventListener('click', () => nouvelleTache());
  on('nouvelle', nouvelleTache);
  $('#btn-routine').addEventListener('click', () => nouvelleRoutine());
  $('#btn-chaines').addEventListener('click', () => ouvrirChaines());
  $('#btn-recent').addEventListener('click', () => ouvrirVue('etiquette', 'recent'));
  $('#btn-equipe').addEventListener('click', () => ouvrirVue('equipe'));
  $('#btn-reglages').addEventListener('click', () => ouvrirVue('reglages'));
  $('#btn-guide').addEventListener('click', () => ouvrirGuide());
  $('#btn-mail').addEventListener('click', () => ouvrirVue('mail'));
  props = deroulant({ bouton: $('#btn-props'), panneau: $('#panneau-props'), titre: t('apercus.propositions'),
    toutVoir: { libelle: t('apercus.tout_voir'), agir: () => ouvrirVue('decisions') }, remplir: dessinerPanneau });
  const rech = $('#recherche');
  initRecherche();
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) { e.preventDefault(); rech.focus(); rech.select(); }
  });
  on('etat', dessinerBandeau);
  on('filtre', dessinerBandeau);
  on('selection', dessinerBandeau);
  on('props', () => props.redessiner());
  setInterval(dessinerBandeau, 30000);
}
