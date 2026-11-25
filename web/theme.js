// Rôle : appliquer le thème avant le premier affichage (script classique bloquant : la CSP interdit le script en ligne).
// Frontières : ne lit que localStorage ; n'écrit que l'attribut data-theme de <html>.
try { const t = localStorage.getItem('orch.theme'); if (t === 'clair' || t === 'sombre') document.documentElement.dataset.theme = t; } catch { /* stockage refusé : thème du système */ }
