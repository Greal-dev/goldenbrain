// Rôle : point d'entrée — chargements, flux SSE, bannière d'erreurs, aiguillage du volet droit.
// Frontières : orchestre les modules ; aucune logique d'affichage propre.
import { t, traduireDom } from './langues.js';
import { $ } from './dom.js';

traduireDom();  // INV-LANGUE-1 : textes du HTML statique (data-t*) avant tout rendu
import { api, ouvrirFlux, MSG_PERIME, MSG_ANNULE } from './api.js';
import { S, on, emit, erreur, ouvrir, ouvrirVue, ouvrirNote, ouvrirRecherche, ouvrirGraphe, fixerOnglet } from './store.js';
import { initArbre, dessiner as dessinerArbre } from './arbre.js';
import { initBandeau, chargerRevue } from './bandeau.js';
import { initIncidents } from './incidents.js';
import { dessinerCascade, etatCascade, initCascade } from './cascade.js';
import { chargerInterface, ouvert, simple, initBarre } from './interface.js';
import { initNotes, evtNote as evtNoteArbre, actualiser as actualiserNotes } from './notes.js';
import { initAlignement, rafraichirEcarts } from './alignement.js';
import { evtTransfo } from './transfo.js';
import { initTelephone } from './telephone.js';
import { initDiscussion } from './discussion.js';
import { initBandeaux } from './bandeaux.js';
import { initApercus } from './apercus.js';
import { charger, pret, sur, surCharge } from './paresseux.js';

const droit = () => $('#volet-droit');
// INV-REACTIVITE-1 : ces modules ne sont pas chargés au premier affichage ; tant qu'ils ne sont pas prêts, leurs événements n'ont rien à mettre à jour.
const rafraichir = sur('detail', 'rafraichir'), evtDetail = sur('detail', 'evtDetail'), tacheOuverte = () => pret('detail')?.tacheOuverte() ?? null;
const rechargerManager = sur('manager', 'rechargerManager'), evtManager = sur('manager', 'evtManager'), evtTourManager = sur('manager', 'evtTourManager');
const rechargerSimultanes = surCharge('simultanes', 'recharger'), rechargerCompactage = surCharge('compactage', 'recharger'), rechargerExecuteurs = surCharge('executeurs', 'recharger');
const rechargerEconomie = surCharge('economie', 'recharger'), actualiserTravaux = sur('travaux', 'actualiserTravaux'), evtNoteVue = sur('note-vue', 'evtNote');
const managerPret = () => charger('manager', (m) => m.initManager());
const detailPret = () => charger('detail', (m) => m.initDetail(droit()));
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
const hashCourant = () => (S.selection ? `#t=${enc(S.selection)}` : S.vue === 'equipe' ? '#equipe' : S.vue === 'reglages' ? (pret('reglages')?.hashReglages() ?? location.hash) : S.vue === 'aujourdhui' ? '#aujourdhui' : S.vue === 'compagnon' ? '#compagnon' : S.vue === 'travail' ? (S.portee ? `#travail=${enc(S.portee)}` : '#travail') : S.vue === 'travaux' ? '#en-cours' : S.vue === 'decisions' ? '#decisions' : S.vue === 'guide' ? (pret('guide')?.hashGuide() ?? location.hash) : S.vue === 'note' && S.note ? `#n=${enc(S.note)}`
  : S.vue === 'recherche' && S.requete ? `#q=${enc(S.requete)}` : S.vue === 'graphe' ? (S.centre ? `#g=${enc(S.centre)}` : '#g') : '');
