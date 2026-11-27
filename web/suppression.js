// Rôle : supprimer une tâche ou un projet après confirmation (INV-SUPPR-1) : aperçu, dialogue, appel, arbre relu.
// Frontières : API GET /suppression, POST /taches/{id}/supprimer et /conteneurs/supprimer ; aucun calcul de vault ici.
import { t, tn } from './langues.js';
import { h } from './dom.js';
import { S, emit, erreur, ouvrir } from './store.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { info } from './info.js';

const enc = encodeURIComponent;

function comptes(a) {
  if (a.quoi === 'tache') return a.sous_taches ? [tn('suppression.sous_taches', a.sous_taches)] : [];
  return [a.taches ? tn('suppression.taches', a.taches) : null, a.sous_projets ? tn('suppression.sous_projets', a.sous_projets) : null].filter(Boolean);
}

// `cible` : {tache} ou {conteneur} (identifiant). Rend la réponse du serveur, ou null si rien n'a été supprimé.
export async function supprimer(cible) {
  let a;
  try { a = await api(cible.tache ? `/suppression?tache=${enc(cible.tache)}` : `/suppression?conteneur=${enc(cible.conteneur)}`); } catch (e) { erreur(e.message); return null; }
  const n = a.quoi === 'tache' ? a.sous_taches : a.taches + a.sous_projets;
  const autres = h('p', { class: 'suppr-autres', 'data-id': 'suppr-autres' });
  const majAutres = (mode) => { const k = mode === 'deplacer' ? a.autres_deplacer : a.autres; autres.textContent = k ? tn('suppression.autres', k) : ''; autres.hidden = !k; };
  const champs = n ? [
    { nom: 'mode', type: 'radio', label: t('suppression.descendants', { liste: comptes(a).join(', ') }), valeur: 'deplacer', options: [
      { valeur: 'supprimer', libelle: tn(a.quoi === 'tache' ? 'suppression.supprimer_aussi' : 'suppression.supprimer_contenu', n) },
      { valeur: 'deplacer', libelle: t('suppression.deplacer') }] },
    { nom: 'vers', type: 'select', label: t('suppression.vers'), valeur: a.defaut, options: a.emplacements.map((e) => (
      { valeur: e.id, libelle: e.type === 'conteneur' ? `${e.titre} — ${e.id}` : e.titre, groupe: t(e.type === 'conteneur' ? 'suppression.groupe_projets' : 'suppression.groupe_taches') })) },
  ] : [];
  const corps = h('div', { class: 'suppr-bilan' }, h('p', { class: 'suppr-alerte', role: 'alert' }, t('suppression.avertissement')), autres);
  majAutres('deplacer');
  const attente = formulaire({ titre: t('suppression.titre', { titre: a.titre }), valider: t('suppression.valider'), corps, exiger: 'compris', danger: true, focus: 'annuler',
    champs: [...champs, { nom: 'compris', type: 'checkbox', label: t('suppression.compris') }] });
  corps.closest('form')?.addEventListener('change', (e) => { if (e.target.name === 'mode') majAutres(e.target.value); });
  const v = await attente;
  if (!v) return null;
  const mode = n ? v.mode : 'supprimer';
  let res;
  try {
    res = cible.tache ? await post(`/taches/${enc(cible.tache)}/supprimer`, { sous_taches: mode, vers: v.vers || null })
      : await post('/conteneurs/supprimer', { conteneur: cible.conteneur, contenu: mode, vers: v.vers || null });
  } catch (e) { erreur(t('suppression.impossible', { motif: e.message })); return null; }
  ouvrir(null);
  try { S.arbre = (await api(`/arbre?toutes=${S.toutes ? 1 : 0}`)).noeuds; emit('arbre'); } catch (e) { erreur(e.message); }
  emit('recharger');
  info([t('suppression.faite', { titre: a.titre }), res.ranges ? ` ${tn('suppression.ranges', res.ranges, { dossier: res.archives })}` : ''], [], 10000);
  return res;
}
