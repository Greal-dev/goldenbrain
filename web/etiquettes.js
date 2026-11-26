// Rôle : étiquettes libres des tâches (INV-ETIQUETTE-1..3) — puces de l'arbre, carte « Étiquettes » de « Détails » (saisie rapide,
//        complétion, clic pour retirer), réglage (consigne pour l'IA, renommer ou fusionner, annuler) et liste de complétion partagée.
// Frontières : API seule (/etiquettes, /taches/<id>/etiquettes, /lots) ; l'appelant redessine à partir de la Tache renvoyée ;
//            aucune étiquette n'est écrite sur la ligne du titre (INV-DETAIL-1).
import { t, tn } from './langues.js';
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit, ouvrir } from './store.js';

const enc = encodeURIComponent;
let connues = []; // [{mot, n, consigne}] : les plus utilisées d'abord
export const motsConnus = () => connues.map((e) => e.mot);
export async function charger() {
  try { connues = (await api('/etiquettes')).etiquettes; } catch { /* le serveur recharge à la prochaine ouverture */ }
  return connues;
}
// Liste de complétion unique (datalist) : saisie rapide, pose et retrait en bloc.
export function completion(id) {
  const d = h('datalist', { id }, motsConnus().map((m) => h('option', { value: m })));
  charger().then(() => d.replaceChildren(...motsConnus().map((m) => h('option', { value: m }))));
  return d;
}


export function carteEtiquettes(tk, surChangement) {
  const mots = tk.etiquettes || [];
  const poser = async (ajouter, retirer) => {
    try { surChangement(await post(`/taches/${enc(tk.id)}/etiquettes`, { ajouter, retirer })); charger(); } catch (e) { erreur(e.message); }
  };
  const saisie = h('input', { type: 'text', class: 'etiq-saisie', id: 'etiq-saisie', list: 'etiq-liste', maxlength: 30, autocomplete: 'off',
    'aria-label': t('etiquettes.ajouter'), placeholder: t('etiquettes.ajouter') });
  saisie.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ',') return;
    e.preventDefault();
    const v = saisie.value.trim();
    if (v) { saisie.value = ''; poser([v], []); }
  });
  const liees = tk.liees_etiquette || [];
  return h('div', { class: 'etiq-carte', 'data-id': 'etiquettes' },
    h('h4', { class: 'etiq-titre' }, t('etiquettes.titre')),
    h('div', { class: 'etiq-ligne' },
      mots.map((m) => h('button', { type: 'button', class: 'etiq retirable', 'data-etiquette': m, title: (tk.consignes_etiquettes || {})[m] || t('etiquettes.retirer', { mot: m }),
        'aria-label': t('etiquettes.retirer', { mot: m }), onclick: () => poser([], [m]) }, `#${m} ×`)),
      saisie, completion('etiq-liste')),
    liees.length ? h('ul', { class: 'etiq-liees', 'aria-label': t('etiquettes.liees') }, liees.map((x) => h('li', null,
      h('button', { type: 'button', class: 'lien-titre', onclick: () => ouvrir(x.id) }, x.titre || x.id), ' ', h('span', { class: 'etiq-st' }, x.statut || '')))) : null);
}

// Réglages → Étiquettes : consigne donnée à tout agent qui travaille une tâche étiquetée ; renommer = fusionner si le mot existe ; annulable.
export function sectionEtiquettes() {
  const corps = h('div', { class: 'rg-etiquettes', 'data-id': 'etiquettes-reglage' });
  let dernier = null;
  const dessiner = (liste) => {
    const lignes = liste.map((e) => {
      const consigne = h('textarea', { rows: 2, maxlength: 600, class: 'etiq-consigne', 'aria-label': t('etiquettes.consigne', { mot: e.mot }), placeholder: t('etiquettes.consigne_ph') }, e.consigne);
      consigne.addEventListener('change', async () => {
        try { await api(`/etiquettes/${enc(e.mot)}`, { methode: 'PUT', corps: { consigne: consigne.value } }); } catch (x) { erreur(x.message); }
      });
      const nouveau = h('input', { type: 'text', class: 'etiq-renommer', maxlength: 30, 'aria-label': t('etiquettes.renommer', { mot: e.mot }), placeholder: t('etiquettes.nouveau_nom'), list: 'etiq-liste-rg' });
      const renommer = h('button', { type: 'button', class: 'btn petit', 'data-renommer': e.mot, onclick: async () => {
        if (!nouveau.value.trim()) return;
        try { dernier = await post('/etiquettes/renommer', { de: e.mot, vers: nouveau.value }); emit('recharger'); recharger(); } catch (x) { erreur(x.message); }
      } }, t('etiquettes.renommer_bouton'));
      const suppr = e.n ? null : h('button', { type: 'button', class: 'btn-discret', onclick: async () => {
        try { await api(`/etiquettes/${enc(e.mot)}`, { methode: 'DELETE' }); recharger(); } catch (x) { erreur(x.message); }
      } }, t('etiquettes.supprimer'));
      return h('li', { class: 'etiq-rg', 'data-mot': e.mot }, h('div', { class: 'etiq-rg-tete' }, h('span', { class: 'etiq' }, `#${e.mot}`), h('span', { class: 'etiq-n' }, tn('lot.n_taches', e.n))),
        consigne, h('div', { class: 'etiq-rg-actions' }, nouveau, renommer, suppr));
    });
    const annuler = dernier?.lot ? h('button', { type: 'button', class: 'btn petit', id: 'etiq-annuler', onclick: async () => {
      try { await post(`/lots/${dernier.lot}/annuler`); dernier = null; emit('recharger'); recharger(); } catch (x) { erreur(x.message); }
    } }, t('etiquettes.annuler', { de: dernier.de, vers: dernier.vers })) : null;
    remplacer(corps, annuler, lignes.length ? h('ul', { class: 'etiq-rg-liste' }, lignes) : h('p', { class: 'aide' }, t('etiquettes.aucune')),
      h('datalist', { id: 'etiq-liste-rg' }, liste.map((e) => h('option', { value: e.mot }))));
  };
  const recharger = () => charger().then(dessiner);
  recharger();
  return corps;
}
