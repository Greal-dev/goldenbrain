// Rôle : ponts entre tâches et notes — clic sur un wikilink ou un chemin de note (fiches, conversations, notes),
// chemin vault d'une tâche ou d'un conteneur. Frontières : API /vault (résolution paresseuse au clic, jamais au rendu).
import { ouvrirNote, erreur } from './store.js';
import { ouvert } from './interface.js';
import { api } from './api.js';
import { t } from './langues.js';

const enc = encodeURIComponent;

export async function resoudre(lien, depuis = '') {
  if (!ouvert('notes')) return null;
  try { return (await api(`/vault/resoudre?lien=${enc(lien)}&depuis=${enc(depuis)}`)).chemin || null; } catch (e) { erreur(e.message); return null; }
}
export async function ouvrirLien(lien, depuis = '') {
  const chemin = await resoudre(lien, depuis);
  if (chemin) ouvrirNote(chemin); else erreur(t('ponts.introuvable', { lien }));
}

// Chemin du fichier d'une tâche relatif au vault : le chemin renvoyé est absolu, le conteneur est relatif.
export function cheminVaultTache(tache) {
  const c = String(tache.chemin || '').replace(/\\/g, '/');
  const i = tache.conteneur ? c.indexOf(`/${tache.conteneur}/`) : -1;
  if (i >= 0) return c.slice(i + 1);
  const m = /\/Vault\/(.+)$/i.exec(c);
  return m ? m[1] : c;
}
export const cheminContexte = (conteneurId) => `${conteneurId}/contexte.md`;

// Un seul écouteur pour toute l'interface : les liens sont posés en HTML par md.js (a.wl).
export function initPonts(creerNote) {
  document.addEventListener('click', (e) => {
    const a = e.target.closest?.('a.wl');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    e.preventDefault();
    const d = a.dataset;
    if (d.note) ouvrirNote(d.note);
    else if (d.chemin) ouvrirLien(d.chemin);
    else if (d.lien) ouvrirLien(d.lien);
    else if (d.fichier) import('./lecteur.js').then((m) => m.ouvrirFichier(d.fichier, true)); // hors racines : le motif du serveur s'affiche
    else if (d.creer) creerNote(d.creer);
  });
}
