// Rôle : volet droit — tâche sélectionnée (en-tête, actions, fiche, corps, conversation, saisie).
// Frontières : API HTTP + événements SSE relayés par app.js ; ne modifie jamais l'arbre lui-même.
import { h, libelleStatut, nomLisible, pastille, remplacer, ajouter as ajouterDom } from './dom.js';
import { rendreMd } from './md.js';
import { S, on, emit, erreur, ouvrir, ouvrirVue, ouvrirNote, ouvrirGraphe, noeudTache } from './store.js';
import { filVisible, simple } from './interface.js';
import { cheminVaultTache } from './ponts.js';
import { notesLiees } from './notes-liees.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { carteLiens } from './liens.js';
import { carteLignes, selecteurNature, enLigne } from './lignes.js';
import { pastilleLivrables } from './livrables.js';
import { carteRevues, solliciter } from './revues.js';
import { chargerHarnais, selecteurMoteur, libelleMoteur } from './moteur.js';
import { blocEconomie } from './economie.js';
import { selecteurApprendre } from './apprendre.js';
import { modifierMessage, blocVersions } from './modifier.js';
import { selecteurExecution, motifExecution } from './execution.js';
import { elMsg, rendreConversation, nbTours, evenementDirect, groupeDirect, etapesAffichees, memoriserEtapes } from './conversation.js';
import { deplacerVers } from './glisser.js';
import { promouvoir as promouvoirTache } from './transfo.js';
import { editeurTemps } from './temps.js';
import { titreEditable } from './renommer.js';
import { repereIA, surOccupees } from './verrou.js';
import { blocCodespace } from './codespace.js';
import { ligneVie } from './vigie.js';
import { bandeauIncident } from './incidents.js';
import { blocRoutine, convertirEnRoutine } from './routines.js';
import { blocChaine } from './chaines.js';
import { groupesStatut, ecrireStatut, INFO_VERROU } from './statut.js';
import { curseur, humain } from './executant.js';
import { deroulant } from './deroulant.js';
import { panneau, creerNotes } from './notes_tache.js';
import { t } from './langues.js';
import { voirResultat } from './resultat.js';
import { pastilleMain, phraseMain, boutonIA, envoyerIA } from './main.js';

let racine, id = null, tache = null, instantane = '', colle = true, ficheAbsente = false;
let direct = false; // un tour de cette tâche est en cours : le dernier tour de la conversation n'a pas encore de réponse finale
let deplies = new Set(); // tours dont les étapes ont été dépliées à la main (valable pour la tâche ouverte)
let choixMoteur = null; // {harnais, modele} choisis dans l'en-tête depuis le dernier message : repris par le prochain envoi
let r = {}; // références DOM de la tâche ouverte
const enc = encodeURIComponent;
const CLE_DETAILS = 'gb.detail-ouvert';
let detOuvert = (() => { try { return localStorage.getItem(CLE_DETAILS) === '1'; } catch { return false; } })();
// INV-DEROULANT-1 : « Détails » est un déroulant ; épinglé, il reste ouvert dans le flux et ce choix est mémorisé.
function epinglerDetails(v) {
  detOuvert = v;
  try { localStorage.setItem(CLE_DETAILS, v ? '1' : '0'); } catch { /* stockage indisponible : le choix vaut pour la séance */ }
}
const montrerDetails = () => r.der.ouvrir();
const actif = (tk) => tk && (tk.etat_execution === 'en_cours' || tk.etat_execution === 'en_file');

