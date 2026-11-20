// Rôle : carte « Revues » d'une tâche (dernier avis par persona) et dialogue « Solliciter… ».
// Frontières : API seule (/equipe, /taches/{id}/solliciter) ; l'appelant redessine à partir de la Tache.
import { h, heure } from './dom.js';
import { erreur } from './store.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { t, tn } from './langues.js';

const VERDICTS = { ok: t('revues.verdict_ok'), reserves: t('revues.verdict_reserves'), en_cours: t('revues.verdict_en_cours'), echec: t('revues.verdict_echec') };
const ORIGINES = { revue: t('revues.origine_revue'), validation: t('revues.origine_validation'), demande: t('revues.origine_demande') };

export function carteRevues(tache) {
  const l = tache.revues || [];
  return h('section', { class: 'revues-carte', 'aria-label': t('revues.titre') },
    h('h3', null, t('revues.titre'), tache.renvois ? ' · ' + tn('revues.renvois', tache.renvois) : ''),
    l.length ? h('ul', { class: 'avis-liste' }, l.map((a) => h('li', { class: 'avis' },
      h('div', { class: 'avis-tete' }, h('b', null, a.nom || a.persona), h('span', { class: `verdict v-${a.verdict}` }, VERDICTS[a.verdict] || a.verdict),
        h('span', { class: 'avis-d' }, [ORIGINES[a.origine], a.date ? heure(a.date) : ''].filter(Boolean).join(' · '))),
      (a.points || []).length ? h('ul', { class: 'points' }, a.points.map((p) => h('li', null, p))) : null)))
      : h('p', { class: 'vide' }, t('revues.aucune')));
}

export async function solliciter(tache) {
  let equipe;
  try { equipe = await api('/equipe'); } catch (e) { erreur(e.message); return false; }
  const actifs = (equipe || []).filter((p) => p.actif);
  if (!actifs.length) { erreur(t('revues.aucun_actif')); return false; }
  const v = await formulaire({
    titre: t('revues.solliciter_titre'), valider: t('revues.solliciter'),
    texte: t('revues.solliciter_texte'),
    champs: [
      { nom: 'persona', label: t('revues.expert'), type: 'select', options: actifs.map((p) => ({ valeur: p.id, libelle: p.nom || p.id })) },
      { nom: 'question', label: t('revues.question'), type: 'textarea', lignes: 3 },
    ],
  });
  if (!v) return false;
  const corps = { persona: v.persona };
  if (v.question.trim()) corps.question = v.question.trim();
  try {
    await post(`/taches/${encodeURIComponent(tache.id)}/solliciter`, corps);
    erreur(t('revues.avis_demande', { nom: actifs.find((p) => p.id === v.persona)?.nom || v.persona }), 'info');
    return true;
  } catch (e) { erreur(e.message); return false; }
}
