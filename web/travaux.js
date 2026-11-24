// Rôle : écran « En cours » — ce qui travaille (agents, sous-agents, avancement), ce qui attend, les routines à venir, les incidents ouverts.
// Frontières : lit GET /travaux ; gestes : ouvrir, mettre en pause / reprendre (INV-TRAVAUX-2), arrêter (confirmation).
// Aucun minuteur (INV-TRAVAUX-1) : l'écran se relit sur les événements serveur relayés par app.js, et seulement s'il est visible.
import { t, tn, LOCALE } from './langues.js';
import { h, remplacer, depuis, heure } from './dom.js';
import { api, post } from './api.js';
import { ouvrir, erreur } from './store.js';
import { formulaire } from './dialogue.js';

let coque = null, version = 0;

// Durée entre deux horodatages ISO (sous-agent fini), sinon jusqu'à maintenant.
function duree(debut, fin) {
  if (!fin) return depuis(debut);
  const s = Math.max(0, Math.round((Date.parse(fin) - Date.parse(debut)) / 1000));
  return s < 60 ? t('duree.s', { n: s }) : s < 3600 ? t('duree.min', { n: Math.floor(s / 60) }) : t('duree.h', { n: Math.floor(s / 3600) });
}
const quand = (iso) => {
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? heure(iso) : t('encours.le', { date: d.toLocaleString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) });
};

async function geste(chemin, x) {
  try { await post(`/taches/${encodeURIComponent(x.tache)}/${chemin}`); await recharger(); } catch (e) { erreur(e.message); }
}
async function arreter(x) {
  const ok = await formulaire({ titre: t('encours.confirmer_titre'), texte: t('encours.confirmer_texte', { titre: x.titre }), valider: t('encours.arreter'), focus: 'annuler' });
  if (ok) await geste('arret', x);
}

function sousAgent(a) {
  const etat = a.fin ? (a.erreur ? t('encours.echec') : t('encours.fini')) : t('encours.en_cours');
  return h('li', { class: `tr-sa${a.fin ? ' fini' : ''}${a.erreur ? ' echec' : ''}`, 'data-id': 'tr-sous-agent' },
    h('span', { class: `tr-point${a.fin ? '' : ' tourne'}`, 'aria-hidden': 'true' }),
    h('span', { class: 'tr-sa-desc', title: a.genre ? t('encours.aide_genre', { genre: a.genre }) : null }, a.description || a.genre || t('encours.aide')),
    h('span', { class: 'tr-sa-etat' }, a.fin ? t('encours.sa_fini', { etat, duree: duree(a.debut, a.fin) }) : t('encours.sa_depuis', { etat, duree: duree(a.debut) })));
}

function carteTour(x) {
  const s = x.signe || {};
  const pause = s.pause_manuelle;
  const phrase = pause ? t('encours.en_pause') : x.pause_ram ? t('encours.pause_ram') : s.silencieux ? t('encours.silence', { duree: depuis(s.depuis) }) : s.etape || s.phrase || '…';  // la dernière action prime sur le dernier mot
  const av = s.avancement?.total ? s.avancement : null;
  const sa = s.sous_agents || [];
  const actifs = sa.filter((a) => !a.fin);
  return h('article', { class: `tr-carte${pause || x.pause_ram ? ' en-pause' : ''}${s.silencieux ? ' silence' : ''}`, 'data-id': 'tr-tour', 'data-tache': x.tache },
    h('header', { class: 'tr-tete' },
      h('div', { class: 'tr-noms' }, h('b', { class: 'tr-titre', title: x.titre }, x.titre), x.projet ? h('span', { class: 'tr-projet' }, x.projet) : null),
      h('span', { class: 'tr-depuis', title: x.depuis }, t('encours.depuis', { duree: depuis(x.depuis) }))),
    h('p', { class: 'tr-qui' }, t('encours.qui', { harnais: x.persona ? `${x.harnais} (${x.persona})` : x.harnais, modele: x.modele || t('encours.par_defaut') })),
    h('p', { class: 'tr-action', 'data-id': 'tr-action' }, phrase, s.fichiers ? h('span', { class: 'tr-fichiers' }, ` · ${tn('encours.fichiers', s.fichiers)}`) : null),
    av ? h('div', { class: 'tr-av', 'data-id': 'tr-avancement' },
      h('progress', { max: av.total, value: av.fait, 'aria-label': tn('encours.avancement', av.fait, { total: av.total }) }), h('span', null, tn('encours.avancement', av.fait, { total: av.total }))) : null,
    sa.length ? h('details', { class: 'tr-sas', open: actifs.length ? true : null },
      h('summary', null, t('encours.sous_agents', { n: sa.length }), actifs.length ? ` — ${t('encours.actifs', { n: actifs.length })}` : ''),
      h('ul', null, sa.slice().reverse().map(sousAgent))) : null,
    h('div', { class: 'tr-gestes' },
      h('button', { class: 'btn petit', type: 'button', 'data-id': 'tr-ouvrir', onclick: () => ouvrir(x.tache) }, t('encours.ouvrir')),
      x.pause_ram && !pause ? null : h('button', { class: 'btn petit', type: 'button', 'data-id': pause ? 'tr-reprendre' : 'tr-pause', onclick: () => geste(pause ? 'continuer' : 'suspendre', x) }, pause ? t('encours.reprendre') : t('encours.pause')),
      h('button', { class: 'btn petit danger', type: 'button', 'data-id': 'tr-arreter', onclick: () => arreter(x) }, t('encours.arreter'))));
}

