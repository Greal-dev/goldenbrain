// Rôle : point d'entrée — chargements, flux SSE, bannière d'erreurs, aiguillage du volet droit.
// Frontières : orchestre les modules ; aucune logique d'affichage propre.
import { t, traduireDom } from './langues.js';
import { $ } from './dom.js';

traduireDom();  // INV-LANGUE-1 : textes du HTML statique (data-t*) avant tout rendu
import { api, ouvrirFlux, MSG_PERIME, MSG_ANNULE } from './api.js';
import { S, on, emit, erreur, ouvrir, ouvrirVue, ouvrirNote, ouvrirRecherche, ouvrirGraphe, fixerOnglet } from './store.js';
import { dessinerGraphe } from './graphe.js';
import { initArbre, dessiner as dessinerArbre } from './arbre.js';
import { initBandeau, chargerRevue } from './bandeau.js';
import { initIncidents } from './incidents.js';
import { initDetail, ouvrirDetail, rafraichir, evtDetail, tacheOuverte } from './detail.js';
import { dessinerCascade, etatCascade, initCascade } from './cascade.js';
import { dessinerEquipe } from './equipe.js';
import { dessinerReglages, etatReglages, fixerAncreReglages, hashReglages } from './reglages.js';
import { chargerInterface, ouvert, simple } from './interface.js';
import { dessinerAujourdhui } from './aujourdhui.js';
import { dessinerCompagnon } from './compagnon.js';
import { dessinerTravail } from './travail.js';
import { dessinerTravaux, actualiserTravaux } from './travaux.js';
import { dessinerDecisions } from './decisions.js';
import { dessinerGuide, hashGuide, fixerAncre } from './guide.js';
import { initNotes, evtNote as evtNoteArbre, actualiser as actualiserNotes } from './notes.js';
import { initNoteVue, dessinerNote, evtNote as evtNoteVue } from './note-vue.js';
import { dessinerResultats } from './resultats.js';
import { fixerTerme } from './recherche.js';
import { initPonts } from './ponts.js';
import { creerDepuisLien } from './note-gestes.js';
import { initAlignement, rafraichirEcarts } from './alignement.js';
import { initVersion } from './version.js';
import { initMajAuto } from './maj-auto.js';
import { initMaj } from './maj.js';
import { initEtoile } from './etoile.js';
import { evtTransfo } from './transfo.js';
import { recharger as rechargerSimultanes } from './simultanes.js';
import { recharger as rechargerCompactage } from './compactage.js';
import { recharger as rechargerExecuteurs } from './executeurs.js';
import { initAccueil } from './accueil.js';
import { initPremiersPas } from './premiers-pas.js';
import { initCerveau } from './cerveau.js';
import { initEconomie, recharger as rechargerEconomie } from './economie.js';
import { initTelephone } from './telephone.js';
import { initDiscussion } from './discussion.js';
import { initManager, rechargerManager, evtManager, evtTourManager } from './manager.js';

const droit = () => $('#volet-droit');
const rapporter = (fn) => async () => { try { await fn(); } catch (e) { erreur(e.message); } };

const chargerArbre = rapporter(async () => {
  S.arbre = (await api(`/arbre?toutes=${S.toutes ? 1 : 0}`)).noeuds;
  S.arbreCharge = true;
  emit('arbre');
});
const chargerEtat = rapporter(async () => { S.etat = await api('/etat'); emit('etat'); });
const chargerProps = rapporter(async () => { S.props = await api('/propositions'); emit('props'); });

let minuteurArbre = 0;
// INV-REACTIVITE-1 : un événement qui ne concerne pas la tâche ouverte (autre tâche, ou « arbre » seul) ne recharge que l'arbre et l'état ; la tâche ouverte
// ne se relit que si sa propre ligne de l'arbre a changé. Ni propositions ni manager (leurs événements propres s'en chargent).
let autres = true;
const signe = (id) => JSON.stringify(S.arbre?.find((n) => n.id === id) ?? null);
function planifier(tache = null, arbreSeul = false) {
  const ailleurs = arbreSeul || (!!tache && tache !== tacheOuverte());
  autres = autres && !!ailleurs;
  clearTimeout(minuteurArbre);
  minuteurArbre = setTimeout(async () => {
    const seul = autres; autres = true;
    const ouverte = tacheOuverte(), avant = signe(ouverte);
    if (!seul) { chargerArbre(); chargerEtat(); chargerProps(); rafraichir(); rechargerManager(); return; }
    chargerEtat();
    await chargerArbre();
    if (ouverte && ouverte === tacheOuverte() && signe(ouverte) !== avant) rafraichir();
  }, 300);
}
setInterval(chargerArbre, 60000); // la pastille « intégration en retard » apparaît et disparaît sans geste (INV-INTEG-1)
function toutRecharger() { chargerArbre(); chargerEtat(); chargerProps(); rafraichir(); }

