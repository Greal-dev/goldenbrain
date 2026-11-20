// Rôle : serveur à jour — bandeau persistant quand le code sur disque est plus récent que celui qui tourne,
// redémarrage différé à la fin des tours (INV-VERSION-3), redémarrage (409 -> « Redémarrer quand même »), voile d'attente puis rechargement de la page.
// Frontières : lit S.etat.version ; POST /redemarrer ; sonde /api/etat. INV-VERSION-1 (docs/ARCHITECTURE.md, lot 7).
import { h, $, remplacer } from './dom.js';
import { S, on, emit, erreur } from './store.js';
import { api, post, sonder, brancherPerime } from './api.js';
import { formulaire } from './dialogue.js';
import { t, tn } from './langues.js';

const DELAI_RELANCE_MS = 20000;
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
let zone, bouton, bandeauDiffere, texteDiffere, voile, forcePerime = false, enCours = false;

const perime = () => forcePerime || S.etat.version?.a_jour === false;
function dessiner() {
  zone.hidden = !perime() && !enCours;
  const attente = !!S.etat.version?.differe;
  bandeauDiffere.hidden = !attente;
  if (attente) {
    const n = (S.etat.tours?.length || 0) + (S.etat.en_file || 0);
    texteDiffere.textContent = t('version.differe', { n }) + ' ';
  }
}

// INV-VERSION-3 : le serveur surveille les tours et se relance seul ; la page attend son retour puis se recharge.
async function armerDiffere() {
  const avant = S.etat.version?.demarree;
  try { await post('/redemarrer-differe', {}); } catch (e) { erreur(e.message); return; }
  S.etat.version = { ...S.etat.version, differe: true };
  dessiner();
  emit('recharger-etat'); // le compte (n) vient de l'état le plus frais
  surveillerDiffere(avant);
}
async function annulerDiffere() {
  try { await api('/redemarrer-differe', { methode: 'DELETE' }); } catch (e) { erreur(e.message); return; }
  S.etat.version = { ...S.etat.version, differe: false };
  dessiner();
}
// Le redémarrage différé survient sans clic : on guette l'extinction du serveur, comme `attendreRetour`.
let guette = false;
async function surveillerDiffere(avant) {
  if (guette) return;
  guette = true;
  for (;;) {
    await pause(2000);
    const e = await sonder();
    if (!e || (e.version?.demarree && e.version.demarree !== avant)) break;
    if (!e.version?.differe) { guette = false; S.etat.version = { ...S.etat.version, differe: false }; dessiner(); return; }
  }
  guette = false;
  enCours = true;
  await attendreRetour(avant);
}

// Retour du serveur = il répond ET (il a été vu coupé, ou son heure de démarrage a changé) : l'ancien processus peut répondre encore une seconde.
export async function attendreRetour(avant) {
  const debut = Date.now();
  const message = h('p', { class: 'voile-aide', role: 'status' });
  remplacer(voile, h('span', { class: 'tourne grand' }), h('p', { class: 'voile-titre' }, t('version.redemarrage')), message);
  voile.hidden = false;
  for (const el of [$('#bandeau'), $('#corps'), zone]) el.inert = true;
  voile.focus();
  let coupure = false;
  for (;;) {
    await pause(1000);
    const e = await sonder();
    if (!e) coupure = true;
    else if (coupure || (e.version?.demarree && e.version.demarree !== avant)) { location.reload(); return; }
    if (Date.now() - debut > DELAI_RELANCE_MS && !message.textContent) {
      message.textContent = t('version.ne_revient_pas');
    }
  }
}

async function redemarrer(force = false) {
  bouton.disabled = true;
  const avant = S.etat.version?.demarree;
  try {
    await post('/redemarrer', force ? { force: true, par: 'interface' } : { par: 'interface' });
  } catch (e) {
    bouton.disabled = false;
    if (e.statut === 409 && !force) return confirmerForce(e.message);
    if (e.statut === 404) { erreur(t('version.trop_ancien')); return; }
    erreur(e.message);
    return;
  }
  enCours = true;
  await attendreRetour(avant);
}

// INV-EXEC-1 : un tour coupé par le redémarrage reprend seul, une fois ; un message en file est perdu.
const avertissement = (n, f) => [
  n ? tn('version.interrompues', n) : '',
  f ? tn('version.perdus', f) : '',
].filter(Boolean).join(' ');

// Le nombre de tours vient de l'état le plus frais : il peut avoir changé depuis le dernier événement.
async function confirmerForce(motif) {
  let et = S.etat;
  try { et = await api('/etat'); } catch { /* on garde l'état connu */ }
  const n = et.tours?.length || 0, f = et.en_file || 0;
  const v = await formulaire({
    titre: t('version.forcer_titre'), valider: t('version.forcer_valider'), annuler: t('version.attendre'), focus: 'annuler',
    texte: `${motif} ${avertissement(n, f)}`,
    corps: h('button', { type: 'button', class: 'btn', 'data-differe': '', onclick: (ev) => { ev.target.closest('dialog').close(); armerDiffere(); } },
      t('version.differer')),
  });
  if (v) redemarrer(true);
}

export function initVersion() {
  zone = $('#maj-serveur'); voile = $('#voile-redemarrage');
  bouton = h('button', { type: 'button', class: 'btn petit primaire', onclick: () => redemarrer(false) }, t('version.redemarrer'));
  remplacer(zone, h('span', { class: 'maj-t' }, h('b', null, t('version.mis_a_jour')), t('version.ancienne')), bouton);
  bandeauDiffere = $('#redemarrage-differe');
  texteDiffere = h('span', { class: 'maj-t' });
  remplacer(bandeauDiffere, texteDiffere, h('button', { type: 'button', class: 'btn petit', onclick: annulerDiffere }, t('version.annuler')));
  brancherPerime(() => { forcePerime = true; dessiner(); });
  on('etat', dessiner);
  dessiner();
  setInterval(() => emit('recharger-etat'), 30000); // `disque` est recalculé côté serveur au plus toutes les 15 s
}
