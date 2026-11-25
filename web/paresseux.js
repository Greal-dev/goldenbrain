// Rôle : chargement à la demande des modules d'écran (INV-REACTIVITE-1) — le premier affichage ne charge que ce que l'écran montre ;
// les écrans (équipe, réglages, décisions, guide, graphe…), la fiche d'une tâche et les services de fond arrivent quand on en a besoin
// ou juste après le premier affichage. Sans étape de construction : `import()` natif, un module à la fois.
// Frontières : ne connaît aucun module en particulier ; `init` (facultatif) s'exécute une seule fois, avant que le module soit dit prêt,
// pour qu'aucun événement n'atteigne un module non initialisé.
const promesses = new Map(), prets = new Map();

export function charger(nom, init = null) {
  if (!promesses.has(nom)) {
    promesses.set(nom, import(`./${nom}.js`).then((m) => { init?.(m); prets.set(nom, m); return m; }).catch((e) => { promesses.delete(nom); throw e; }));
  }
  return promesses.get(nom);
}
/** Le module s'il est déjà chargé (et initialisé), sinon null : un événement qui arrive avant n'a rien à mettre à jour. */
export const pret = (nom) => prets.get(nom) ?? null;
/** Appel d'une fonction d'un module seulement s'il est prêt. */
export const sur = (nom, fonction) => (...a) => prets.get(nom)?.[fonction](...a);
/** Comme `sur`, mais charge le module s'il manque : pour un événement rare dont le module peut déjà vivre (importé par un écran) sans être passé par `charger`. */
export const surCharge = (nom, fonction) => (...a) => { charger(nom).then((m) => m[fonction](...a), () => {}); };
