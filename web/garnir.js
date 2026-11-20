// Rôle : phrase traduite portant des éléments (lien, gras, code) : garnir(t('cle'), { nom: noeud }) coupe le texte sur `{nom}`
// et glisse chaque nœud à sa place — l'ordre des mots change selon la langue (INV-LANGUE-1).
// Frontières : rend un tableau pour h()/remplacer(), n'écrit rien ; la clé reste littérale chez l'appelant (la porte la vérifie).
export function garnir(texte, noeuds) {
  return texte.split(/(\{\w+\})/).map((m) => { const k = /^\{(\w+)\}$/.exec(m)?.[1]; return k && k in noeuds ? noeuds[k] : m; }).filter((x) => x !== '');
}
