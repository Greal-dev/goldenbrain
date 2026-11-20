// Curseur « Moi / IA » d'une tâche et « Confier la suite ».
// Rôle : dessiner le curseur et la pastille 👤 ; appeler les routes /executant et /confier.
// Frontières : ne lance aucun tour lui-même (le serveur décide) ; la vue tâche (detail.js) l'intègre.
// Invariant porté : INV-EXECUTANT-1 (tâche « Moi » : aucun agent n'y travaille ; la conversation est inactive).
import { h } from './dom.js';
import { post } from './api.js';
import { formulaire } from './dialogue.js';
import { t, tn } from './langues.js';

const enc = encodeURIComponent;
export const humain = (tk) => (tk?.executant || 'ia') === 'humain';

export function pastilleMoi(n) {
  return humain(n) ? h('span', { class: 'pastille-moi', title: t('executant.moi_titre') }, '👤') : null;
}

// `apres(tk)` reçoit la tâche relue ; `erreur(msg)` affiche un échec.
export function curseur(tk, apres, erreur) {
  const moi = humain(tk);
  const bouton = (val, txt, titre) => h('button', {
    type: 'button', class: `cur-ex${(val === 'humain') === moi ? ' actif' : ''}`, 'aria-pressed': String((val === 'humain') === moi), 'data-executant': val, title: titre,
    onclick: () => ((val === 'humain') === moi ? null : (val === 'humain' ? versMoi : versIA)(tk, apres, erreur)),
  }, txt);
  return h('div', { class: 'curseur-ex', role: 'group', 'aria-label': t('executant.qui') },
    bouton('humain', t('executant.moi'), t('executant.moi_aide')),
    bouton('ia', t('executant.ia'), t('executant.ia_aide')));
}

async function versMoi(tk, apres, erreur) {
  try { apres(await post(`/taches/${enc(tk.id)}/executant`, { executant: 'humain' })); } catch (e) { erreur(e.message); }
}

async function versIA(tk, apres, erreur) {
  const n = tk.notes?.length || 0;
  const v = await formulaire({
    titre: t('executant.confier'), valider: t('executant.confier_valider'),
    texte: tn('executant.confier_texte', n),
    champs: [{ nom: 'consigne', label: t('executant.consigne'), aide: t('executant.consigne_aide') }],
  });
  if (!v) return;
  try { await post(`/taches/${enc(tk.id)}/confier`, { consigne: v.consigne || '' }); apres(null); } catch (e) { erreur(e.message); }
}
