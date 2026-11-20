// Rôle : section « PC connectés » de la page Réglages — exécuteurs distants : connexion, mémoire libre, tours en cours ou en attente,
// appairage par code court (valable quelques minutes, usage unique), création d'un jeton (montré une seule fois)
// et révocation ; état des prérequis de chaque PC et bouton « Réparer ». INV-DISTANT-1, INV-DISTANT-4, INV-APPAIRAGE-1, INV-INSTALL-4.
// Frontières : GET /api/executeurs, POST /api/executeurs/appairage, POST/DELETE /api/executeurs/jetons, POST /api/executeurs/reparations ;
// le serveur décide de la répartition et de la validité du code.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit } from './store.js';
import { t, tn, LOCALE } from './langues.js';

const GO = 1024 ** 3;
const go = (o) => (o / GO).toLocaleString(LOCALE, { maximumFractionDigits: 1 });
let zone = null;
let montre = null; // { nom, jeton } : affiché jusqu'au prochain rechargement de la page
let appairage = null; // { nom, code, fin } : code d'appairage affiché tant qu'il est valable

const ETATS = { ok: t('executeurs.etat_ok'), manquant: t('executeurs.etat_manquant'), a_connecter: t('executeurs.etat_a_connecter'),
  manuel: t('executeurs.etat_manuel'), bloque: t('executeurs.etat_bloque'), inconnu: t('executeurs.etat_inconnu') };

async function reparer(nom, p) {
  // INV-INSTALL-4 : l'accord porte la commande exacte, que l'exécuteur confronte à son propre catalogue.
  if (!confirm(t('executeurs.confirmer_reparation', { nom, commande: p.commande }))) return;
  try { await post('/executeurs/reparations', { nom, etape: p.id, accord: p.commande }); recharger(); } catch (e) { erreur(e.message); }
}

function prerequis(x) {
  if (x.revoque || !x.prerequis.length) return null;
  const faux = x.prerequis.filter((p) => p.etat !== 'ok' && !p.optionnel && p.etat !== 'inconnu');
  const rep = x.reparation;
  return h('div', { class: 'note', 'data-id': `exe-prerequis-${x.nom}` },
    h('p', null, faux.length ? tn('executeurs.prerequis', faux.length) : t('executeurs.pret')),
    h('ul', null, ...x.prerequis.filter((p) => p.etat !== 'ok' || !p.optionnel).map((p) => h('li', { 'data-id': `exe-etape-${x.nom}-${p.id}` },
      t(p.optionnel && p.etat !== 'ok' ? 'executeurs.etape_facultative' : 'executeurs.etape', { libelle: p.libelle, etat: ETATS[p.etat] || p.etat }),
      p.commande && ['manquant', 'a_connecter'].includes(p.etat) && x.connecte
        ? h('button', { class: 'btn', type: 'button', 'data-id': `exe-reparer-${x.nom}-${p.id}`, onclick: () => reparer(x.nom, p) }, t('executeurs.reparer')) : null,
      p.instructions && p.etat !== 'ok' ? h('span', { class: 'note' }, ` — ${p.instructions}`) : null))),
    rep ? h('p', { 'data-id': `exe-reparation-${x.nom}` }, t('executeurs.derniere_reparation', { etape: rep.etape, etat: rep.etat }) + (rep.message ? ' — ' + rep.message : '')) : null);
}

function ligne(x) {
  const etat = x.revoque ? t('executeurs.revoque') : x.connecte ? t('executeurs.connecte') : (x.vu_il_y_a_s == null ? t('executeurs.jamais_vu') : t('executeurs.perdu', { s: x.vu_il_y_a_s }));
  const mem = x.memoire?.libre != null ? ` · ${t('executeurs.memoire', { libre: go(x.memoire.libre), total: go(x.memoire.total) })}` : '';
  const tours = x.tours.map((tr) => h('li', { 'data-id': `exe-tour-${tr.tache}` }, tr.attente ? t('executeurs.tour_attente', { titre: tr.titre }) : tr.titre));
  const prepa = x.attente.map((i) => h('li', null, t('executeurs.preparation', { id: i })));
  return h('li', { class: 'rg-fam', 'data-id': `exe-${x.nom}` },
    h('div', null, h('b', null, x.nom), ` — ${etat}${mem} · ${tn('executeurs.seances', x.tours.length, { places: x.places || 1 })}`,
      x.harnais.length ? h('span', { class: 'note' }, ` · ${x.harnais.join(', ')}`) : null,
      x.revoque ? null : h('button', { class: 'btn', type: 'button', 'data-id': `exe-revoquer-${x.nom}`, onclick: () => revoquer(x.nom) }, t('executeurs.revoquer'))),
    tours.length || prepa.length ? h('ul', null, ...tours, ...prepa) : null,
    prerequis(x));
}