function squelette() {
  r = {};
  r.une = h('div', { class: 'd-une' });
  r.vie = h('div', { class: 'd-vie' });
  r.fiche = h('section', { class: 'fiche' });
  r.lignes = h('div', { class: 'liens f-lignes' });
  r.liens = h('div', { class: 'liens f-liens' });
  r.revues = h('div', { class: 'liens f-equipe' });
  r.corps = h('details', { class: 'corps' }, h('summary', null, t('detail.corps')), (r.corpsMd = h('div', { class: 'md' })));
  r.conv = h('div', { class: `conv${etapesAffichees() ? '' : ' masque'}` });
  r.conv.addEventListener('click', (e) => {
    const b = e.target.closest('.msg-modifier, .msg-repondre');
    if (b?.classList.contains('msg-repondre') && !b.dataset.suite) r.ta.focus(); // dernière réponse : le fil continue normalement
    else if (b) modifier(b);
  });
  r.etapes = h('button', { class: 'btn petit btn-etapes', type: 'button', 'aria-pressed': String(etapesAffichees()), onclick: basculerEtapes,
    title: t('detail.etapes_titre') }, h('span', { class: 'sw', 'aria-hidden': 'true' }), t('detail.etapes'));
  // INV-DETAIL-1 : une seule ligne d'en-tête ; tout le reste vit dans « Détails », replié par défaut, choix mémorisé.
  r.detMeta = h('div', { class: 'd-det-meta' });
  r.details = h('div', { class: 'd-details', 'data-id': 'details', id: 'details', hidden: true }, r.detMeta, r.vie, r.fiche, r.lignes, r.liens, r.revues, r.corps);
  r.bascule = h('button', { class: 'btn petit d-bascule', type: 'button', 'data-id': 'details-bascule', title: t('detail.details_titre') }, t('detail.details'));
  r.der = deroulant({ bouton: r.bascule, panneau: r.details, garder: true, epingle: detOuvert, surEpingle: epinglerDetails });
  r.tete = h('div', { class: 'd-tete' }, r.une, r.details);
  r.defile = h('div', { class: 'd-defile' }, h('div', { class: 'conv-tete' }, (r.convTitre = h('h3', { class: 'conv-titre' }, t('detail.echanges'))), r.etapes), r.conv);
  r.defile.addEventListener('scroll', () => { colle = r.defile.scrollHeight - r.defile.scrollTop - r.defile.clientHeight < 48; r.bas.hidden = colle; });
  r.bas = h('button', { class: 'btn petit retour-bas', type: 'button', hidden: true, onclick: () => descendre(true) }, t('detail.direct'));
  r.ta = h('textarea', { rows: 2, 'aria-label': t('detail.message_agent'), placeholder: t('detail.message_placeholder') });
  r.note = h('span', { class: 'note' });
  r.envoyer = h('button', { class: 'btn primaire', type: 'submit' }, t('detail.envoyer'));
  r.rappel = h('button', { class: 'rappel', type: 'button', onclick: () => { montrerDetails(); r.tete.querySelector('.moteur select')?.focus(); } });
  const form = h('form', { class: 'composer' }, h('div', { class: 'c-ligne' }, r.ta, h('div', { class: 'c-col' }, r.rappel, r.envoyer)), r.note);
  form.addEventListener('submit', (e) => { e.preventDefault(); envoyer(); });
  r.ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); envoyer(); } });
  // INV-EXECUTANT-2 : deux panneaux réductibles, côte à côte (empilés sur écran étroit), sans onglet.
  r.notes = creerNotes(() => rafraichir(), erreur);
  r.pConv = panneau('conv', t('detail.conversation'), h('div', { class: 'p-defile' }, r.defile, r.bas), form);
  r.pNotes = panneau('notes', t('detail.notes'), r.notes.el);
  remplacer(racine, h('div', { class: 'detail' }, r.tete, h('div', { class: 'd-zone' }, r.pConv, r.pNotes)));
}

function descendre(force) { if (force || colle) { r.defile.scrollTop = r.defile.scrollHeight; colle = true; r.bas.hidden = true; } }

async function agir(fn) { try { return await fn(); } catch (e) { erreur(e.message); } }
function appliquer(tk) { tache = tk; instantane = JSON.stringify(tk); dessiner(); emit('recharger'); }

const modeleDe = (tk) => tk.modele ?? tk.frontmatter?.modele ?? '';
const aValider = (tk) => tk.a_valider ?? (tk.statut === 'fait' && !!tk.session);

function selecteurStatut(tk) {
  const opt = (s) => h('option', { value: s, selected: s === tk.statut ? true : null }, s === tk.statut && aValider(tk) ? t('statut.a_valider') : libelleStatut(s));
  return h('select', { 'aria-label': t('detail.statut'), disabled: tk.statut_verrouille ? true : null, title: tk.statut_verrouille ? INFO_VERROU : null,
    onchange: async (e) => {
      const nt = await agir(() => ecrireStatut(id, e.target.value));
      if (nt) appliquer(nt); else e.target.value = tache.statut;
    } },
  groupesStatut(tk.statut).map((g) => (g.titre ? h('optgroup', { label: g.titre }, g.statuts.map(opt)) : g.statuts.map(opt))));
}

