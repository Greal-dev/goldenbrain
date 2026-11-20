// Rôle : routines programmées dans l'interface — pastille d'horloge de l'arbre, création, bloc du détail
// (programme, pause / reprise, « Exécuter maintenant », historique des exécutions).
// Frontières : lit le repère `routine` des nœuds (INV-ROUTINE-5) et l'API /api/routines ; aucune échéance
// n'est calculée ici, le serveur la fournit (INV-ROUTINE-2).
import { t, LOCALE } from './langues.js';
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { emit, erreur, ouvrir } from './store.js';

const enc = encodeURIComponent;
const ISSUES = { reussie: t('routines.issue_reussie'), echouee: t('routines.issue_echouee'), en_cours: t('routines.issue_en_cours'), sautee: t('routines.issue_sautee') };

// « aujourd’hui 08:00 », « demain 08:00 », sinon « lun. 23/11 08:00 ».
export function quand(iso) {
  if (!iso) return '';
  const d = new Date(iso), j = new Date();
  const hm = d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
  const ecart = Math.round((new Date(d.toDateString()) - new Date(j.toDateString())) / 864e5);
  if (ecart === 0) return t('routines.aujourdhui', { heure: hm });
  if (ecart === 1) return t('routines.demain', { heure: hm });
  return t('routines.date_heure', { date: d.toLocaleDateString(LOCALE, { weekday: 'short', day: '2-digit', month: '2-digit' }), heure: hm });
}

export function libelleRoutine(n) {
  const r = n.routine;
  if (r.etat === 'en-pause') return t('routines.en_pause');
  if (r.erreur) return t('routines.illisible');
  return r.prochaine ? `⏰ ${quand(r.prochaine)}` : t('routines.sans_echeance');
}

// Pastille de l'arbre : état de la routine à la place du statut, point de la dernière issue.
export function badgeRoutine(n) {
  const r = n.routine, d = r.derniere;
  const titre = [t('routines.titre_programme', { programme: r.programme }), r.etat === 'en-pause' ? t('routines.titre_pause') : t('routines.titre_prochaine', { quand: quand(r.prochaine) || '—' }),
    r.erreur ? t('routines.titre_illisible', { erreur: r.erreur }) : '', d ? t('routines.titre_derniere', { quand: quand(d.a), issue: ISSUES[d.issue] || d.issue }) : t('routines.jamais')].filter(Boolean).join('\n');
  return h('span', { class: `badge-st bs-routine${r.etat === 'en-pause' ? ' pause' : ''}`, 'data-statut': 'routine', title: titre },
    d ? h('span', { class: `issue i-${d.issue}`, 'aria-label': t('routines.aria_derniere', { issue: ISSUES[d.issue] || d.issue }) }) : null,
    libelleRoutine(n));
}

const AIDE = t('routines.aide'); // syntaxe lue par le serveur : exemples identiques dans toutes les langues

export async function nouvelleRoutine(conteneur = '') {
  let conteneurs = [];
  try { conteneurs = await api('/conteneurs'); } catch (e) { erreur(e.message); }
  const v = await formulaire({
    titre: t('routines.nouvelle_titre'), valider: t('routines.creer'), texte: t('routines.texte_programme', { aide: AIDE }),
    champs: [
      { nom: 'titre', label: t('routines.champ_titre'), requis: true },
      { nom: 'consigne', label: t('routines.champ_consigne'), type: 'textarea', requis: true },
      { nom: 'programme', label: t('routines.champ_programme'), requis: true, aide: t('routines.programme_exemple') },
      { nom: 'conteneur', label: t('routines.champ_projet'), type: 'select', valeur: conteneur,
        options: [{ valeur: '', libelle: t('routines.arrivee') }, ...conteneurs.map((c) => ({ valeur: c.id, libelle: c.titre, groupe: c.casquette || '' }))] },
      { nom: 'contexte', label: t('routines.champ_conversation'), type: 'select', valeur: 'suite',
        options: [{ valeur: 'suite', libelle: t('routines.conv_suite') }, { valeur: 'neuf', libelle: t('routines.conv_neuf') }] },
      { nom: 'rattrapage', label: t('routines.champ_rattrapage'), type: 'select', valeur: 'une',
        options: [{ valeur: 'une', libelle: t('routines.rattrapage_une') }, { valeur: 'aucune', libelle: t('routines.rattrapage_aucune') }] },
    ],
  });
  if (!v) return;
  try {
    const r = await post('/routines', { titre: v.titre.trim(), consigne: v.consigne.trim(), programme: v.programme.trim(),
      conteneur: v.conteneur || null, contexte: v.contexte, rattrapage: v.rattrapage });
    emit('recharger');
    ouvrir(r.id);
  } catch (e) { erreur(e.message); }
}

