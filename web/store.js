// Rôle : état partagé de l'interface et petit bus d'événements (découple les modules).
// Frontières : aucune E/S, aucun DOM.
let arbreBrut = [], arbreVu = null;
export const S = {
  // Arbre tel que l'écran le voit : `vueArbre` (posée par interface.js) retire les opérations en mode simple.
  get arbre() { return (arbreVu ??= S.vueArbre(arbreBrut)); },
  set arbre(v) { arbreBrut = v; arbreVu = null; },
  invaliderArbre() { arbreVu = null; },
  arbreCharge: false, // vrai dès qu'une réponse de /arbre est arrivée : distingue « vault vide » de « en chargement »
  vueArbre: (n) => n,
  etat: { tours: [], en_file: 0, a_moi: 0, en_retard: 0, propositions: 0 }, props: [],
  toutes: false, selection: null, recherche: '', filtreAMoi: false,
  vue: 'cascade', portee: null, centre: null, filtres: new Set(), marque: null, // marque : clé du dernier élément déplacé (mise en évidence brève)
  // volet droit sans tâche : 'reglages' | 'cascade' (portée = "type:id" ou null) | 'aujourdhui' | 'compagnon' | 'decisions' | 'equipe' | 'note' (S.note = chemin) | 'recherche' (S.requete)
  onglet: localStorage.getItem('orch.onglet') === 'notes' ? 'notes' : 'taches', note: null, requete: '',
  interface: null, // {mode, familles, propositions} : valeurs effectives du serveur (interface.js)
  garde: null, // () => bool : l'éditeur de note y refuse (ou fait confirmer) toute navigation qui perdrait des modifications
};
const ecouteurs = {};
export const on = (nom, f) => (ecouteurs[nom] ??= []).push(f);
export const emit = (nom, donnee) => (ecouteurs[nom] || []).forEach((f) => f(donnee));
export const erreur = (m, type = 'erreur') => emit('banniere', { m, type });
const quitter = () => !S.garde || S.garde();
export function ouvrir(id) {
  if (!quitter()) return false;
  S.selection = id; if (id == null) { S.vue = 'cascade'; S.portee = null; } emit('selection', id); return true;
}
export function ouvrirVue(vue, portee = null) {
  if (!quitter()) return false;
  S.selection = null; S.vue = vue; S.portee = portee; emit('selection', null); return true;
}
// Graphe du second cerveau : global (centre nul) ou local autour d'une note ou d'une tâche.
export function ouvrirGraphe(centre = null) {
  if (S.vue === 'graphe' && S.centre === centre && !S.selection) return true;
  if (!quitter()) return false;
  S.selection = null; S.vue = 'graphe'; S.centre = centre; S.portee = null; emit('selection', null); return true;
}
export function ouvrirNote(chemin, editer = false) {
  if (S.vue === 'note' && S.note === chemin && !S.selection) return true; // même note : jamais de rechargement sous les doigts de l'éditeur
  if (!quitter()) return false;
  S.selection = null; S.vue = 'note'; S.note = chemin; S.portee = null; S.editer = editer; emit('selection', null); return true;
}
export function ouvrirRecherche(q) {
  if (!quitter()) return false;
  S.selection = null; S.vue = 'recherche'; S.requete = q; S.portee = null; emit('selection', null); return true;
}
export function fixerOnglet(o) { S.onglet = o; localStorage.setItem('orch.onglet', o); emit('onglet', o); }
export function fixerToutes(v) { S.toutes = v; localStorage.setItem('orch.toutes', v ? '1' : '0'); emit('toutes'); emit('recharger-arbre'); }
export const cleNoeud = (n) => `${n.type}:${n.id}`;

export function* parcourir(noeuds) {
  for (const n of noeuds) { yield n; yield* parcourir(n.enfants || []); }
}
export function chemin(noeuds, pred, acc = []) {
  for (const n of noeuds) {
    if (pred(n)) return [...acc, n];
    const r = chemin(n.enfants || [], pred, [...acc, n]);
    if (r) return r;
  }
  return null;
}
export const noeudTache = (id) => chemin(S.arbre, (n) => n.type === 'tache' && n.id === id)?.at(-1) ?? null;
export function titreTache(id) { return noeudTache(id)?.titre || id; }
