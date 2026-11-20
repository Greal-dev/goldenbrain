// Rôle : galerie de modèles du formulaire « Nouvelle tâche » — un clic pré-remplit titre et description (la mission) ; rien n'est créé.
// Frontières : GET /api/modeles (un fichier Markdown par modèle, dossier `modeles/`, INV-MODELES-1). INV-WEB-1 : tout passe par h().
import { h } from './dom.js';
import { api } from './api.js';
import { t } from './langues.js';


/** Galerie, ou null si aucun modèle ; `choisir(modele, carte)` reçoit le modèle cliqué. */
export async function galerieModeles(choisir) {
  let liste = [];
  try { liste = await api('/modeles'); } catch { return null; } // sans modèles, le formulaire reste tel quel
  if (!liste.length) return null;
  const grille = h('div', { class: 'modeles', role: 'list' });
  for (const m of liste) {
    const carte = h('button', { class: 'modele', type: 'button', role: 'listitem', 'data-id': `modele-${m.id}`, title: m.resume,
      onclick: () => { grille.querySelectorAll('.choisi').forEach((x) => x.classList.remove('choisi')); carte.classList.add('choisi'); choisir(m, carte); } },
    h('b', null, m.titre), m.resume ? h('span', null, m.resume) : null);
    grille.append(carte);
  }
  return h('div', { 'data-id': 'modeles' }, h('div', { class: 'note' }, h('b', null, t('modeles.titre')), ' — ', t('modeles.aide')), grille);
}