// Fil d'Ariane cliquable : tâche = l'ouvrir ; casquette, opération, conteneur = cascade limitée à ce sous-arbre.
// Repli si le serveur n'envoie pas `fil` : les titres de `fil_ariane` sont résolus dans l'arbre en mémoire, sinon texte simple.
const normT = (s) => (s || '').normalize('NFD').replace(/\p{M}/g, '').toLowerCase().trim();
function segmentsFil(tk) {
  const aller = (type, nid) => (type === 'tache' ? ouvrir(nid) : ouvrirVue('cascade', `${type}:${nid}`));
  const lien = (txt, type, nid) => h('span', null, h('button', { class: 'crumb', type: 'button', title: t('detail.aller', { titre: txt }), onclick: () => aller(type, nid) }, txt));
  if (tk.fil?.length) return filVisible(tk.fil).filter((s) => s.titre !== '?' && !(simple() && s.titre === '_meta')).map((s) => lien(nomLisible(s.titre), s.type, s.id));
  let niveau = S.arbre;
  return (tk.fil_ariane || []).filter((txt) => txt !== '?' && !(simple() && txt === '_meta')).map((txt) => {
    const q = normT(txt);
    const n = niveau.find((x) => normT(x.titre) === q || (x.type === 'casquette' && normT(x.titre).startsWith(q)));
    niveau = n?.enfants || [];
    return n ? lien(nomLisible(txt), n.type, n.id) : h('span', null, nomLisible(txt));
  });
}

// « Rattachée à : <mère ou conteneur> » : dernier ancêtre du fil ; « Changer… » rouvre le dialogue « Déplacer vers… » (même geste que dans l'arbre).
function rattachement(tk, b) {
  const a = tk.fil?.at(-1);
  const nom = a ? h('button', { class: 'crumb', type: 'button', title: t('detail.aller', { titre: a.titre }), onclick: () => (a.type === 'tache' ? ouvrir(a.id) : ouvrirVue('cascade', `${a.type}:${a.id}`)) }, nomLisible(a.titre))
    : h('span', { class: 'crumb-txt' }, nomLisible((tk.fil_ariane || []).at(-1) || '—'));
  const noeud = noeudTache(tk.id);
  const mobile = noeud ? noeud.deplacable !== false : true;
  return h('div', { class: 'd-rattache' }, t('detail.rattachee'), nom, a ? h('span', { class: 'badge-type' }, a.type === 'tache' ? t('detail.tache_mere') : t('detail.projet')) : null,
    b(t('detail.changer'), () => deplacerVers(noeud || { id: tk.id, type: 'tache', titre: tk.titre, deplacable: true, enfants: [] }),
      { off: !mobile, titre: mobile ? t('detail.rattacher_titre') : t('detail.deplacement_impossible') }));
}

// INV-CONTROLE-1 : verdict du contrôle requis à côté du statut ; rien sans contrôle déclaré.
function controleRepere(c) {
  if (!c) return null;
  const v = c.verdict;
  const [cls, txt] = !v ? ['manque', t('detail.controle_non_lance')] : v.verdict !== 'reussi' ? ['echoue', t('detail.controle_echoue')]
    : v.perime ? ['perime', t('detail.controle_perime')] : v.perime === null ? ['', t('detail.controle_reussi_nr')] : ['reussi', t('detail.controle_reussi')];
  const titre = [t('detail.controle_requis', { par: c.declare_par, commande: c.commande }), v && `${v.date.replace('T', ' ')} · ${v.reference || t('detail.etat_non_ref')}`,
    v && v.cause, v && v.journal && t('detail.journal', { journal: v.journal })].filter(Boolean).join('\n');
  return h('span', { class: `controle ${cls}`, title: titre }, txt);
}

