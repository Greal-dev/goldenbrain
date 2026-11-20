// Rôle : bouton « Voir le résultat » — ouvre ce que l'assistant a produit (INV-RESULTAT-1, poste seulement).
// Frontières : API HTTP seule ; la liste et l'ouverture sont décidées par le serveur (le client ne désigne qu'un élément reçu).
import { h } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { formulaire } from './dialogue.js';
import { t } from './langues.js';

const GENRES = { site: () => t('resultat.genre_site'), fichier: () => t('resultat.genre_fichier'), dossier: () => t('resultat.genre_dossier') };

const enc = encodeURIComponent;

async function ouvrirElement(id, e) {
  try { erreur((await post(`/taches/${enc(id)}/resultat/ouvrir`, { cible: e.cible })).message, 'info'); } catch (x) { erreur(x.message); }
}

export async function voirResultat(id) {
  let r;
  try { r = await api(`/taches/${enc(id)}/resultat`); } catch (x) { erreur(x.message); return; }
  if (!r.elements.length) { erreur(r.message, 'info'); return; }
  if (r.elements.length === 1) { await ouvrirElement(id, r.elements[0]); return; }
  const liste = h('ul', { class: 'voir-resultats' }, r.elements.map((e) => h('li', null,
    h('span', { class: 'genre' }, GENRES[e.genre]?.() || ''), ' ',
    h('button', { type: 'button', class: 'btn', title: e.cible, onclick: () => ouvrirElement(id, e) }, e.libelle))));
  await formulaire({ titre: t('resultat.titre'), texte: t('resultat.consigne'), corps: liste, valider: t('resultat.fermer'), annuler: t('resultat.fermer') });
}
