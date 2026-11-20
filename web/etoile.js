// Rôle : invitation unique à mettre une étoile GitHub (fenêtre discrète) et son interrupteur dans les Réglages.
// Frontières : GET/PUT /api/etoile, POST /api/etoile/usage|reponse ; le serveur décide (INV-ETOILE-1). Aucune minuterie :
// le temps d'usage actif se cumule sur les événements d'interaction (onglet visible, pas d'inaction au-delà de 60 s) et
// ne part au serveur que par paquets d'une minute. Dès que l'invitation n'a plus lieu d'être, plus rien n'écoute.
import { h } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

const INACTION_MS = 60000; // au-delà, la pause n'est pas de l'usage
const PAQUET_S = 60;
const EVENEMENTS = ['pointerdown', 'keydown', 'wheel'];
let dernier = 0, cumul = 0, envoi = false, ecoute = false, ouverte = false;

async function repondre(choix, url) {
  if (choix === 'etoile' && url) window.open(url, '_blank', 'noopener');
  try { await post('/etoile/reponse', { choix }); } catch (e) { erreur(e.message); }
}

function inviter(url) {
  if (ouverte) return;
  ouverte = true;
  const dlg = h('dialog', { class: 'dlg', 'aria-label': t('etoile.titre'), 'data-id': 'etoile' });
  const choisir = async (choix) => { ouverte = false; dlg.close(); dlg.remove(); await repondre(choix, url); };
  const bouton = (choix, libelle, classe = 'btn') => h('button', { type: 'button', class: classe, 'data-choix': choix, onclick: () => choisir(choix) }, libelle);
  dlg.append(h('div', { class: 'dlg-form' },
    h('h3', null, t('etoile.question')),
    h('p', { class: 'dlg-texte' }, t('etoile.texte')),
    h('div', { class: 'dlg-actions' },
      bouton('jamais', t('etoile.jamais')), bouton('plus_tard', t('etoile.plus_tard')), bouton('etoile', t('etoile.mettre'), 'btn primaire'))));
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); choisir('plus_tard'); }); // Échap = « Plus tard »
  document.body.append(dlg);
  dlg.showModal();
}

function arreter() {
  for (const e of EVENEMENTS) window.removeEventListener(e, interaction, true);
  ecoute = false;
}

async function envoyer() {
  if (envoi || cumul < PAQUET_S) return;
  envoi = true;
  const s = cumul; cumul = 0;
  try { adopter(await post('/etoile/usage', { secondes: s })); } catch { cumul += s; } finally { envoi = false; }
}

function adopter(e) {
  if (!e) return;
  if (!e.actif) arreter();
  if (e.afficher) { arreter(); inviter(e.url); }
}

function interaction() {
  if (document.hidden) { dernier = 0; return; }
  const maintenant = Date.now();
  if (dernier) cumul += Math.min(maintenant - dernier, INACTION_MS) / 1000;
  dernier = maintenant;
  envoyer();
}

export async function initEtoile() {
  try {
    const e = await api('/etoile');
    if (!e.actif) return;
    if (!ecoute && !e.afficher) {
      ecoute = true;
      for (const ev of EVENEMENTS) window.addEventListener(ev, interaction, { capture: true, passive: true });
    }
    adopter(e);
  } catch { /* serveur ancien ou hors ligne : pas d'invitation */ }
}

// Réglages : interrupteur, état lu puis écrit par PUT /api/etoile.
export function sectionEtoile() {
  const el = h('div', { 'data-id': 'etoile-section' });
  const dessiner = (e) => {
    el.replaceChildren(h('h3', null, t('etoile.section')),
      h('label', { class: 'case' },
        h('input', { type: 'checkbox', 'data-id': 'etoile-actif', checked: e.actif ? true : null,
          onchange: async (ev) => { try { dessiner(await api('/etoile', { methode: 'PUT', corps: { actif: ev.target.checked } })); } catch (x) { erreur(x.message); } } }),
        h('b', null, t('etoile.proposer'))),
      h('p', { class: 'note' }, t('etoile.note')));
  };
  api('/etoile').then(dessiner).catch(() => {});
  return el;
}