function dessinerTete() {
  const tk = tache;
  const etat = tk.attente_prerequis?.length ? t('detail.attente_de', { liste: tk.attente_prerequis.map((p) => p.titre).join(', ') }) // INV-ORDO-1
    : tk.rang_poste ? t('detail.poste_rang', { rang: tk.rang_poste }) // INV-POSTE-1 : file du poste
    : tk.attente_poste ? t('detail.poste_reserve', { titre: tk.attente_poste.titre })
    : tk.etat_execution === 'en_file' && tk.rang_file ? t('detail.en_file_rang', { libelle: tk.rang_file.libelle, motif: tk.rang_file.motif }) // INV-ORDO-2
    : tk.etat_execution === 'en_pause' ? (tk.pause || t('detail.pause_quota'))
    : { en_cours: t('detail.tour_en_cours'), en_file: t(tk.reprise_auto ? 'detail.reprise_auto' : 'detail.en_file'), interrompu: t(tk.reprise_auto ? 'detail.reprise_auto' : 'detail.tour_interrompu'), attente_reseau: t('detail.attente_reseau') }[tk.etat_execution];
  const b = (txt, f, o = {}) => h('button', { class: `btn petit${o.cls ? ' ' + o.cls : ''}`, type: 'button', onclick: f, disabled: o.off ? true : null, title: o.titre || null }, txt);
  // Alertes : la plus importante en tête de ligne, les autres en compteur ; toutes se lisent dans « Détails » (INV-DETAIL-1).
  const alertes = [tk.incident && tk.incident.libelle, tk.pause_ram && t('detail.pause_ram'), tk.controle?.verdict && tk.controle.verdict.verdict !== 'reussi' && t('detail.controle_echoue')].filter(Boolean);
  const routine = tk.frontmatter?.nature === 'routine';
  remplacer(r.une,
    titreEditable(tk, appliquer, repereIA(tk.id)), // INV-RENOMMER-1
    ...(routine ? [] : [pastille(tk.statut), selecteurStatut(tk)]), // INV-ROUTINE-5 : état au lieu du statut
    tk.main ? pastilleMain(tk.main, `etat ${tk.etat_execution}`, () => envoyerIA(tk.id, tk.main, () => rafraichir())) : etat && !tk.pause_ram ? h('span', { class: `etat ${tk.etat_execution}`, title: etat }, tk.etat_execution === 'en_cours' ? h('span', { class: 'tourne' }) : null, etat) : null, // INV-MAIN-1 : une seule pastille d'état
    phraseMain(tk.main), boutonIA(tk.id, tk.main, () => rafraichir()), // INV-MAIN-5
    alertes.length ? h('button', { class: 'd-alerte', type: 'button', 'data-id': 'alerte', title: alertes.join('\n'), onclick: montrerDetails },
      h('span', { class: 'd-alerte-t' }, alertes[0]), alertes.length > 1 ? h('span', { class: 'd-alerte-n' }, t('detail.alertes_plus', { n: alertes.length - 1 })) : null) : null,
    aValider(tk) ? h('span', { class: 'a-valider', role: 'status', title: t('detail.a_valider') }, b(t('detail.valider'), valider, { cls: 'primaire' }), b(t('detail.renvoyer_btn'), renvoyer)) : null,
    pastilleLivrables(tk), // INV-LIVRABLES-1 : une pastille ; le volet porte le reste
    b(t('resultat.bouton'), () => voirResultat(tk.id), { cls: `${aValider(tk) ? '' : 'primaire'} d-resultat`, titre: t('resultat.aide') }), // au téléphone : dans « Détails » (INV-REACTIVITE-1)
    tk.pause_ram ? b(t('detail.reprendre_maintenant'), reprendreRam, { cls: 'primaire', titre: t('detail.reprendre_ram_titre') }) : null,
    tk.etat_execution === 'en_pause' ? b(t('detail.reprendre_maintenant'), reprendreMaintenant, { cls: 'primaire', titre: t('detail.reprendre_quota_titre') }) : null,
    actif(tk) || tk.etat_execution === 'en_pause' ? b(t('detail.arreter'), arreter, { cls: 'danger' }) : null,
    tk.etat_execution === 'interrompu' ? b(t('detail.relancer'), relancer, { cls: 'primaire', titre: t('detail.relancer_titre') }) : null,
    r.bascule);
  remplacer(r.detMeta,
    h('nav', { class: 'fil', 'aria-label': t('detail.fil') }, segmentsFil(tk)),
    h('div', { class: 'd-resultat-det' }, b(t('resultat.bouton'), () => voirResultat(tk.id), { cls: 'primaire', titre: t('resultat.aide') })),
    curseur(tk, (x) => (x ? appliquer(x) : rafraichir()), erreur), // INV-EXECUTANT-1
    rattachement(tk, b),
    routine ? blocRoutine(tk.id, () => { emit('recharger'); rafraichir(); }) : null, // INV-ROUTINE-5
    tk.frontmatter?.chaine || tk.frontmatter?.chaine_phase ? blocChaine(tk.id, () => { emit('recharger'); rafraichir(); }) : null, // INV-CHAINE-1
    h('div', { class: 'd-meta' },
      tk.statut_verrouille ? b(t('detail.reprendre_main'), reprendre, { cls: 'verrou', titre: t('detail.reprendre_main_titre') }) : null,
      controleRepere(tk.controle),
      motifExecution(tk.execution), // INV-REGROUPE-1
      (tk.enfants?.length && tk.execution) ? selecteurExecution(tk.id, tk.execution, () => rafraichir()) : null,
      tk.pause_ram ? h('span', { class: 'etat pause-ram', 'data-id': 'pause-ram', title: t('detail.pause_ram_titre') }, t('detail.pause_ram')) : null,
      editeurTemps(tk, appliquer),
      selecteurMoteur(tk.harnais || '', modeleDe(tk), changerMoteur),
      selecteurApprendre(tk, appliquer),  // INV-APPRENDRE-1
      selecteurNature(tk, appliquer),  // INV-NATURE-1
      tk.fil?.length > 1 ? b(t('lignes.en_ligne'), async () => { if (await enLigne(tk)) { emit('recharger'); rafraichir(); } }, { titre: t('lignes.en_ligne_titre') }) : null,
      blocEconomie(tk, (vers) => changerMoteur(vers, '')),  // INV-ECO-1 : bascule acceptée d'un geste
      blocCodespace(tk, appliquer),
      h('span', { class: 'session' }, tk.session ? t('detail.session', { id: tk.session.slice(0, 8) }) : t('detail.sans_session')),
      tk.dossier_travail ? h('span', { class: 'session', title: tk.dossier_travail_origine }, t('detail.dossier', { dossier: tk.dossier_travail })) : null),
    notesLiees(cheminVaultTache(tk)),
    h('div', { class: 'd-actions' },
      b(t('detail.ouvrir_note'), () => ouvrirNote(cheminVaultTache(tk)), { cls: 'f-notes', titre: t('detail.ouvrir_note_titre') }),
      b(t('detail.graphe'), () => ouvrirGraphe(tk.id), { cls: 'f-notes', titre: t('detail.graphe_titre') }),
      b(t('detail.solliciter'), demanderAvis, { cls: 'f-equipe', titre: t('detail.solliciter_titre') }), b(t('detail.deriver'), deriver), routine ? null : b(t('detail.routine'), async () => { if (await convertirEnRoutine(tk.id)) { emit('recharger'); rafraichir(); } }, { titre: t('detail.routine_titre') }), b(t('detail.promouvoir'), promouvoir, { cls: 'f-transformations', titre: t('detail.promouvoir_titre') }),
      b(t('detail.console'), consoleGB, { titre: t('detail.console_titre') }),
      b(t('detail.natif'), natif, { titre: t('detail.natif_titre') })));
  r.note.textContent = (S.etat.occupees || {})[id]?.terminal // INV-NATIF-1
    ? t('detail.terminal')
    : actif(tk) ? t('detail.tour_en_cours_msg') : '';
  r.rappel.textContent = choixMoteur ? t('detail.moteur_modifie', { moteur: libelleMoteur(tk.harnais, modeleDe(tk)) }) : `⚙ ${libelleMoteur(tk.harnais, modeleDe(tk))}`;
  r.rappel.title = t('detail.moteur_titre');
  majVie();
}

