// Rôle : état « interface » (mode simple / avancé, familles débrayées, politique des propositions) et ses applications à l'écran.
// Frontières : GET/PUT /api/interface seulement ; le serveur reste maître (INV-INTERFACE-1 : une famille fermée répond 409),
// ces fonctions évitent les appels voués à l'échec et masquent ce qui n'a plus lieu d'être. Aucun HTML (INV-WEB-1).
import { S, emit } from './store.js';
import { api } from './api.js';
import { reglerRetour } from './dom.js';
import { t, etatInterfaceInitial } from './langues.js';

export const FAMILLES = ['equipe', 'liens', 'alignement', 'jardinage', 'moteurs', 'notes', 'transformations', 'conseil'];

// Tant que l'état n'est pas lu (ou si la lecture échoue), tout est ouvert : le serveur tranche par 409.
export const ouvert = (f) => S.interface?.familles?.[f] !== false;
export const simple = () => S.interface?.mode === 'simple';
export const montrerPropositions = () => (S.interface?.propositions ?? 'montrer') === 'montrer';

// En simple, « conteneur » et « opération » se disent « projet » (un seul vocabulaire : projet, tâche).
export const mot = (type) => (type === 'tache' ? t('interface.mot_tache') : type === 'casquette' ? t('interface.mot_casquette')
  : simple() ? t('interface.mot_projet') : type === 'operation' ? t('interface.mot_operation') : t('interface.mot_projet'));

// En simple, les opérations disparaissent de l'arbre affiché : leurs enfants remontent au niveau de la casquette.
export function sansOperations(noeuds) {
  if (!simple()) return noeuds;
  return noeuds.flatMap((n) => (n.type === 'operation' ? sansOperations(n.enfants || [])
    : [n.enfants ? { ...n, enfants: sansOperations(n.enfants) } : n]));
}
S.vueArbre = (n) => sansOperations(n);
export const filVisible = (fil) => (simple() ? fil.filter((s) => s.type !== 'operation') : fil);

// Classes sur <body> : le CSS fait le reste (`.sans-<famille> .f-<famille> { display: none }`).
function poser() {
  const c = document.body.classList;
  c.toggle('mode-simple', simple());
  c.toggle('mode-avance', !simple());
  for (const f of FAMILLES) c.toggle(`sans-${f}`, !ouvert(f));
  c.toggle('sans-propositions', !montrerPropositions());
  document.getElementById('arbre')?.setAttribute('aria-label', simple() ? t('interface.arbre_simple') : t('interface.arbre_avance'));
}

function adopter(etat) {
  if (!etat || JSON.stringify(etat) === JSON.stringify(S.interface)) return false;
  reglerRetour(etat.statut_retour);  // INV-STATUT-1
  S.interface = etat;
  S.invaliderArbre();
  poser();
  emit('interface', etat);
  return true;
}

export async function chargerInterface() { adopter(etatInterfaceInitial() || await api('/interface')); }
export async function changerInterface(corps) { adopter(await api('/interface', { methode: 'PUT', corps })); }