async function creer(nom) {
  try { montre = await post('/executeurs/jetons', { nom }); recharger(); } catch (e) { erreur(e.message); }
}

async function appairer(nom) {
  try {
    const c = await post('/executeurs/appairage', { nom });
    appairage = { nom: c.nom, code: c.code, fin: Date.now() + c.valide_s * 1000 };
    recharger();
  } catch (e) { erreur(e.message); }
}

function blocAppairage(ecoute) {
  if (!appairage || appairage.fin <= Date.now()) { appairage = null; return null; }
  const min = Math.max(1, Math.ceil((appairage.fin - Date.now()) / 60000));
  const adresse = ecoute ? `http://${ecoute}:${location.port}` : `http://${t('executeurs.adresse_chef')}:${location.port}`;
  return h('div', { class: 'note', 'data-id': 'exe-appairage' },
    h('p', null, t('executeurs.code', { nom: appairage.nom, min }),
      h('code', { 'data-id': 'exe-code' }, appairage.code)),
    h('p', null, t('executeurs.sur_autre'), h('code', null, `python orch.py executeur --serveur ${adresse} --code ${appairage.code}`)));
}

async function revoquer(nom) {
  if (!confirm(t('executeurs.confirmer_revocation', { nom }))) return;
  try { await api(`/executeurs/jetons/${encodeURIComponent(nom)}`, { methode: 'DELETE' }); recharger(); } catch (e) { erreur(e.message); }
}

function remplir(r) {
  const n = r.executeurs.length;
  emit('resume', ['executeurs', n ? tn('executeurs.resume', n) : t('executeurs.resume_aucun')]);
  if (!zone) return;
  // le code consommé (l'exécuteur s'est appairé) ou expiré côté chef disparaît de l'écran
  if (appairage && !r.appairages?.some((x) => x.nom === appairage.nom)) appairage = null;
  const champ = h('input', { type: 'text', 'data-id': 'exe-nom', placeholder: t('executeurs.nom_pc'), maxlength: '40' });
  remplacer(zone,
    h('ul', { class: 'rg-liste', 'data-id': 'exe-liste' }, r.executeurs.length ? r.executeurs.map(ligne) : h('li', null, t('executeurs.aucun'))),
    blocAppairage(r.ecoute),
    montre ? h('p', { class: 'note', 'data-id': 'exe-jeton' }, t('executeurs.jeton', { nom: montre.nom }), h('code', null, montre.jeton)) : null,
    h('div', { class: 'rg-sim' }, champ, h('button', { class: 'btn', type: 'button', 'data-id': 'exe-appairer', onclick: () => champ.value.trim() && appairer(champ.value.trim()) }, t('executeurs.appairer')),
      h('button', { class: 'btn', type: 'button', 'data-id': 'exe-creer', onclick: () => champ.value.trim() && creer(champ.value.trim()) }, t('executeurs.creer'))),
    h('p', { class: 'note' }, r.ecoute ? t('executeurs.ecoute', { adresse: r.ecoute }) : t('executeurs.ecoute_locale')));
}

let derniere = 0;
export function recharger() {
  // Une réponse tardive d'une lecture plus ancienne ne doit pas écraser l'état d'une lecture plus récente
  // (course constatée : l'état « tout est prêt » disparaissait après une réparation).
  const rang = ++derniere;
  if (zone?.isConnected) api('/executeurs').then((r) => { if (rang === derniere) remplir(r); }).catch((e) => erreur(e.message));
}

export function sectionExecuteurs() {
  zone = h('div', { 'data-id': 'executeurs' }, h('p', { class: 'note' }, t('executeurs.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('executeurs.titre')), zone];
}
