// Rôle : vue « Travail en cours » du compagnon mobile (jalon 3) — les seules tâches épinglées sur cet appareil, et le chat de chacune.
// Frontières : l'épinglage est un réglage de l'appareil (localStorage : identifiants, rien du vault) ; la liste se lit dans l'instantané
//        (compagnon.js) ; la conversation par GET /taches/{id}/conversation, l'envoi par POST /taches/{id}/messages (routes existantes,
//        garde d'appareil INV-DISTANT-6/7) : aucune route nouvelle, aucun geste de statut ni de structure.
import { h, remplacer, pastille } from './dom.js';
import { api, post } from './api.js';
import { S, ouvrirVue, on } from './store.js';
import { epingles, estEpingle, basculerEpingle } from './epingles.js';
import { rendreConversation } from './conversation.js';
import { lireInstantane } from './compagnon.js';
import { t } from './langues.js';

const enc = encodeURIComponent;

let coque = null, ouvertId = null, bandeau = null, minuterie = 0, version = 0, envoi = false;

// --- liste -----------------------------------------------------------------------------------
async function dessinerListe() {
  const v = ++version, e = await lireInstantane();
  if (v !== version || !coque?.isConnected) return;
  const par = new Map((e.donnees?.arbre || []).filter((n) => n.type === 'tache').map((n) => [n.id, n]));
  const actifs = new Set((e.donnees?.travaux?.tours || []).map((x) => x.tache));
  const ids = epingles();
  remplacer(coque, h('button', { class: 'co-retour', type: 'button', onclick: () => ouvrirVue('compagnon') }, '‹ ', t('compagnon.titre')),
    h('h2', { class: 'casc-titre' }, t('travail.titre')),
    ids.length ? h('ul', { class: 'co-liste' }, ids.map((id) => {
      const n = par.get(id);
      return h('li', { class: 'tr-ligne' },
        h('button', { class: 'co-ligne', type: 'button', disabled: !e.enligne || !n, onclick: () => ouvrirVue('travail', id) },
          n ? pastille(n.statut) : null, h('span', { class: 'co-titre' }, n ? n.titre : t('travail.introuvable')),
          actifs.has(id) ? h('span', { class: 'tag' }, t('travail.au_travail')) : null),
        h('button', { class: 'btn-discret tr-pin', type: 'button', 'aria-label': t('travail.retirer'), onclick: () => { basculerEpingle(id); dessinerListe(); } }, '★'));
    })) : h('p', { class: 'vide' }, t('travail.vide')),
    e.enligne ? null : h('p', { class: 'co-meta' }, t('travail.hors_ligne')));
}

// --- chat ------------------------------------------------------------------------------------
async function chargerConv(zone, titre) {
  if (!ouvertId) return;
  const id = ouvertId;
  try {
    const l = await api(`/taches/${enc(id)}/conversation?limite=200`);
    if (id !== ouvertId || !zone.isConnected) return;
    const bas = zone.scrollHeight - zone.scrollTop - zone.clientHeight < 80;
    remplacer(zone, l.length ? rendreConversation(l, false, new Set()) : h('p', { class: 'vide' }, t('travail.aucun_echange')));
    if (bas) zone.scrollTop = zone.scrollHeight;
  } catch (e) { remplacer(zone, h('p', { class: 'co-retour-geste ko', role: 'alert' }, e.message)); }
}

async function dessinerChat(id) {
  ouvertId = id;
  const zone = h('div', { class: 'tr-conv', role: 'log' }), erreurEnvoi = h('p', { class: 'co-retour-geste ko', role: 'alert', hidden: true });
  const ta = h('textarea', { rows: 2, 'aria-label': t('travail.message'), placeholder: t('travail.message') });
  const bouton = h('button', { type: 'submit', class: 'btn primaire' }, t('travail.envoyer'));
  let titre = id;
  const pin = h('button', { class: 'btn-discret tr-pin', type: 'button', 'aria-pressed': String(estEpingle(id)), 'aria-label': t('travail.epingle'),
    onclick: () => { pin.setAttribute('aria-pressed', String(basculerEpingle(id))); } }, '★');
  const entete = h('header', { class: 'tr-tete' }, h('button', { class: 'co-retour', type: 'button', onclick: () => ouvrirVue('travail') }, '‹'),
    h('span', { class: 'co-titre' }, titre), pin);
  const form = h('form', { class: 'composer tr-saisie' }, erreurEnvoi, h('div', { class: 'c-ligne' }, ta, h('div', { class: 'c-col' }, bouton)));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const texte = ta.value.trim();
    if (!texte || envoi) return;
    envoi = true; bouton.disabled = true; bouton.textContent = t('compagnon.envoi'); erreurEnvoi.hidden = true;
    try { await post(`/taches/${enc(id)}/messages`, { texte }); ta.value = ''; await chargerConv(zone, titre); zone.scrollTop = zone.scrollHeight; }
    catch (e) { erreurEnvoi.textContent = t('travail.echec', { erreur: e.message }); erreurEnvoi.hidden = false; }
    envoi = false; bouton.disabled = false; bouton.textContent = t('travail.envoyer');
  });
  remplacer(coque, entete, zone, form);
  lireInstantane().then((e) => { // le titre vient de l'instantané ; le chat n'en dépend pas pour s'ouvrir
    const n = (e.donnees?.arbre || []).find((x) => x.type === 'tache' && x.id === id);
    if (n && id === ouvertId) { titre = n.titre; entete.querySelector('.co-titre').textContent = n.titre; }
  });
  await chargerConv(zone, titre);
  zone.scrollTop = zone.scrollHeight;
}

export function dessinerTravail(racine, id) {
  coque = h('div', { class: 'compagnon travail' });
  remplacer(racine, coque);
  ouvertId = null;
  if (id) dessinerChat(id); else dessinerListe();
}

// Flux d'événements existant : un tour qui commence, avance ou finit relit la conversation ouverte (rien ne tourne vue fermée).
on('etat', () => {
  if (!coque?.isConnected || S.vue !== 'travail') return;
  clearTimeout(minuterie);
  minuterie = setTimeout(() => { const z = coque.querySelector('.tr-conv'); if (z && !envoi) chargerConv(z, ''); else if (!ouvertId) dessinerListe(); }, 1200);
});