// Bouton « Transformer en routine » : la tâche existante devient routine sur place (même note, même session).
export async function convertirEnRoutine(id) {
  const v = await formulaire({
    titre: t('routines.transformer_titre'), valider: t('routines.transformer'), texte: t('routines.transformer_texte', { aide: AIDE }),
    champs: [
      { nom: 'programme', label: t('routines.champ_programme'), requis: true, aide: t('routines.programme_exemple') },
      { nom: 'contexte', label: t('routines.champ_conversation'), type: 'select', valeur: 'suite',
        options: [{ valeur: 'suite', libelle: t('routines.conv_suite') }, { valeur: 'neuf', libelle: t('routines.conv_neuf') }] },
      { nom: 'rattrapage', label: t('routines.champ_rattrapage'), type: 'select', valeur: 'une',
        options: [{ valeur: 'une', libelle: t('routines.rattrapage_une') }, { valeur: 'aucune', libelle: t('routines.rattrapage_aucune') }] },
    ],
  });
  if (!v) return false;
  try { await post(`/routines/${enc(id)}/convertir`, { programme: v.programme.trim(), contexte: v.contexte, rattrapage: v.rattrapage }); return true; }
  catch (e) { erreur(e.message); return false; }
}

// Bloc du détail : rempli après lecture de /api/routines/{id} ; `apres` recharge la tâche et l'arbre.
export function blocRoutine(id, apres) {
  const el = h('section', { class: 'routine-bloc', 'aria-label': t('routines.bloc_aria') });
  const agir = async (f) => { try { await f(); } catch (e) { erreur(e.message); } apres(); }; // apres() redessine le détail, donc ce bloc
  async function dessiner() {
    let r;
    try { r = await api(`/routines/${enc(id)}`); } catch (e) { erreur(e.message); return; }
    const prog = h('input', { type: 'text', value: r.programme, 'aria-label': t('routines.champ_programme'), title: AIDE, class: 'r-prog' });
    const pause = r.etat === 'en-pause';
    const b = (txt, f, cls = '') => h('button', { type: 'button', class: `btn petit ${cls}`, onclick: () => agir(f) }, txt);
    remplacer(el,
      h('div', { class: 'r-tete' }, h('span', { class: 'r-horloge', 'aria-hidden': 'true' }, '⏰'),
        h('strong', null, pause ? t('routines.titre_bloc_pause') : t('routines.titre_prochaine', { quand: quand(r.prochaine) || '—' })),
        r.erreur ? h('span', { class: 'r-erreur', role: 'alert' }, t('routines.titre_illisible', { erreur: r.erreur })) : null),
      h('div', { class: 'r-actions' }, prog,
        b(t('routines.enregistrer'), () => post(`/routines/${enc(id)}/modifier`, { programme: prog.value })),
        b(pause ? t('routines.reprendre') : t('routines.mettre_pause'), () => post(`/routines/${enc(id)}/modifier`, { pause: !pause })),
        b(t('routines.executer'), () => post(`/routines/${enc(id)}/executer`), 'primaire'),
        b(t('routines.retirer'), () => post(`/routines/${enc(id)}/retirer`))),
      h('details', { class: 'r-hist' }, h('summary', null, t('routines.historique', { n: r.historique.length })),
        r.historique.length ? h('ul', null, r.historique.map((x) => h('li', { class: `i-${x.issue}` },
          h('span', { class: `issue i-${x.issue}`, 'aria-hidden': 'true' }),
          (() => { const l = t('routines.ligne_historique', { quand: quand(x.a), origine: x.origine || t('routines.origine_programmee'), issue: ISSUES[x.issue] || x.issue }); return x.motif ? t('routines.ligne_motif', { ligne: l, motif: x.motif }) : l; })(),
          x.session ? h('span', { class: 'session', title: t('routines.session_titre') }, t('routines.session', { id: x.session.slice(0, 8) })) : null)))
          : h('p', { class: 'note' }, t('routines.jamais'))));
  }
  dessiner();
  return el;
}
