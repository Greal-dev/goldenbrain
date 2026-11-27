// Rôle : « Nouvelle étiquette » (dialogue nom + consigne) et panneau « Trouver les tâches » de la vue d'une étiquette —
//        classement local immédiat, « Affiner avec l'IA », cases à cocher, « Étiqueter les n sélectionnées », « Annuler ».
// Frontières : chargé au clic (paresseux.js, INV-REACTIVITE-1) ; lit /etiquettes/<mot>/candidates (et /ia, INV-ETIQUETTE-5) ;
//            écrit par PUT /etiquettes/<mot> (déclaration, geste humain, INV-ETIQUETTE-2) et POST /lots (pose en bloc annulable, INV-LOT-1).
import { t, tn } from './langues.js';
import { h, remplacer, filLisible } from './dom.js';
import { api, post } from './api.js';
import { ouvrirVue, erreur, emit } from './store.js';
import { formulaire } from './dialogue.js';
import { charger as chargerEtiquettes } from './etiquettes.js';

const enc = encodeURIComponent;
let attendu = null; // étiquette tout juste créée : sa vue ouvre le panneau d'emblée

/** Vrai une seule fois pour l'étiquette tout juste créée. */
export function prendre(mot) {
  const oui = attendu === mot;
  if (oui) attendu = null;
  return oui;
}

export async function nouvelleEtiquette() {
  const v = await formulaire({ titre: t('etiq_trouver.nouvelle_titre'), valider: t('etiq_trouver.creer'),
    champs: [{ nom: 'nom', label: t('etiq_trouver.nom'), requis: true, aide: t('etiq_trouver.nom_aide') },
      { nom: 'consigne', label: t('etiq_trouver.consigne'), type: 'textarea', lignes: 3, aide: t('etiquettes.consigne_ph') }] });
  if (!v) return;
  try {
    const r = await api(`/etiquettes/${enc(v.nom)}`, { methode: 'PUT', corps: { consigne: v.consigne } });
    await chargerEtiquettes();
    attendu = r.mot;
    ouvrirVue('etiquette', r.mot);
  } catch (e) { erreur(e.message); }
}

export function remplir(zone, mot, surPose) {
  let liste = [], coches = new Set(), etat = t('etiq_trouver.recherche'), occupe = true, dernier = null;
  const dessiner = () => {
    if (!zone.isConnected) return;
    const lignes = liste.map((x) => h('li', { class: 'etiq-cand', 'data-id': 'etiq-cand', 'data-tache': x.id },
      h('label', { class: 'case' }, h('input', { type: 'checkbox', checked: coches.has(x.id) ? true : null,
        onchange: (e) => { if (e.target.checked) coches.add(x.id); else coches.delete(x.id); dessiner(); } }), ' ',
      h('span', { class: 'au-titre' }, x.titre), ' ', h('span', { class: 'au-place' }, filLisible(x.fil).join(' › '))),
      x.motif ? h('p', { class: 'tr-raison', 'data-id': 'etiq-motif' }, x.motif) : null));
    remplacer(zone, h('h3', null, t('etiq_trouver.titre')),
      h('p', { class: 'tr-raison', role: 'status', 'data-id': 'etiq-trouver-etat' }, etat),
      lignes.length ? h('ul', { class: 'au-liste' }, lignes) : occupe ? null : h('p', { class: 'vide' }, t('etiq_trouver.aucune')),
      h('p', null,
        h('button', { type: 'button', class: 'btn primaire', 'data-id': 'etiq-poser', disabled: coches.size && !occupe ? null : '', onclick: poser },
          tn('etiq_trouver.poser', coches.size)), ' ',
        h('button', { type: 'button', class: 'btn', 'data-id': 'etiq-affiner', disabled: occupe ? '' : null, onclick: affiner }, t('etiq_trouver.affiner')), ' ',
        dernier ? h('button', { type: 'button', class: 'btn petit', 'data-id': 'etiq-annuler-pose', onclick: annuler }, t('lot.annuler')) : null, ' ',
        h('button', { type: 'button', class: 'btn-discret', 'data-id': 'etiq-trouver-fermer', onclick: () => zone.remove() }, t('etiq_trouver.fermer'))));
  };
  const recevoir = (r) => { liste = r.candidates; coches = new Set(liste.filter((x) => x.pertinente).map((x) => x.id)); };
  async function local() {
    try { recevoir(await api(`/etiquettes/${enc(mot)}/candidates`)); etat = tn('etiq_trouver.trouvees', liste.length); } catch (e) { etat = e.message; }
    occupe = false; dessiner();
  }
  async function affiner() {
    occupe = true; etat = t('etiq_trouver.affinage'); dessiner();
    try {
      const r = await post(`/etiquettes/${enc(mot)}/candidates/ia`);
      recevoir(r);
      etat = r.erreur || tn('etiq_trouver.ia_ok', coches.size); // repli : classement local et motif clair (INV-ETIQUETTE-5)
    } catch (e) { etat = e.message; }
    occupe = false; dessiner();
  }
  async function poser() {
    occupe = true; dessiner();
    try {
      const r = await api('/lots', { methode: 'POST', corps: { taches: [...coches], etiquettes: { ajouter: [mot] } } });
      dernier = r.lot;
      liste = liste.filter((x) => !r.changees.includes(x.id));
      coches = new Set();
      etat = [tn('lot.fait', r.changees.length), r.exclues.length ? t('lot.exclues', { liste: r.exclues.map((x) => x.titre).join(', ') }) : ''].filter(Boolean).join(' ');
      emit('recharger-arbre'); surPose();
    } catch (e) { erreur(e.message); }
    occupe = false; dessiner();
  }
  async function annuler() {
    try { await post(`/lots/${dernier}/annuler`); dernier = null; etat = t('lot.annule'); emit('recharger-arbre'); surPose(); } catch (e) { return erreur(e.message); }
    occupe = true; dessiner(); await local();
  }
  dessiner();
  local();
}