function pousserUrl(initial) {
  const hs = hashCourant();
  if (dec(location.hash) === dec(hs) || location.hash.startsWith('#f=')) return; // #f= : lecteur de fichiers, propriétaire de son adresse (lecteur.js)
  history[initial ? 'replaceState' : 'pushState'](null, '', hs || location.pathname + location.search);
}
let premier = true, tourEcran = 0, ancreInitiale = null; // ancreInitiale : section de réglages de l'adresse d'arrivée, appliquée avant le premier dessin
// Un écran se charge à la demande ; si l'utilisateur est parti ailleurs entretemps (tourEcran a changé), il n'est pas dessiné.
function ecran(nom, dessiner, init = null) {
  const mon = tourEcran;
  charger(nom, init).then((m) => { if (mon === tourEcran) { dessiner(m); pousserUrl(false); } }, (e) => erreur(e.message));
}
function majVoletDroit() {
  tourEcran += 1;
  if (S.selection) { const mon = tourEcran; detailPret().then((m) => { if (mon === tourEcran) m.ouvrirDetail(S.selection); }, (e) => erreur(e.message)); }
  else if (S.vue === 'equipe') ecran('equipe', (m) => m.dessinerEquipe(droit()));
  else if (S.vue === 'reglages') ecran('reglages', (m) => { if (ancreInitiale !== null) { m.fixerAncreReglages(ancreInitiale); ancreInitiale = null; } m.dessinerReglages(droit()); });
  else if (S.vue === 'aujourdhui') ecran('aujourdhui', (m) => m.dessinerAujourdhui(droit()));
  else if (S.vue === 'compagnon') ecran('compagnon', (m) => m.dessinerCompagnon(droit())); // INV-COMPAGNON-1
  else if (S.vue === 'travail') ecran('travail', (m) => m.dessinerTravail(droit(), S.portee)); // INV-COMPAGNON-2
  else if (S.vue === 'travaux') ecran('travaux', (m) => m.dessinerTravaux(droit()));
  else if (S.vue === 'decisions') ecran('decisions', (m) => m.dessinerDecisions(droit()));
  else if (S.vue === 'guide') ecran('guide', (m) => m.dessinerGuide(droit())); // INV-GUIDE-1
  else if (S.vue === 'note' && S.note) ecran('note-vue', (m) => m.dessinerNote(droit(), S.note), (m) => m.initNoteVue());
  else if (S.vue === 'graphe') ecran('graphe', (m) => m.dessinerGraphe(droit(), S.centre));
  else if (S.vue === 'recherche') {
    const terme = S.requete;
    Promise.all([charger('recherche'), charger('resultats')]).then(([r, m]) => { if (terme === S.requete && S.vue === 'recherche' && !S.selection) { r.fixerTerme(terme); m.dessinerResultats(droit(), terme); pousserUrl(false); } }, (e) => erreur(e.message));
  }
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
    const section = rg[1] && dec(rg[1]);
    charger('reglages').then((m) => {
      m.fixerAncreReglages(section);
      if (S.vue !== 'reglages' || S.selection) { if (!ouvrirVue('reglages')) history.pushState(null, '', hashCourant() || location.pathname + location.search); } else { tourEcran += 1; ecran('reglages', (x) => x.dessinerReglages(droit())); } // un seul dessin : un second défairait l'ouverture de la section visée
    }, (e) => erreur(e.message));
  }
  else if (location.hash === '#decisions') { if (S.vue !== 'decisions' || S.selection) ok = ouvrirVue('decisions'); }
  else if ((gd = /^#guide(?:=(.*))?$/.exec(location.hash))) {
    const ancre = dec(gd[1] || '');
    charger('guide').then((m) => { m.fixerAncre(ancre); if (!ouvrirVue('guide')) history.pushState(null, '', hashCourant() || location.pathname + location.search); }, (e) => erreur(e.message));
  }
  else if (location.hash === '#aujourdhui') { if (S.vue !== 'aujourdhui' || S.selection) ok = ouvrirVue('aujourdhui'); }
  else if (location.hash === '#compagnon') { if (S.vue !== 'compagnon' || S.selection) ok = ouvrirVue('compagnon'); }
  else if ((tv = /^#travail(?:=(.+))?$/.exec(location.hash))) { const id = tv[1] ? dec(tv[1]) : null; if (S.vue !== 'travail' || S.portee !== id || S.selection) ok = ouvrirVue('travail', id); }
  else if (location.hash === '#en-cours') { if (S.vue !== 'travaux' || S.selection) ok = ouvrirVue('travaux'); }
  else if (S.selection || S.vue !== 'cascade') ok = ouvrir(null);
  if (!ok) history.pushState(null, '', hashCourant() || location.pathname + location.search); // navigation refusée (note modifiée) : l'URL reste fidèle à l'écran
}

// Services de fond et fiche de tâche : chargés juste après le premier affichage, jamais avant (INV-REACTIVITE-1). Un échec se signale, sans bloquer le reste.
function differes() {
  const sûr = (p) => p.catch((e) => erreur(e.message));
  sûr(detailPret());
  sûr(charger('lecteur', (m) => m.initLecteur()));
  sûr(charger('version', (m) => m.initVersion()));
  sûr(charger('maj-auto', (m) => m.initMajAuto()));
  sûr(charger('maj', (m) => m.initMaj()));
  sûr(charger('etoile', (m) => m.initEtoile()));
  sûr(charger('economie', (m) => m.initEconomie()));
  sûr(managerPret());
  sûr(Promise.all([charger('note-gestes'), charger('ponts')]).then(([g, p]) => p.initPonts(g.creerDepuisLien)));
  // Second cerveau d'abord (INV-CERVEAU-1), puis assistant IA, puis l'accueil s'il se propose.
  sûr(Promise.all([charger('cerveau'), charger('premiers-pas'), charger('accueil')]).then(([c, pp, ac]) => c.initCerveau(() => pp.initPremiersPas(ac.initAccueil))));
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
  else if (/^#reglages(\/|$)/.test(location.hash)) { S.vue = 'reglages'; ancreInitiale = dec(location.hash.slice(10)); }
  else if (location.hash === '#aujourdhui') S.vue = 'aujourdhui';
  else if (location.hash === '#compagnon') S.vue = 'compagnon';
  else if (tv0) { S.vue = 'travail'; S.portee = tv0[1] ? dec(tv0[1]) : null; }
  else if (location.hash === '#en-cours') S.vue = 'travaux';
  else if (location.hash === '#decisions') S.vue = 'decisions';
  else if (/^#guide(=|$)/.test(location.hash)) { S.vue = 'guide'; const ancre = dec(location.hash.slice(7)); charger('guide').then((m) => m.fixerAncre(ancre)); }
  initArbre();
  initNotes();
  initBandeau();
  initApercus();
  initIncidents();
  initTelephone();
  initBandeaux();
  initDiscussion();
  initBarre(); // INV-BARRE-1
  initCascade();
  initAlignement();
  on('selection', majVoletDroit);
  on('etat', actualiserTravaux); // INV-TRAVAUX-1 : relu sur événement serveur, jamais par minuteur
  // Un clic sur « Manager » avant que son module soit prêt le charge, puis rejoue le clic.
  $('#btn-manager').addEventListener('click', (e) => { if (pret('manager')) return; e.stopImmediatePropagation(); managerPret().then(() => $('#btn-manager').click(), (x) => erreur(x.message)); });
  on('etat', () => { if (cascadeVisible()) etatCascade(droit()); if (S.vue === 'reglages' && !S.selection) pret('reglages')?.etatReglages(droit()); });
  on('arbre', () => { if (!S.selection && S.vue === 'aujourdhui') pret('aujourdhui')?.dessinerAujourdhui(droit()); });
  for (const nom of ['arbre', 'props']) on(nom, () => { if (!S.selection && S.vue === 'decisions') pret('decisions')?.dessinerDecisions(droit()); });
  for (const nom of ['arbre', 'props', 'toutes']) on(nom, () => { if (cascadeVisible()) dessinerCascade(droit()); });
  on('recharger', planifier);
  on('recharger-arbre', chargerArbre);
  on('recharger-etat', chargerEtat);
  on('vault-change', () => { if (!ouvert('notes')) return; actualiserNotes(); if (S.note) evtNoteVue({ chemin: S.note }); });
  on('interface', surInterface);
  window.addEventListener('hashchange', depuisUrl);
  window.addEventListener('popstate', depuisUrl);
  let lance = false;
  on('arbre', () => { if (!lance) { lance = true; setTimeout(differes, 0); } }); // une fois l'arbre peint, pas avant
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
