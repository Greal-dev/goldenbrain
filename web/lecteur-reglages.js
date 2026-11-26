// Rôle : section Réglages du lecteur de fichiers — dossiers lisibles en plus des racines, et extensions forcées vers le lecteur
// ou vers l'application du poste (INV-LECTEUR-1). Frontières : le serveur valide et écrit `[lecteur]` ; rien n'est déduit ici.
import { h } from './dom.js';
import { api } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

const mots = (s) => s.split(/[\s,;]+/).filter(Boolean).map((x) => x.replace(/^\./, '').toLowerCase());
export function sectionLecteur() {
  const corps = h('div', { class: 'rg-lecteur', 'data-id': 'lecteur-reglage' });
  const dessiner = (c) => {
    const dossiers = h('textarea', { id: 'rg-lec-dossiers', rows: 3, 'aria-label': t('reglages.lecteur_dossiers') }, c.dossiers.join('\n'));
    const lecteur = h('input', { type: 'text', id: 'rg-lec-lecteur', value: c.lecteur.join(' '), 'aria-label': t('reglages.lecteur_lecteur') });
    const appli = h('input', { type: 'text', id: 'rg-lec-appli', value: c.application.join(' '), 'aria-label': t('reglages.lecteur_application') });
    const sauver = async () => {
      try { dessiner(await api('/lecteur/reglages', { methode: 'PUT', corps: { dossiers: dossiers.value.split('\n').map((x) => x.trim()).filter(Boolean), lecteur: mots(lecteur.value), application: mots(appli.value) } })); } catch (e) { erreur(e.message); dessiner(c); }
    };
    for (const el of [dossiers, lecteur, appli]) el.addEventListener('change', sauver);
    corps.replaceChildren(
      h('label', { class: 'rg-ligne', for: 'rg-lec-dossiers' }, h('span', null, t('reglages.lecteur_dossiers')), dossiers),
      h('label', { class: 'rg-ligne', for: 'rg-lec-lecteur' }, h('span', null, t('reglages.lecteur_lecteur')), lecteur),
      h('label', { class: 'rg-ligne', for: 'rg-lec-appli' }, h('span', null, t('reglages.lecteur_application')), appli));
  };
  api('/lecteur/reglages').then(dessiner).catch((e) => erreur(e.message));
  return corps;
}
