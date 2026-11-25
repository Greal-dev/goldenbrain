// Rôle : appliquer le thème avant le premier affichage (script classique bloquant : la CSP interdit le script en ligne).
// Frontières : ne lit que localStorage et l'adresse ; n'écrit que des attributs de <html> et, en essai, une feuille.
// INV-DIRECTION-1 : ?theme=a|b|c charge une direction visuelle d'essai (web/directions/<x>.css) ; sans ce paramètre,
// rien n'est chargé et l'interface par défaut reste inchangée, sans coût.
try { const t = localStorage.getItem('orch.theme'); if (t === 'clair' || t === 'sombre') document.documentElement.dataset.theme = t; } catch { /* stockage refusé : thème du système */ }
{
  const d = new URLSearchParams(location.search).get('theme');
  if (d === 'a' || d === 'b' || d === 'c') {
    document.documentElement.dataset.direction = d;
    document.write(`<link rel="stylesheet" href="directions/${d}.css">`); // dans <head>, avant le premier affichage : pas d'éclair
  }
}
