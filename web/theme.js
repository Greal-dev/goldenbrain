// Rôle : appliquer le thème choisi (clair, sombre, ou celui du système) avant le premier rendu.
// Frontières : script classique et bloquant dans <head> (la CSP interdit le script en ligne) ; ne lit que localStorage.
// Le choix se fait dans Réglages (reglages.js) ; les couleurs suivent `color-scheme` (style.css).
try { const t = localStorage.getItem('orch.theme'); if (t === 'clair' || t === 'sombre') document.documentElement.dataset.theme = t; } catch { /* stockage refusé : thème du système */ }
