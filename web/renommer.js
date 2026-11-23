// Rôle : renommer une tâche depuis sa fiche — clic sur le titre → champ éditable (Entrée valide, Échap annule).
// Frontières : appel `POST /taches/{id}/renommer` ; l'identifiant et le fichier ne changent pas (INV-RENOMMER-1).
// INV-WEB-1 : tout texte passe par h() (jamais d'innerHTML).
import { h } from './dom.js';
import { post } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

// `suffixe` : nœud affiché après le titre (repère IA) ; `appliquer(tache)` reçoit la tâche renvoyée par le serveur.
export function titreEditable(tk, appliquer, suffixe = null) {
  const titre = h('h2', { class: 'd-titre d-titre-editable', tabindex: 0, role: 'button', title: t('renommer.aide'),
    'data-id': 'titre-tache' }, tk.titre, suffixe);
  const ouvrir = () => {
    const champ = h('input', { class: 'd-titre-champ', type: 'text', value: tk.titre, 'aria-label': t('renommer.champ'),
      autocomplete: 'off', enterkeyhint: 'done', 'data-id': 'titre-champ' });
    let fini = false, envoi = false;
    const fermer = () => { fini = true; champ.replaceWith(titre); titre.focus(); };
    const valider = async () => {
      if (envoi) return;
      const nouveau = champ.value.trim();
      if (!nouveau) return erreur(t('renommer.vide'));
      if (nouveau === tk.titre) return fermer();
      envoi = true;
      try { const r = await post(`/taches/${encodeURIComponent(tk.id)}/renommer`, { titre: nouveau }); fini = true; appliquer(r); }
      catch (e) { envoi = false; erreur(e.message); }
    };
    champ.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); valider(); } else if (e.key === 'Escape') { e.preventDefault(); fermer(); }
    });
    // Au téléphone, « OK » du clavier ou un toucher ailleurs ferme le champ sans Entrée : le titre tapé est gardé (seul Échap annule).
    champ.addEventListener('blur', () => { if (fini || envoi) return; if (champ.value.trim() && champ.value.trim() !== tk.titre) valider(); else fermer(); });
    titre.replaceWith(champ);
    champ.focus();
    champ.select();
  };
  titre.addEventListener('click', ouvrir);
  titre.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ouvrir(); } });
  return titre;
}