// INV-VIGIE-1, INV-VIGIE-2 : l'état global (rafraîchi à chaque signe de vie) prime sur la tâche lue à l'ouverture.
function majVie() {
  if (!r.vie || !tache) return;
  const tour = (S.etat.tours || []).find((x) => x.tache === id), f = (S.etat.file || []).find((x) => x.tache === id);
  const signe = tour ? tour.signe : tache.etat_execution === 'en_cours' ? tache.signe : null;
  remplacer(r.vie, ligneVie(id, signe, f ? f.raison : tache.raison_attente),
    tour ? null : bandeauIncident(tache.incident)); // INV-INCIDENT-1 : cause du dernier échec ou arrêt
}

const NON_INDIQUE = t('detail.non_indique');
function dessinerFiche() {
  const f = tache.fiche || {};
  const champ = (l, v) => h('div', { class: 'f-champ' }, h('dt', null, l), rendreMd(h('dd', { class: 'md' }), v || '—'));
  const st = f.sous_taches || [];
  remplacer(r.fiche, h('h3', null, t('detail.fiche')),
    ficheAbsente ? h('p', { class: 'note' }, t('detail.fiche_absente')) : '',
    h('dl', { class: 'f-grille' }, champ(t('detail.f_fait'), f.fait), champ(t('detail.f_resultat'), f.resultat || NON_INDIQUE), champ(t('detail.f_essai'), f.essai || NON_INDIQUE), champ(t('detail.f_situation'), f.situation), champ(t('detail.f_reste'), f.reste), champ(t('detail.f_prochain'), f.prochain_pas)),
    f.retenir ? h('div', { class: 'f-retenir', 'data-id': 'fiche-retenir' }, h('h4', null, t('detail.retenir')), h('ul', null, f.retenir.split(/\s*;\s*/).filter(Boolean).map((p) => h('li', null, p)))) : '',
    st.length ? h('div', { class: 'f-st' }, h('h4', null, t('detail.sous_taches')),
      h('ul', null, st.map((s) => h('li', { class: s.fait ? 'fait' : '' },
        h('input', { type: 'checkbox', checked: s.fait ? true : null, disabled: true, 'aria-label': s.fait ? t('detail.faite') : t('detail.a_faire') }),
        rendreMd(h('span', { class: 'md' }), s.texte),
        h('button', { class: 'btn petit', type: 'button', title: t('detail.ticket_titre'), onclick: () => ticket(s.texte) }, t('detail.ticket')))))) : '');
}
function dessiner() {
  dessinerTete(); dessinerFiche();
  remplacer(r.lignes, carteLignes(tache, () => rafraichir()));
  remplacer(r.liens, carteLiens(tache, appliquer));
  remplacer(r.revues, carteRevues(tache));
  rendreMd(r.corpsMd, tache.corps || '');
  r.corps.hidden = !(tache.corps || '').trim();
  r.notes.dessiner(tache);
  r.pNotes.compte((tache.notes || []).length);
  modeMoi();
}
// INV-EXECUTANT-1 : tâche « Moi » → conversation lisible mais inactive (aucun tour d'agent) ; le travail s'écrit dans les Notes.
function modeMoi() {
  const moi = humain(tache);
  r.pConv.classList.toggle('inactive', moi);
  r.ta.disabled = moi; r.envoyer.disabled = moi;
  r.ta.placeholder = moi ? t('detail.inactive') : t('detail.message_placeholder');
}