function ligneFile(f) {
  const pourquoi = f.raison || (f.rang ? (f.motif ? t('encours.rang_motif', { rang: f.rang, motif: f.motif }) : t('encours.rang', { rang: f.rang })) : t('encours.en_file'));
  return h('li', null, h('button', { class: 'au-ligne tr-ligne', type: 'button', 'data-id': 'tr-file', onclick: () => ouvrir(f.tache) },
    h('span', { class: 'au-titre', title: f.titre }, f.titre), h('span', { class: 'au-place' }, f.projet || ''), h('span', { class: 'tr-raison' }, pourquoi)));
}
const ligneRoutine = (r) => h('li', null, h('button', { class: 'au-ligne tr-ligne', type: 'button', onclick: () => ouvrir(r.id) },
  h('span', { class: 'au-titre', title: r.titre }, r.titre), h('span', { class: 'tr-raison' }, t('encours.prochaine', { date: quand(r.prochaine) }))));
const ligneIncident = (i) => h('li', null, h('button', { class: 'au-ligne tr-ligne', type: 'button', title: i.motif, onclick: () => ouvrir(i.tache) },
  h('span', { class: 'au-titre', title: i.titre }, i.titre), h('span', { class: 'tr-raison' }, `${i.libelle} — ${i.geste}`), h('span', { class: 'au-place' }, quand(i.date))));

function bloc(cle, titre, items, vide, rendu, liste = true) {
  return h('section', { class: `au-groupe tr-${cle}`, 'aria-label': titre },
    h('h3', null, titre, ' ', h('span', { class: 'n' }, items.length)),
    !items.length ? h('p', { class: 'vide' }, vide) : liste ? h('ul', { class: 'au-liste' }, items.map(rendu)) : h('div', { class: 'tr-cartes' }, items.map(rendu)));
}

function dessiner(d) {
  remplacer(coque, h('h2', { class: 'casc-titre' }, t('encours.titre')), h('p', { class: 'au-date tr-sous-titre' }, t('encours.sous_titre')),
    bloc('tours', t('encours.travaillent'), d.tours, t('encours.rien'), carteTour, false),
    bloc('file', t('encours.attendent'), d.file, t('encours.file_vide'), ligneFile),
    bloc('routines', t('encours.routines'), d.routines, t('encours.routines_vide'), ligneRoutine),
    bloc('incidents', t('encours.incidents'), d.incidents, t('encours.incidents_vide'), ligneIncident));
}

async function recharger() {
  if (!coque?.isConnected) return;
  const moi = ++version;
  try {
    const d = await api('/travaux');
    if (moi === version && coque.isConnected) dessiner(d);
  } catch (e) { erreur(e.message); }
}

export async function dessinerTravaux(zone) {
  if (!coque || coque.parentNode !== zone) {
    coque = h('div', { class: 'aujourdhui travaux', 'data-id': 'travaux' }, h('p', { class: 'vide' }, '…'));
    remplacer(zone, coque);
  }
  await recharger();
}
// Appelé par app.js sur les événements serveur ; ne fait rien si l'écran n'est pas affiché.
export const actualiserTravaux = () => { if (coque?.isConnected) recharger(); };
