// Rôle : appliquer le thème avant le premier affichage (script classique bloquant : la CSP interdit le script en ligne).
// Frontières : ne lit que localStorage ; n'écrit que l'attribut data-theme de <html> et la variable --l-arbre (largeur du volet, réglée par volet_largeur.js, chargé après le premier affichage).
try { const t = localStorage.getItem('orch.theme'); if (t === 'clair' || t === 'sombre') document.documentElement.dataset.theme = t; } catch { /* stockage refusé : thème du système */ }
try { const l = parseInt(localStorage.getItem('gb.largeur-arbre'), 10); if (l >= 200 && l <= 760) document.documentElement.style.setProperty('--l-arbre', l + 'px'); } catch { /* idem */ }