// --- conversation ---
// Bascule « Étapes » : une classe CSS, sans nouveau rendu. Ancre = un message de l'utilisateur (sa hauteur ne change jamais à la bascule) :
// le premier qui touche la zone visible, sinon le dernier au-dessus ; sa position à l'écran est rétablie après le changement.
function basculerEtapes() {
  const v = !etapesAffichees();
  memoriserEtapes(v);
  const d = r.defile, haut = d.getBoundingClientRect().top, bas = d.getBoundingClientRect().bottom;
  const us = [...r.conv.querySelectorAll('.msg.user')];
  const ancre = us.find((x) => { const b = x.getBoundingClientRect(); return b.bottom > haut && b.top < bas; }) ?? us.findLast((x) => x.getBoundingClientRect().bottom <= haut);
  const avant = ancre?.getBoundingClientRect().top;
  r.conv.classList.toggle('masque', !v);
  r.etapes.setAttribute('aria-pressed', String(v));
  if (colle) descendre(true);
  else if (ancre) d.scrollTop += ancre.getBoundingClientRect().top - avant;
}
// Ouverture (INV-DISCUSSION-1) : le fil est demandé dès l'ouverture, en parallèle des moteurs et de la fiche, puis les derniers
// échanges s'affichent d'abord ; le début de l'historique se dessine ensuite, sans bouger ce qu'on lit.
const lireConv = (i) => api(`/taches/${enc(i)}/conversation?limite=200`);
let prechargee = null; // { id, p } : fil lancé par ouvrirDetail
const PREMIERS = 30; // messages rendus avant le reste de l'historique
function afficherConv(l, initial) {
  const contenu = (x, n0 = 0) => (x.length || direct ? rendreConversation(x, direct, deplies, n0) : h('p', { class: 'vide' }, t('detail.aucun_echange')));
  let k = l.length - PREMIERS;
  while (initial && k > 0 && l[k].role !== 'utilisateur' && l[k].role !== 'systeme') k--; // coupe au début d'un échange
  if (!initial || k <= 0) { remplacer(r.conv, contenu(l)); return; }
  const debut = l.slice(0, k), conv = r.conv, courant = id;
  remplacer(conv, contenu(l.slice(k), nbTours(debut)));
  descendre(true);
  setTimeout(() => {
    if (r.conv !== conv || courant !== id) return;
    const d = r.defile, h0 = d.scrollHeight, t0 = d.scrollTop, noeuds = rendreConversation(debut, false, deplies);
    const v = conv.querySelector(':scope > .modif-versions');
    if (v) v.after(...noeuds); else conv.prepend(...noeuds);
    d.scrollTop = t0 + d.scrollHeight - h0; // le défilement est géré à la main (lot7.css) : on compense l'ajout au-dessus
  }, 0);
}
async function chargerConv(initial) {
  const courant = id;
  const pre = initial && prechargee?.id === courant ? prechargee.p : null;
  prechargee = null;
  const l = (pre && await pre) || await agir(() => lireConv(id));
  if (!l || courant !== id) return;
  const avait = colle;
  afficherConv(l, initial);
  if (initial || avait) descendre(true); // le dernier échange d'abord : la fiche vit derrière « Détails »
  const versions = await blocVersions(courant); // INV-RETOUR-2 : la fin retirée reste consultable
  if (versions && courant === id) { r.conv.querySelector(':scope > .modif-versions')?.remove(); r.conv.prepend(versions); } // deux chargements concurrents : un seul bloc
  if (initial || avait) descendre(true);
}
function ajouter(el, avant = null) {
  r.conv.querySelector('.vide')?.remove();
  if (avant) avant.before(el); else ajouterDom(r.conv, el);
  if (colle) descendre(true); else r.bas.hidden = false;
}
// Le serveur et les événements peuvent se contredire un instant : l'état de la dernière `tache` lue fait foi pour la ligne d'activité.
function accorderDirect() {
  const en = tache?.etat_execution === 'en_cours';
  if (en === direct) return;
  direct = en;
  if (r.conv) chargerConv(false);
}
function evenement(e) {
  if (!r.conv || e.tache !== id) return;
  if (e.type === 'tour_texte' || e.type === 'tour_outil') {
    direct = true;
    evenementDirect(r.conv, e);
    if (colle) descendre(true); else r.bas.hidden = false;
  } else if (e.type === 'revue' || e.type === 'controle' || e.type === 'pause' || e.type === 'incident') { rafraichir(); } else if (e.type === 'natif_fin') { rafraichir(); chargerConv(false); } else if (e.type === 'remontee') { chargerConv(false); } else if (e.type === 'tour_debut') {
    ficheAbsente = false; direct = true; groupeDirect(r.conv);
    if (colle) descendre(true);
    rafraichir(); chargerConv(false); // le message du tour s'affiche dès son début, avant tout transcript
  } else if (e.type === 'tour_fin') {
    ficheAbsente = !!e.fiche_absente; direct = false;
    if (tache) dessinerFiche();
    rafraichir(); chargerConv(false);
  }
}