function dernierLigne(texte, type) {
  const l = String(texte || '').split('\n').filter((x) => x.trim()).at(-1) || '';
  return type === 'tour_outil' ? `› ${l}` : l;
}
let rafEtat = 0, minuteurSigne = 0;
function etatBientot() { if (!minuteurSigne) minuteurSigne = setTimeout(() => { minuteurSigne = 0; chargerEtat(); }, 2000); }
function surEvenement(e) {
  switch (e.type) {
    case 'tour_fin': {
      if (e.erreur) {
        const titre = S.etat.tours?.find((x) => x.tache === e.tache)?.titre || e.tache;
        erreur(t('app.tour_echec', { titre, erreur: e.erreur }));
      }
      chargerEtat(); evtDetail(e); evtTransfo(e); evtTourManager(e); planifier(e.tache); rechargerCompactage(); break; // mesure par tour (INV-REGLAGES-1 : plus de redessin complet sur etat)
    }
    case 'tour_debut': chargerEtat(); evtDetail(e); evtTourManager(e); planifier(e.tache); break;
    case 'manager': evtManager(e); break; // INV-MANAGER-1
    case 'revue': evtDetail(e); chargerEtat(); break;
    case 'remontee': evtDetail(e); break; // INV-PILOTAGE-3 : ligne d’une descendante, sans tour
    case 'natif_fin': chargerEtat(); evtDetail(e); planifier(e.tache); break; // INV-NATIF-1
    case 'controle': evtDetail(e); break;
    case 'tour_texte': case 'tour_outil': {
      let t = S.etat.tours.find((x) => x.tache === e.tache);
      if (!t) { t = { tache: e.tache, titre: e.tache, depuis: new Date().toISOString(), dernier: '' }; S.etat.tours.push(t); }
      t.dernier = dernierLigne(e.texte, e.type);
      etatBientot(); // INV-VIGIE-1 : la phrase d'activité est calculée par le serveur
      cancelAnimationFrame(rafEtat);
      rafEtat = requestAnimationFrame(() => emit('etat'));
      evtDetail(e);
      break;
    }
    case 'arbre': planifier(null, true); break;
    case 'pause_ram': chargerEtat(); planifier(); rechargerSimultanes(); break;
    case 'simultanes': rechargerSimultanes(); break;
    case 'executeurs': rechargerExecuteurs(); break; // INV-DISTANT-4
    case 'economie': rechargerEconomie(); break;
    case 'pause': chargerEtat(); evtDetail(e); planifier(e.tache); break; // INV-EXEC-10
    case 'note': evtNoteArbre(e); evtNoteVue(e); break;
    case 'proposition': chargerProps(); chargerEtat(); break;
    case 'poste': chargerEtat(); planifier(); break;
    case 'suivi': etatBientot(); break; // INV-TRAVAUX-1 : sous-agent ou avancement
    case 'vigie': chargerEtat(); break; // INV-VIGIE-1 : silence, diagnostic ou exploration
    case 'reseau': chargerEtat(); planifier(); break;
    case 'incident': emit('incident'); evtDetail(e); actualiserTravaux(); break; // INV-INCIDENT-1
    case 'interface': chargerInterface().catch((x) => erreur(x.message)); break;
  }
}

function bannière() {
  const b = $('#banniere');
  let t = 0;
  on('banniere', ({ m, type }) => {
    if (m === MSG_PERIME) return; // le bandeau « serveur à mettre à jour » le dit déjà, en permanence
    if (String(m).endsWith(MSG_ANNULE)) return; // INV-VERROU-1 : « Non » à la confirmation, rien n'a changé
    b.textContent = m;
    b.className = type;
    b.hidden = false;
    b.onclick = () => { b.hidden = true; };
    clearTimeout(t);
    t = setTimeout(() => { b.hidden = true; }, type === 'info' ? 5000 : 9000);
  });
}

// L'URL reflète le volet droit : #t=<tâche> · #n=<note> · #q=<recherche> · #g[=<centre>] (graphe) · #equipe. Chaque navigation ajoute une entrée d'historique.
const enc = encodeURIComponent;
const dec = (s) => { try { return decodeURIComponent(s); } catch { return s; } };
const hashCourant = () => (S.selection ? `#t=${enc(S.selection)}` : S.vue === 'equipe' ? '#equipe' : S.vue === 'reglages' ? hashReglages() : S.vue === 'aujourdhui' ? '#aujourdhui' : S.vue === 'compagnon' ? '#compagnon' : S.vue === 'travail' ? (S.portee ? `#travail=${enc(S.portee)}` : '#travail') : S.vue === 'travaux' ? '#en-cours' : S.vue === 'decisions' ? '#decisions' : S.vue === 'guide' ? hashGuide() : S.vue === 'note' && S.note ? `#n=${enc(S.note)}`
  : S.vue === 'recherche' && S.requete ? `#q=${enc(S.requete)}` : S.vue === 'graphe' ? (S.centre ? `#g=${enc(S.centre)}` : '#g') : '');
