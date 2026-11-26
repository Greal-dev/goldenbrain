// Rôle : lecture « à qui la main » (INV-MAIN-1) — l'unique pastille d'état d'une tâche (quatre valeurs : L'IA travaille,
// En file, Action humaine nécessaire, Terminé), sa phrase, et les gestes « Confier à l'IA » / « Renvoyer à l'IA » (INV-MAIN-5).
// Frontières : la lecture est calculée par le serveur (champ `main` des nœuds, du détail et d'Aujourd'hui) ; aucun calcul d'état
// ici ; l'envoi passe par POST /taches/{id}/ia (consigne facultative), jamais par un agent.
import { t } from './langues.js';
import { h } from './dom.js';
import { post } from './api.js';
import { formulaire } from './dialogue.js';
import { erreur, emit } from './store.js';

export const libelleMain = (m) => (m ? m.libelle || t(`main.${m.cle}`) : ''); // le serveur donne un libellé propre à « terminé pour l'instant », au groupe, à « à faire par vous »
export const infoMain = (m) => [m.phrase, m.reprise && t('main.reprise', { quand: m.reprise })].filter(Boolean).join('\n');
export const geste = (m) => (m && (m.geste === 'confier' || m.geste === 'renvoyer') ? m.geste : null);

// La pastille : `extra` ajoute des classes (l'en-tête réutilise `etat` pour sa mise en page).
export const pastilleMain = (m, extra = '', clic = null) => (m ? h('span', { class: `main main-${m.cle}${extra ? ' ' + extra : ''}${clic && geste(m) ? ' main-clic' : ''}`, 'data-main': m.cle, 'data-motif': m.motif || '', title: infoMain(m), ...(clic && geste(m) ? { role: 'button', tabindex: '0', onclick: clic } : {}) }, libelleMain(m)) : null);  // clic : sur téléphone, la pastille porte le geste (le bouton d'en-tête y est masqué)
export const phraseMain = (m) => (m && (m.cle !== 'termine' || m.motif === 'veille' || m.motif === 'groupe') ? h('span', { class: 'main-phrase', 'data-id': 'main-phrase', title: m.phrase }, m.phrase) : null);

export async function envoyerIA(id, m, apres) {
  const g = geste(m) || 'renvoyer';
  const v = await formulaire({ titre: t(`main.${g}`), valider: t(`main.${g}`), texte: t('main.consigne_texte'),
    champs: [{ nom: 'consigne', label: t('main.consigne'), type: 'textarea', lignes: 3, aide: t('main.consigne_aide') }] });
  if (!v) return false;
  try { await post(`/taches/${encodeURIComponent(id)}/ia`, { consigne: (v.consigne || '').trim() }); } catch (e) { erreur(e.message); return false; }
  emit('recharger'); if (apres) apres();
  return true;
}

export const boutonIA = (id, m, apres, cls = '', toujours = false) => (geste(m) && (m.suggere !== false || toujours) // INV-MAIN-7 : « Confier à l'IA » d'une tâche tenue par l'utilisateur n'est jamais suggéré en liste
  ? h('button', { class: `btn petit main-ia-btn${cls ? ' ' + cls : ''}`, type: 'button', 'data-id': 'main-ia', 'data-geste': geste(m), title: t('main.ia_titre'), onclick: (e) => { e.stopPropagation(); envoyerIA(id, m, apres); } }, t(`main.${geste(m)}`))
  : null);