// --- actions ---
// INV-RETOUR-1 : « Modifier » un message envoyé (l'ancien texte est relu dans la conversation affichée), ou « Répondre à partir d'ici »
// sur une réponse de l'IA : c'est modifier le message qui la suit, en partant d'une saisie vide.
async function modifier(b) {
  const l = await agir(() => api(`/taches/${enc(id)}/conversation?limite=200`));
  const repondre = b.classList.contains('msg-repondre'), tour = repondre ? b.dataset.suite : b.dataset.tour;
  const m = l?.find((x) => x.tour === tour);
  if (!m) return;
  const res = await agir(() => modifierMessage(id, m.tour, repondre ? '' : m.texte, repondre));
  if (res) { rafraichir(); chargerConv(false); }
}
async function envoyer() {
  const texte = r.ta.value.trim();
  if (!texte) return;
  if (humain(tache)) return; // INV-EXECUTANT-1 : aucun message à l'agent d'une tâche « Moi »
  r.envoyer.disabled = true;
  const corps = { texte, ...(choixMoteur || {}) }; // harnais/modèle changés dans l'en-tête partent avec le message
  const etaitActif = actif(tache);
  const res = await agir(() => post(`/taches/${enc(id)}/messages`, corps));
  r.envoyer.disabled = false;
  if (!res) return;
  r.ta.value = ''; choixMoteur = null;
  // Le tour que ce message déclenche peut avoir ouvert son groupe en direct avant la réponse HTTP : le message passe devant.
  ajouter(elMsg({ role: 'utilisateur', texte, outils: [], horodatage: new Date().toISOString() }), etaitActif ? null : r.conv.querySelector(':scope > .tour-c.live'));
  if (tache) { tache.etat_execution = res.etat_execution; instantane = ''; dessinerTete(); }
  if (res.etat_execution === 'en_cours') { direct = true; groupeDirect(r.conv); if (colle) descendre(true); }
  emit('recharger');
}
async function deriver() {
  const v = await formulaire({
    titre: t('detail.deriver_titre'), valider: t('detail.deriver'),
    champs: [
      { nom: 'titre', label: t('detail.titre'), requis: true },
      { nom: 'lien', label: t('detail.lien'), type: 'radio', valeur: 'enfant', options: [{ valeur: 'enfant', libelle: t('detail.enfant') }, { valeur: 'soeur', libelle: t('detail.soeur') }] },
      { nom: 'avec_fil', label: tache.session ? t('detail.garder_fil') : t('detail.garder_fil_aucune'), type: 'checkbox', valeur: !!tache.session, desactive: !tache.session },
      { nom: 'message', label: t('detail.premier_message'), type: 'textarea', lignes: 3 },
    ],
  });
  if (!v) return;
  const corps = { titre: v.titre.trim(), lien: v.lien, avec_fil: !!tache.session && v.avec_fil };
  if (v.message.trim()) corps.message = v.message.trim();
  const tk = await agir(() => post(`/taches/${enc(id)}/deriver`, corps));
  if (tk) { emit('recharger'); ouvrir(tk.id); }
}
async function ticket(texte) {
  const tk = await agir(() => post(`/taches/${enc(id)}/deriver`, { titre: texte, lien: 'enfant', avec_fil: !!tache.session }));
  if (tk) emit('recharger');
}
async function promouvoir() {
  const res = await agir(() => promouvoirTache(tache));
  if (!res) return;
  appliquer(res.tache); // la tâche reste ouverte : son fil d'Ariane montre le nouveau projet
  accorderDirect();
  chargerConv(false); // le mandat de découpage vient d'être soumis à la conversation
}
async function consoleGB() { const res = await agir(() => post(`/taches/${enc(id)}/console`)); if (res) erreur(t('detail.console_ouverte'), 'info'); }
async function natif() { const res = await agir(() => post(`/taches/${enc(id)}/natif`)); if (res) { erreur(t('detail.natif_ouvert', { harnais: res.harnais }), 'info'); rafraichir(); } }
async function reprendreMaintenant() { const res = await agir(() => post(`/taches/${enc(id)}/reprise`)); if (res) rafraichir(); }
async function arreter() { const res = await agir(() => post(`/taches/${enc(id)}/arret`)); if (res) rafraichir(); }
async function reprendreRam() { const res = await agir(() => post(`/taches/${enc(id)}/reprendre-ram`)); if (res) rafraichir(); }
async function relancer() { const res = await agir(() => post(`/taches/${enc(id)}/relancer`)); if (res) rafraichir(); }
// Réponse attendue : une Tache ; sinon on recharge (le contrat ne précise pas toujours le corps).
async function appliquerOuRecharger(res) {
  if (res?.id === id) appliquer(res); else { instantane = ''; await rafraichir(); emit('recharger'); }
}
async function geste(chemin, corps) {
  try { await appliquerOuRecharger(await post(`/taches/${enc(id)}/${chemin}`, corps)); return true; } catch (e) { erreur(e.message); return false; }
}
const valider = () => geste('valider');
async function renvoyer() {
  const v = await formulaire({ titre: t('detail.renvoyer_agent'), valider: t('detail.renvoyer'), texte: t('detail.renvoyer_texte'),
    champs: [{ nom: 'attendu', label: t('detail.attendu'), type: 'textarea', lignes: 2, aide: t('detail.attendu_aide') },
             { nom: 'texte', label: t('detail.observe'), type: 'textarea', lignes: 4, requis: true }] });
  if (!v) return;
  const attendu = (v.attendu || '').trim();
  await geste('renvoyer', { texte: attendu ? [t('detail.anomalie'), t('detail.msg_attendu', { x: attendu }), t('detail.msg_observe', { x: v.texte.trim() })].join('\n') : v.texte.trim() });
}
const demanderAvis = () => solliciter(tache);
async function reprendre() {
  const v = await formulaire({ titre: t('detail.reprendre_main'), valider: t('detail.reprendre_main'),
    texte: t('detail.reprendre_texte') });
  if (v) await geste('liberer');
}
async function changerMoteur(harnais, modele) {
  choixMoteur = { harnais, modele };
  if (!(await geste('moteur', { harnais, modele }))) { choixMoteur = null; dessinerTete(); }
}