function pousserUrl(initial) {
  const hs = hashCourant();
  if (dec(location.hash) === dec(hs)) return;
  history[initial ? 'replaceState' : 'pushState'](null, '', hs || location.pathname + location.search);
}
let premier = true;
function majVoletDroit() {
  if (S.selection) ouvrirDetail(S.selection);
  else if (S.vue === 'equipe') dessinerEquipe(droit());
  else if (S.vue === 'reglages') dessinerReglages(droit());
  else if (S.vue === 'aujourdhui') dessinerAujourdhui(droit());
  else if (S.vue === 'compagnon') dessinerCompagnon(droit()); // INV-COMPAGNON-1
  else if (S.vue === 'travail') dessinerTravail(droit(), S.portee); // INV-COMPAGNON-2
  else if (S.vue === 'travaux') dessinerTravaux(droit());
  else if (S.vue === 'decisions') dessinerDecisions(droit());
  else if (S.vue === 'guide') dessinerGuide(droit()); // INV-GUIDE-1
  else if (S.vue === 'note' && S.note) dessinerNote(droit(), S.note);
  else if (S.vue === 'graphe') dessinerGraphe(droit(), S.centre);
  else if (S.vue === 'recherche') { fixerTerme(S.requete); dessinerResultats(droit(), S.requete); }
  else dessinerCascade(droit());
  pousserUrl(premier); premier = false;
  dessinerArbre();
}
const cascadeVisible = () => !S.selection && S.vue === 'cascade';

// Le mode ou une famille a changé : écarter les vues devenues interdites, relire ce qui vient de s'ouvrir, redessiner.
function surInterface() {
  if (S.vue === 'equipe' && !ouvert('equipe')) S.vue = 'cascade';
  if (['note', 'recherche', 'graphe'].includes(S.vue) && !ouvert('notes')) { S.vue = 'cascade'; S.note = null; S.requete = ''; }
  if (S.onglet === 'notes' && !ouvert('notes')) fixerOnglet('taches');
  if (simple() && S.portee?.startsWith('operation:')) S.portee = null; // une opération n'existe plus à l'écran
  rafraichirEcarts();
  chargerRevue();
  majVoletDroit();
  emit('arbre');
}

