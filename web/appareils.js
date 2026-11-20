// Rôle : section « Appareils » de la page Réglages — accès distant depuis le téléphone par le réseau privé (Tailscale) :
// état de l'accès (actif, HTTPS), code QR du téléchargement de Tailscale, « Ajouter un téléphone » (code QR à usage unique,
// deux minutes), liste des appareils avec dernière connexion, révocation d'un clic, journal des connexions distantes.
// INV-DISTANT-5, INV-DISTANT-6, INV-DISTANT-7, INV-DISTANT-8.
// Frontières : GET /api/appareils, POST /api/appareils/appairage, DELETE /api/appareils/{id} (au poste seulement) ;
// le code QR est calculé par le serveur et montré en image (jamais d'innerHTML, INV-WEB-1).
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit } from './store.js';
import { t, tn, LOCALE } from './langues.js';

let zone = null;
let code = null; // { nom, qr, lien, fin } : affiché tant qu'il est valable
let minuterie = null;

const image = (svg, alt, id) => h('img', { class: 'qr', 'data-id': id, alt, width: '200', height: '200',
  src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg) });
const quand = (ts) => (ts ? new Date(ts * 1000).toLocaleString(LOCALE, { dateStyle: 'short', timeStyle: 'short' }) : '—');

async function ajouter(nom) {
  try {
    const c = await post('/appareils/appairage', { nom });
    code = { nom: c.nom, qr: c.qr, lien: c.lien, fin: Date.now() + c.valide_s * 1000 };
    clearInterval(minuterie);
    minuterie = setInterval(() => { if (!zone?.isConnected || !code || code.fin <= Date.now()) clearInterval(minuterie); recharger(); }, 5000);
    recharger();
  } catch (e) { erreur(e.message); }
}

async function revoquer(a) {
  if (!confirm(t('appareils.confirmer_revocation', { nom: a.nom }))) return;
  try { await api(`/appareils/${encodeURIComponent(a.id)}`, { methode: 'DELETE' }); recharger(); } catch (e) { erreur(e.message); }
}

function blocCode() {
  if (!code || code.fin <= Date.now()) { code = null; return null; }
  const s = Math.max(0, Math.round((code.fin - Date.now()) / 1000));
  return h('div', { class: 'note', 'data-id': 'app-code' },
    h('p', null, t('appareils.scanner', { nom: code.nom, s })),
    image(code.qr, t('appareils.qr_appairage'), 'app-qr'));
}

function etat(r) {
  if (!r.ecoute) return t('appareils.inactif');
  if (!r.actif) return t('appareils.coupe', { adresse: r.ecoute });
  return t(r.gestes === 'confirmer' ? 'appareils.actif_confirmer' : 'appareils.actif_interdire', { adresse: r.adresse });
}

function remplir(r) {
  emit('resume', ['appareils', r.actif && r.adresse ? tn('appareils.resume', r.appareils.length) : t('appareils.resume_coupe')]);
  if (!zone) return;
  const champ = h('input', { type: 'text', 'data-id': 'app-nom', placeholder: t('appareils.nom'), maxlength: '40' });
  const actif = r.actif && r.adresse;
  remplacer(zone,
    h('p', { 'data-id': 'app-etat' }, etat(r)),
    actif && !r.https ? h('p', { class: 'note alerte', 'data-id': 'app-sans-https' },
      t('appareils.sans_https')) : null,
    h('details', null, h('summary', null, t('appareils.installer')),
      h('p', { class: 'note' }, t('appareils.reseau')),
      image(r.qr_tailscale, t('appareils.qr_tailscale'), 'app-qr-tailscale'),
      h('p', null, h('a', { href: r.tailscale, target: '_blank', rel: 'noopener' }, r.tailscale))),
    h('ul', { class: 'rg-liste', 'data-id': 'app-liste' }, r.appareils.length ? r.appareils.map((a) => h('li', { class: 'rg-fam', 'data-id': `app-${a.id}` },
      h('b', null, a.nom), ' — ' + t('appareils.derniere', { quand: quand(a.derniere), ip: a.ip || '?' }),
      h('button', { class: 'btn', type: 'button', 'data-id': `app-revoquer-${a.id}`, onclick: () => revoquer(a) }, t('appareils.revoquer'))))
      : h('li', null, t('appareils.aucun'))),
    blocCode(),
    actif ? h('div', { class: 'rg-sim' }, champ, h('button', { class: 'btn', type: 'button', 'data-id': 'app-ajouter',
      onclick: () => ajouter(champ.value.trim()) }, t('appareils.ajouter'))) : null,
    h('details', { 'data-id': 'app-journal' }, h('summary', null, t('appareils.journal', { n: r.journal.length })),
      h('ul', null, ...r.journal.map((e) => h('li', null, `${quand(e.t)} · ${e.genre} · ${e.ip}${e.detail ? ' · ' + e.detail : ''}${e.nb ? ` (×${e.nb})` : ''}`)))));
}

export function recharger() {
  if (zone?.isConnected) api('/appareils').then(remplir).catch((e) => erreur(e.message));
}

export function sectionAppareils() {
  zone = h('div', { 'data-id': 'appareils' }, h('p', { class: 'note' }, t('appareils.lecture')));
  queueMicrotask(recharger);
  return [h('h3', null, t('appareils.titre')), zone];
}
