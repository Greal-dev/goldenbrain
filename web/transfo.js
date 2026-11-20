// Rôle : promotion d'une tâche en projet (avec découpage par l'agent) et réduction d'un projet en tâche (avec contraction).
// Parcours commun : avis de l'agent rapide -> dialogue -> appel -> ligne d'information. Frontières : API /taches/{id}/promouvoir,
// /conteneurs/reduire, /conseil (via conseil.js) ; l'arbre est relu après chaque geste. INV-TRANSFO-1 : l'interface ne crée aucun ticket.
import { t, tn } from './langues.js';
import { h, nomDe } from './dom.js';
import { S, emit, erreur, ouvrir, chemin, parcourir } from './store.js';
import { ouvert } from './interface.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { consulter } from './conseil.js';
import { info, effacerInfo } from './info.js';

const enc = encodeURIComponent;
const suivis = new Map(); // tâche -> {nom, cont} : promotions dont le découpage est attendu (pour nommer le projet dans le compte rendu)

async function relireArbre() {
  try { S.arbre = (await api(`/arbre?toutes=${S.toutes ? 1 : 0}`)).noeuds; emit('arbre'); } catch (e) { erreur(e.message); }
}

// --- promotion ---
export async function promouvoir(tache) {
  const av = await consulter('promouvoir', { tache: tache.id }, t('transfo.merite_projet', { titre: tache.titre }));
  if (!av) return null;
  const v = await formulaire({
    titre: t('transfo.promouvoir_titre'), valider: t('transfo.promouvoir'),
    texte: t('transfo.promouvoir_texte'),
    champs: [
      { nom: 'nom', label: t('transfo.nom_projet'), valeur: tache.titre, requis: true },
      { nom: 'decouper', label: t('transfo.decouper'), type: 'checkbox', valeur: true },
    ],
  });
  if (!v) return null;
  const nom = v.nom.trim();
  let res;
  try { res = await post(`/taches/${enc(tache.id)}/promouvoir`, { nom, decouper: v.decouper }); } catch (e) { erreur(t('transfo.promotion_impossible', { motif: e.message })); return null; }
  const cont = typeof res.conteneur === 'string' ? res.conteneur : res.tache?.conteneur;
  if (v.decouper) suivis.set(tache.id, { nom, cont });
  info([t(v.decouper ? 'transfo.projet_decoupe' : 'transfo.projet', { nom }), av.phrase ? ` ${av.phrase}` : ''], [], v.decouper ? 0 : 8000);
  await relireArbre();
  emit('deplace', { cle: `tache:${tache.id}`, depuis: null }); // déplie le projet jusqu'à la tâche, qui reste ouverte
  return res;
}

const DOSSIER_ARCHIVES = 'Archives/';
const DEMANDE_DECOUPAGE = [
  'Le découpage précédent est insuffisant. Découpe le travail de ce projet en tickets autonomes et vérifiables, au moins deux, autant que nécessaire, sans reprendre les tickets déjà présents, et termine par :',
  '<decoupage>', 'resume: une phrase sur le projet', '- titre: …', '  ' + 'description: …', '- titre: …', '  ' + 'description: …', '</decoupage>',
].join('\n');

async function relancerDecoupage(tache) {
  try {
    await post(`/taches/${enc(tache)}/messages`, { texte: DEMANDE_DECOUPAGE });
    emit('message-envoye', { tache, texte: DEMANDE_DECOUPAGE });
    emit('recharger');
    info(t('transfo.decoupage_envoye'), [], 0);
  } catch (e) { erreur(e.message); }
}

// SSE `tour_fin` : seul un tour de découpage porte `decoupage` (nombre de tickets créés, ou « insuffisant »).
export async function evtTransfo(e) {
  if (e.decoupage == null) return;
  const p = suivis.get(e.tache);
  suivis.delete(e.tache);
  if (e.decoupage === 'insuffisant') {
    info(t('transfo.decoupage_insuffisant'), [{ libelle: t('transfo.relancer'), action: () => relancerDecoupage(e.tache) }], 60000);
    return;
  }
  const n = Number(e.decoupage);
  info(p?.nom ? tn('transfo.tickets_crees_dans', n, { nom: p.nom }) : tn('transfo.tickets_crees', n), [], 10000);
  await relireArbre();
  const cont = p?.cont ?? chemin(S.arbre, (x) => x.type === 'tache' && x.id === e.tache)?.slice(0, -1).findLast((x) => x.type === 'conteneur')?.id;
  if (cont) { emit('deplace', { cle: `conteneur:${cont}`, depuis: null }); emit('deplier', `conteneur:${cont}`); }
}

// --- réduction ---
const fermee = (x) => x.statut === 'cloture' || x.statut === 'abandonne' || (x.statut === 'fait' && !x.a_valider);

// Ce qui sera archivé : tâches du projet (arbre complet) et autres notes du dossier (total récursif moins les tâches et le contexte).
async function bilan(c) {
  let racines = S.arbre;
  try { racines = (await api('/arbre?toutes=1')).noeuds; } catch { /* on se contente de l'arbre affiché */ }
  const noeud = chemin(racines, (x) => x.type === 'conteneur' && x.id === c.id)?.at(-1);
  const taches = [...parcourir(noeud?.enfants || [])].filter((x) => x.type === 'tache');
  const fer = taches.filter(fermee).length, ouv = taches.length - fer;
  let autres = null;
  if (ouvert('notes')) try {
    const d = await api(`/vault/dossier?chemin=${enc(c.id)}`);
    autres = Math.max(0, d.notes.length + d.dossiers.reduce((s, x) => s + x.notes, 0) - taches.length - 1);
  } catch { /* nombre inconnu : on ne l'affiche pas */ }
  return { ouv, fer, autres };
}

export async function reduire(c) {
  const av = await consulter('reduire', { conteneur: c.id }, t('transfo.peut_etre_tache', { titre: c.titre }));
  if (!av) return null;
  const b = await bilan(c);
  const dest = `${DOSSIER_ARCHIVES}${nomDe(c.id)}-ARCHIVE-${new Date().toLocaleDateString('sv-SE')}`;
  const v = await formulaire({
    titre: t('transfo.reduire_titre', { titre: c.titre }), valider: t('transfo.reduire'),
    texte: t('transfo.reduire_texte'),
    corps: h('div', { class: 'rappel-archive' },
      h('p', null, t('transfo.sera_archive'), h('b', null, tn('transfo.ouvertes', b.ouv)), ', ',
        h('b', null, tn('transfo.fermees', b.fer)), b.autres == null ? '' : [', ', h('b', null, tn('transfo.autres_notes', b.autres))], '.'),
      h('p', null, t('transfo.destination'), h('code', null, `${dest}/`), t('transfo.suffixe'))),
    champs: [{ nom: 'point_git', label: t('transfo.point_restauration'), type: 'checkbox', valeur: true }],
  });
  if (!v) return null;
  info(t('transfo.reduction_en_cours', { titre: c.titre }), [], 0);
  let res;
  try { res = await post('/conteneurs/reduire', { conteneur: c.id, point_git: v.point_git }); } catch (e) { effacerInfo(); erreur(t('transfo.reduction_impossible', { motif: e.message })); return null; }
  await relireArbre();
  ouvrir(res.tache.id);
  info([t('transfo.tache_archivee', { titre: c.titre, archive: res.archive }), av.phrase ? ` ${av.phrase}` : ''], [], 0);
  return res;
}