// Changement d'URL sans rechargement (saisie du hash, précédent / suivant) : on ouvre l'élément visé.
function depuisUrl() {
  const m = /^#(t|n|q)=(.*)$/.exec(location.hash);
  const g = /^#g(?:=(.*))?$/.exec(location.hash);
  const v = m ? dec(m[2]) : '';
  let ok = true, gd, rg, tv;
  if (m && m[1] === 't' && v) { if (S.selection !== v) ok = ouvrir(v); }
  else if (m && m[1] !== 't' && !ouvert('notes')) { if (S.selection || S.vue !== 'cascade') ok = ouvrir(null); }
  else if (m && m[1] === 'n' && v) { if (S.vue !== 'note' || S.note !== v || S.selection) ok = ouvrirNote(v); }
  else if (m && m[1] === 'q' && v) { if (S.vue !== 'recherche' || S.requete !== v || S.selection) ok = ouvrirRecherche(v); }
  else if (g && ouvert('notes')) ok = ouvrirGraphe(g[1] ? dec(g[1]) : null);
  else if (location.hash === '#equipe' && ouvert('equipe')) { if (S.vue !== 'equipe' || S.selection) ok = ouvrirVue('equipe'); }
  else if ((rg = /^#reglages(?:\/(.+))?$/.exec(location.hash))) { // #reglages/<section> ouvre la section (reglages.js)
    fixerAncreReglages(rg[1] && dec(rg[1]));
    if (S.vue !== 'reglages' || S.selection) ok = ouvrirVue('reglages'); else dessinerReglages(droit());
  }
  else if (location.hash === '#decisions') { if (S.vue !== 'decisions' || S.selection) ok = ouvrirVue('decisions'); }
  else if ((gd = /^#guide(?:=(.*))?$/.exec(location.hash))) { fixerAncre(dec(gd[1] || '')); ok = ouvrirVue('guide'); }
  else if (location.hash === '#aujourdhui') { if (S.vue !== 'aujourdhui' || S.selection) ok = ouvrirVue('aujourdhui'); }
  else if (location.hash === '#compagnon') { if (S.vue !== 'compagnon' || S.selection) ok = ouvrirVue('compagnon'); }
  else if ((tv = /^#travail(?:=(.+))?$/.exec(location.hash))) { const id = tv[1] ? dec(tv[1]) : null; if (S.vue !== 'travail' || S.portee !== id || S.selection) ok = ouvrirVue('travail', id); }
  else if (location.hash === '#en-cours') { if (S.vue !== 'travaux' || S.selection) ok = ouvrirVue('travaux'); }
  else if (S.selection || S.vue !== 'cascade') ok = ouvrir(null);
  if (!ok) history.pushState(null, '', hashCourant() || location.pathname + location.search); // navigation refusée (note modifiée) : l'URL reste fidèle à l'écran
}

async function demarrer() {
  try { await chargerInterface(); } catch (e) { erreur(e.message); } // avant le premier rendu : rien ne s'affiche pour être retiré aussitôt
  S.toutes = localStorage.getItem('orch.toutes') === '1';
  bannière();
  const h0 = /^#(t|n|q)=(.+)$/.exec(location.hash), tv0 = /^#travail(?:=(.+))?$/.exec(location.hash);
  const sansNotes = !ouvert('notes');
  if (h0 && h0[1] === 't') S.selection = dec(h0[2]);
  else if (h0 && h0[1] !== 't' && sansNotes) { /* notes fermées : lien ignoré */ }
  else if (h0 && h0[1] === 'n') { S.vue = 'note'; S.note = dec(h0[2]); }
  else if (h0) { S.vue = 'recherche'; S.requete = dec(h0[2]); }
  else if (/^#g(=|$)/.test(location.hash) && !sansNotes) { S.vue = 'graphe'; S.centre = location.hash.length > 3 ? dec(location.hash.slice(3)) : null; }
  else if (location.hash === '#equipe' && ouvert('equipe')) S.vue = 'equipe';
  else if (/^#reglages(\/|$)/.test(location.hash)) { S.vue = 'reglages'; fixerAncreReglages(dec(location.hash.slice(10))); }
  else if (location.hash === '#aujourdhui') S.vue = 'aujourdhui';
  else if (location.hash === '#compagnon') S.vue = 'compagnon';
  else if (tv0) { S.vue = 'travail'; S.portee = tv0[1] ? dec(tv0[1]) : null; }
  else if (location.hash === '#en-cours') S.vue = 'travaux';
  else if (location.hash === '#decisions') S.vue = 'decisions';
  else if (/^#guide(=|$)/.test(location.hash)) { S.vue = 'guide'; fixerAncre(dec(location.hash.slice(7))); }
  initDetail(droit());
  initArbre();
  initNotes();
  initBandeau();
  initIncidents();
  initTelephone();
  initDiscussion();
  initCascade();
  initNoteVue();
  initPonts(creerDepuisLien);
  initAlignement();
  initVersion();
  initMajAuto();
  initCerveau(() => initPremiersPas(initAccueil)); // second cerveau d'abord (INV-CERVEAU-1), puis assistant IA, puis l'accueil s'il se propose
  initMaj();
  initEtoile();
  initEconomie();
  initManager();
  on('selection', majVoletDroit);
  on('etat', actualiserTravaux); // INV-TRAVAUX-1 : relu sur événement serveur, jamais par minuteur
  $('#btn-travaux').addEventListener('click', () => ouvrirVue('travaux'));
  on('etat', () => { if (cascadeVisible()) etatCascade(droit()); if (S.vue === 'reglages' && !S.selection) etatReglages(droit()); });
  on('arbre', () => { if (!S.selection && S.vue === 'aujourdhui') dessinerAujourdhui(droit()); });
  for (const nom of ['arbre', 'props']) on(nom, () => { if (!S.selection && S.vue === 'decisions') dessinerDecisions(droit()); });
  for (const nom of ['arbre', 'props', 'toutes']) on(nom, () => { if (cascadeVisible()) dessinerCascade(droit()); });
  on('recharger', planifier);
  on('recharger-arbre', chargerArbre);
  on('recharger-etat', chargerEtat);
  on('vault-change', () => { if (!ouvert('notes')) return; actualiserNotes(); if (S.note) evtNoteVue({ chemin: S.note }); });
  on('interface', surInterface);
  window.addEventListener('hashchange', depuisUrl);
  window.addEventListener('popstate', depuisUrl);
  majVoletDroit();
  toutRecharger();
  let deja = false;
  ouvrirFlux(surEvenement, (ok) => {
    $('#conn').hidden = ok;
    if (ok && deja) toutRecharger();
    if (ok) deja = true;
  });
}
demarrer();
