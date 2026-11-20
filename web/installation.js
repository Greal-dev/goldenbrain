// Rôle : section « Ajouter ce PC comme exécuteur » de la page Réglages — vérifie ce PC (Python, git, Tailscale, harnais, connexions),
// montre pour chaque étape la commande exacte qui sera lancée et ne la lance qu'après un accord explicite, une étape à la fois ;
// repli en instructions à copier (droits administrateur, connexion qui dialogue) ; appairage au chef par code court.
// INV-INSTALL-1 (accord = commande affichée), INV-INSTALL-2 (aucun identifiant saisi ici), INV-INSTALL-3 (repli administrateur).
// Frontières : GET /api/installation, GET /api/installation/travail, POST /api/installation/etapes/{id}, POST /api/installation/appairage.
// Le serveur ne lance que les commandes de son catalogue ; l'interface ne fait que relayer l'accord.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit } from './store.js';
import { t, tn } from './langues.js';

const LIBELLES = { ok: t('installation.etat_ok'), manquant: t('installation.etat_manquant'), manuel: t('installation.etat_manuel'),
  bloque: t('installation.etat_bloque'), a_connecter: t('installation.etat_a_connecter'), inconnu: t('installation.etat_inconnu') };
let zone = null;
let travail = null; // dernier relevé du travail d'arrière-plan
let minuteur = null;
let message = '';

async function lancer(e) {
  const dit = e.elevation ? `${e.commande}\n\n${t('installation.elevation')}` : e.commande;
  if (!confirm(t('installation.confirmer', { commande: dit }))) return;
  try { await post(`/installation/etapes/${encodeURIComponent(e.id)}`, { accord: e.commande }); } catch (x) { erreur(x.message); return; }
  suivre();
}

function suivre() {
  clearInterval(minuteur);
  const tic = async () => {
    try { travail = await api('/installation/travail'); } catch { travail = null; }
    if (!zone?.isConnected) { clearInterval(minuteur); return; }
    if (!travail?.en_cours) { clearInterval(minuteur); recharger(); } else rendreSortie();
  };
  minuteur = setInterval(tic, 1500);
  tic();
}

function rendreSortie() {
  const el = zone?.querySelector('[data-id="inst-sortie"]');
  if (el) el.textContent = (travail?.sortie || []).join('\n');
}

function etape(e) {
  const dit = e.etat === 'ok' ? null : e.commande
    ? h('div', null, t('installation.va_etre_fait'), h('code', { 'data-id': `inst-commande-${e.id}` }, e.commande), e.elevation ? h('span', { class: 'note' }, t('installation.droits_admin')) : null)
    : null;
  const lancable = ['manquant', 'a_connecter', 'inconnu'].includes(e.etat) && e.commande && e.sans_saisie && !travail?.en_cours;
  return h('li', { class: 'rg-fam', 'data-id': `inst-${e.id}`, 'data-etat': e.etat },
    h('div', null, h('b', null, e.libelle), t(e.optionnel ? 'installation.etat_facultatif' : 'installation.etat', { etat: LIBELLES[e.etat] || e.etat })),
    dit,
    e.instructions ? h('div', { class: 'note', 'data-id': `inst-instructions-${e.id}` }, e.au_terminal ? e.instructions : t('installation.a_faire', { instructions: e.instructions })) : null,
    e.etat === 'bloque' ? h('div', { class: 'note' }, t('installation.dabord', { etapes: e.attend.join(', ') })) : null,
    lancable ? h('button', { class: 'btn', type: 'button', 'data-id': `inst-lancer-${e.id}`, onclick: () => lancer(e) }, e.etat === 'manquant' ? t('installation.installer') : t('installation.connecter')) : null);
}

async function appairer(serveur, code) {
  message = '';
  try {
    const r = await post('/installation/appairage', { serveur, code });
    message = r.relie ? t('installation.apparie', { serveur, nom: r.nom }) : t('installation.apparie_attente', { serveur, nom: r.nom });
  } catch (e) { message = ''; erreur(e.message); }
  recharger();
}

function remplir(r) {
  emit('resume', ['installation', tn('installation.resume', r.etapes.filter((e) => e.etat === 'ok').length, { total: r.etapes.length })]);
  if (!zone) return;
  const serveur = h('input', { type: 'text', 'data-id': 'inst-serveur', placeholder: t('installation.adresse'), value: r.liaison.serveur || '', maxlength: '200' });
  const code = h('input', { type: 'text', 'data-id': 'inst-code', placeholder: t('installation.code'), maxlength: '32' });
  remplacer(zone,
    h('p', { class: 'note' }, t(r.admin ? 'installation.ce_pc_admin' : 'installation.ce_pc', { plateforme: r.plateforme })),
    h('ul', { class: 'rg-liste', 'data-id': 'inst-liste' }, r.etapes.map(etape)),
    h('pre', { class: 'note', 'data-id': 'inst-sortie' }, (travail?.sortie || []).join('\n')),
    travail?.resultat?.repli ? h('div', { class: 'note', 'data-id': 'inst-repli' }, t('installation.repli'), h('pre', null, travail.resultat.repli)) : null,
    travail?.resultat?.erreur ? h('p', { class: 'note' }, travail.resultat.erreur) : null,
    h('div', { class: 'rg-sim' }, serveur, code,
      h('button', { class: 'btn', type: 'button', 'data-id': 'inst-appairer', onclick: () => serveur.value.trim() && code.value.trim() && appairer(serveur.value.trim(), code.value.trim()) }, t('installation.appairer'))),
    message ? h('p', { class: 'note', 'data-id': 'inst-message' }, message) : null,
    h('p', { class: 'note' }, t('installation.meme_parcours')));
}

export function recharger() {
  if (zone?.isConnected) api('/installation').then(remplir).catch((e) => erreur(e.message));
}

export function sectionInstallation() {
  zone = h('div', { 'data-id': 'installation' }, h('p', { class: 'note' }, t('installation.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('installation.titre')), zone];
}
