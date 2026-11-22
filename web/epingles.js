// Rôle : épinglage de tâches propre à CET appareil (localStorage : liste d'identifiants, jamais de contenu du vault).
// Frontières : aucun appel serveur ; partagé par compagnon.js (étoiles de l'arbre) et travail.js (vue « Travail en cours »).
const CLE = 'orch.compagnon.epingles';
export const epingles = () => { try { const l = JSON.parse(localStorage.getItem(CLE) || '[]'); return Array.isArray(l) ? l.filter((x) => typeof x === 'string') : []; } catch { return []; } };
export const estEpingle = (id) => epingles().includes(id);
export function basculerEpingle(id) {
  const l = epingles(), n = l.includes(id) ? l.filter((x) => x !== id) : [...l, id];
  localStorage.setItem(CLE, JSON.stringify(n));
  return n.includes(id);
}
export const oublierEpingles = () => localStorage.removeItem(CLE);