// --- cycle de vie ---
export function initDetail(el) {
  racine = el;
  surOccupees(() => { if (tache && r.tete?.isConnected) dessinerTete(); });
  on('etat', majVie);
  setInterval(majVie, 15000); // « il y a N s » vieillit même sans événement
  on('arbre', () => rafraichir()); // un geste d'arbre (ici ou ailleurs) a pu changer le rattachement de la tâche ouverte, même absente de l'arbre filtré
  on('message-envoye', (m) => { if (m.tache === id && r.conv) ajouter(elMsg({ role: 'utilisateur', texte: m.texte, outils: [], horodatage: new Date().toISOString() })); });
}
export async function ouvrirDetail(nouvelId) {
  id = nouvelId; tache = null; instantane = ''; colle = true; ficheAbsente = false; choixMoteur = null; direct = false; deplies = new Set();
  squelette();
  remplacer(r.une, h('p', { class: 'vide' }, t('detail.chargement')));
  prechargee = { id, p: lireConv(id).catch(() => null) };
  await agir(chargerHarnais); // liste des moteurs avant le premier dessin de l'en-tête
  instantane = ''; // un rafraîchissement parti pendant le chargement a pu dessiner sans la liste
  await rafraichir(true);
}
export const tacheOuverte = () => id;
export async function rafraichir(initial = false) {
  const courant = id;
  if (!courant) return;
  let tk;
  // Une tâche quittée entre-temps (réduite, archivée, déplacée) ne doit pas lever d'erreur à l'écran.
  try { tk = await api(`/taches/${enc(courant)}`); } catch (e) { if (courant === id) erreur(e.message); return; }
  if (!tk || courant !== id) return;
  const j = JSON.stringify(tk);
  if (j === instantane && !initial) return;
  instantane = j; tache = tk;
  dessiner();
  if (initial) { direct = tk.etat_execution === 'en_cours'; await chargerConv(true); } else accorderDirect();
}
export const evtDetail = evenement;
