// Rôle : vue « Aujourd'hui » du volet droit — en retard, dues aujourd'hui, dues dans les sept jours, puis « À moi ».
// Frontières : lit GET /aujourdhui (groupes et tri faits par le serveur) ; n'écrit rien ; ouvrir une tâche passe par store.ouvrir.
import { t, tn, LOCALE } from './langues.js';
import { h, remplacer, pastille, libelleStatut, filLisible } from './dom.js';
import { api } from './api.js';
import { ouvrir, erreur } from './store.js';
import { libelleEcheance, celluleCle } from './temps.js';
import { repereIA, surOccupees } from './verrou.js';
import { STATUTS_COURTS, cleStatut, statutsActifs, passeStatut, basculerStatut, effacerStatuts } from './filtres.js';
import { on } from './store.js';

let racine = null, coque = null, version = 0, dernier = null, tgEtat = null;
surOccupees(() => { if (coque?.isConnected && dernier) dessiner(dernier); });
on('filtre', () => { if (coque?.isConnected && dernier) dessiner(dernier); });

function ligne(x) {
  return h('li', null, h('button', { class: 'au-ligne', type: 'button', onclick: () => ouvrir(x.id) },
    pastille(x.statut),
    h('span', { class: 'au-titre', title: x.titre }, x.titre, repereIA(x.id), x.a_valider ? h('span', { class: 'tag', title: t('aujourdhui.valider_titre') }, t('aujourdhui.a_valider')) : null),
    h('span', { class: 'au-place', title: filLisible(x.fil_ariane).join(' › ') }, filLisible(x.fil_ariane).slice(-2).join(' › ')),
    x.a_valider ? h('span', { class: `au-res${x.resultat ? '' : ' manque'}`, title: t('aujourdhui.essai', { valeur: x.essai || t('aujourdhui.non_indique_agent') }) }, t('aujourdhui.resultat', { valeur: x.resultat || t('aujourdhui.non_indique') })) : null,
    h('span', { class: `au-ech${x.retard ? ' retard' : ''}`, title: x.echeance ? t('aujourdhui.echeance', { date: x.echeance }) : libelleStatut(x.statut) }, libelleEcheance(x.echeance, x.retard)),
    h('span', null, celluleCle(x.priorite))));
}

function groupe(g) {
  const l = g.taches.filter(passeStatut);
  return h('section', { class: `au-groupe au-${g.cle}`, 'aria-label': g.titre },
    h('h3', null, g.titre, ' ', h('span', { class: 'n' }, l.length)),
    l.length ? h('ul', { class: 'au-liste' }, l.map(ligne)) : h('p', { class: 'vide' }, t('aujourdhui.rien')));
}
// Filtre de statut partagé avec le volet et la vue principale (filtres.js).
function pastilles(d) {
  const c = {}, actifs = statutsActifs();
  for (const g of d.groupes) for (const x of g.taches) c[cleStatut(x)] = (c[cleStatut(x)] || 0) + 1;
  return h('div', { class: 'casc-chips', role: 'group', 'aria-label': t('cascade.filtre_statut_groupe') },
    STATUTS_COURTS.filter(([k]) => c[k] || actifs.includes(k)).map(([k, l]) => h('button', { class: 'chip-st', type: 'button', 'data-statut': k, 'aria-pressed': String(actifs.includes(k)), onclick: () => basculerStatut(k) },
      l, ' ', h('span', { class: 'n' }, c[k] || 0))),
    actifs.length ? h('button', { class: 'btn-discret', type: 'button', onclick: effacerStatuts }, t('cascade.effacer_filtre')) : null);
}

// Invitation à connecter Telegram : tant qu'il n'a ni jeton ni activation ; fermable (mémorisé sur ce navigateur).
function encartTelegram() {
  if (!tgEtat || tgEtat.jeton || tgEtat.actif || localStorage.getItem('orch.tg-encart') === '0') return null;
  const aller = () => { location.hash = '#reglages/telegram'; }; // ouvre la section Telegram (reglages.js)
  return h('div', { class: 'au-encart', 'data-id': 'au-telegram' }, h('span', null, t('aujourdhui.telegram_texte')),
    h('button', { class: 'btn', type: 'button', 'data-id': 'au-telegram-aller', onclick: aller }, t('aujourdhui.telegram_connecter')),
    h('button', { class: 'btn', type: 'button', 'data-id': 'au-telegram-non', onclick: () => { localStorage.setItem('orch.tg-encart', '0'); dessiner(dernier); } }, t('aujourdhui.plus_tard')));
}

function dessiner(d) {
  dernier = d;
  const total = d.groupes.reduce((a, g) => a + g.taches.filter(passeStatut).length, 0);
  const jour = new Date(`${d.date}T12:00:00`).toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' });
  remplacer(coque, h('h2', { class: 'casc-titre' }, t('aujourdhui.titre')), h('p', { class: 'au-date' }, tn('aujourdhui.date_total', total, { jour })), encartTelegram(), pastilles(d),
    total ? d.groupes.map(groupe) : h('p', { class: 'vide' }, t('aujourdhui.vide')));
}

// Le volet est redessiné à chaque changement de l'arbre : une réponse tardive d'un appel périmé est ignorée.
export async function dessinerAujourdhui(zone) {
  if (!coque || coque.parentNode !== zone) {
    racine = zone;
    coque = h('div', { class: 'aujourdhui' }, h('p', { class: 'vide' }, t('aujourdhui.chargement')));
    remplacer(racine, coque);
  }
  const moi = ++version;
  try {
    const d = await api('/aujourdhui');
    if (tgEtat === null) tgEtat = await api('/telegram').catch(() => ({ jeton: 'x' }));
    if (moi === version && coque.isConnected) dessiner(d);
  } catch (e) { erreur(e.message); }
}
