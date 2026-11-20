// Rôle : demi-verrou côté interface (INV-VERROU-1) — repère « IA au travail », compteur « IA : n » des ancêtres,
// confirmation d'un geste refusé (409 `occupee`) branchée sur api.js.
// Frontières : lit S.etat.occupees (GET /etat) ; aucune vérification locale avant un geste : le serveur fait foi.
import { h } from './dom.js';
import { S, on, parcourir } from './store.js';
import { brancherOccupee } from './api.js';
import { formulaire } from './dialogue.js';
import { t, tn, LOCALE } from './langues.js';

const heure = (iso) => (iso ? new Date(iso).toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }) : '');
const occupees = () => S.etat.occupees || {};

// Pastille animée sur une tâche qu'un agent travaille ; infobulle « moteur · depuis HH:MM ».
export function repereIA(id) {
  const o = occupees()[id];
  if (!o) return null;
  const txt = [o.terminal ? t('verrou.terminal') : '', o.moteur, o.depuis ? t('verrou.depuis', { heure: heure(o.depuis) }) : ''].filter(Boolean).join(' · ');
  return h('span', { class: 'ia-travail', 'data-ia': '1', ...(o.terminal ? { 'data-terminal': '1' } : {}), role: 'img', title: txt,
    'aria-label': o.terminal ? txt : t('verrou.ia_travail', { txt }) });
}

// Ancêtre (casquette, opération, projet, tâche mère) : nombre de tâches occupées de sa descendance.
export function compteIA(n) {
  const occ = occupees();
  let k = 0;
  for (const x of parcourir(n.enfants || [])) if (x.type === 'tache' && occ[x.id]) k += 1;
  return k ? h('span', { class: 'ia-compte', title: tn('verrou.compte_titre', k) }, t('verrou.compte', { k })) : null;
}

// `f` est rappelée quand l'ensemble des tâches occupées change (flux SSE → GET /etat) : mise à jour en direct.
export function surOccupees(f) {
  let sig = null;
  on('etat', () => { const s = JSON.stringify(occupees()); if (s !== sig) { sig = s; f(); } });
}

brancherOccupee(async (o) => (await formulaire({
  titre: o.terminal ? t('verrou.terminal') : t('verrou.agent'),
  texte: o.terminal ? (o.depuis ? t('verrou.texte_terminal_depuis', { titre: o.titre, heure: heure(o.depuis) }) : t('verrou.texte_terminal', { titre: o.titre }))
    : (o.depuis ? t('verrou.texte_agent_depuis', { titre: o.titre, heure: heure(o.depuis) }) : t('verrou.texte_agent', { titre: o.titre })),
  valider: t('verrou.continuer'), annuler: t('verrou.non'), focus: 'annuler',
})) !== null);
