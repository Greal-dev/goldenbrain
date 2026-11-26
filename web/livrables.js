// Rôle : « Livrables » — pastille de l'en-tête d'une tâche et volet qui liste les artefacts produits (déclarés, relevés des traces
// et des lignes, attendus), chez la tâche et, agrégés par tâche d'origine, chez ses parents.
// Frontières : API HTTP seule ; le serveur déduplique, type et vérifie l'existence. Ouverture : note du vault dans l'interface, adresse dans
// le navigateur (http/https seulement), fichier par le poste seulement (le serveur refuse l'appareil distant), branche/commit copiés.
// INV-LIVRABLES-1 ; INV-DETAIL-1 : une seule pastille dans l'en-tête, rien d'autre au-dessus du fil.
import { t } from './langues.js';
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, ouvrirNote, ouvrir } from './store.js';
import { formulaire } from './dialogue.js';

const enc = encodeURIComponent;
export const TYPES = ['note', 'fichier', 'url', 'publie', 'branche', 'commit'];
const libelleType = (x) => t(`livrables.type_${x}`);
const fermerVolet = () => document.querySelector('dialog[open]')?.close();

// Pastille : « Livrables (n) » ; le compte est relu à part (une requête légère) pour ne pas alourdir la fiche.
export function pastilleLivrables(tk) {
  const b = h('button', { class: 'btn petit d-livrables', type: 'button', 'data-id': 'livrables-pastille', title: t('livrables.pastille_titre'),
    'aria-label': t('livrables.titre'), onclick: () => volet(tk) }, h('span', { class: 'liv-mot' }, t('livrables.titre')));
  api(`/livrables?de=${enc(tk.id)}`).then((r) => {
    b.firstChild.textContent = r.total ? t('livrables.pastille', { n: r.total }) : t('livrables.titre');
    b.classList.toggle('manque', r.manquants > 0);
    if (r.manquants) b.title = `${t('livrables.pastille_titre')} — ${t('livrables.manquants', { n: r.manquants })}`;
  }).catch(() => {});
  return b;
}

async function ouvrirItem(tk, x) {
  if (x.type === 'note') { if (x.existe) { fermerVolet(); ouvrirNote(x.cible); } }
  else if (x.type === 'url' || x.type === 'publie') window.open(x.cible, '_blank', 'noopener,noreferrer');
  else if (x.type === 'fichier') {
    if (await import('./lecteur.js').then((m) => m.ouvrirFichier(x.cible))) return;
    try { erreur((await post(`/taches/${enc(tk.id)}/livrables/ouvrir`, { cible: x.cible })).message, 'info'); } catch (e) { erreur(e.message); }
  } else {
    try { await navigator.clipboard.writeText(x.cible); erreur(t('livrables.copie', { valeur: x.cible }), 'info'); } catch { erreur(x.cible, 'info'); }
  }
}

const geste = async (chemin, corps, recharger) => { try { await post(chemin, corps); } catch (e) { erreur(e.message); } recharger(); };

function ligne(tk, g, x, recharger) {
  const etat = x.existe === false ? h('span', { class: 'liv-disparu', 'data-id': 'liv-disparu' }, t('livrables.disparu'))
    : x.existe === null && x.type === 'fichier' ? h('span', { class: 'liv-inconnu' }, t('livrables.non_verifie')) : null;
  const retirable = g.id === tk.id && x.index !== null && x.index !== undefined;
  return h('li', { class: `liv liv-${x.type}${x.existe === false ? ' manquant' : ''}`, 'data-type': x.type },
    h('span', { class: 'liv-type' }, libelleType(x.type)),
    h('button', { class: 'liv-nom', type: 'button', title: x.cible, disabled: x.existe === false || (!x.ouvrable && x.type === 'fichier') ? true : null,
      onclick: () => ouvrirItem(tk, x) }, x.titre),
    etat,
    h('span', { class: 'liv-meta' }, `${x.date} · ${x.auteur === 'ia' ? t('lignes.par_ia') : t('lignes.par_moi')}`),
    retirable ? h('button', { class: 'btn petit', type: 'button', 'aria-label': t('livrables.retirer'), title: t('livrables.retirer'),
      onclick: () => geste(`/taches/${enc(tk.id)}/livrables/retirer`, { index: x.index }, recharger) }, '×') : null);
}

function attendu(tk, a, recharger) {
  return h('li', { class: `liv-att${a.produit ? ' fait' : ''}` },
    h('input', { type: 'checkbox', checked: a.produit ? true : null, 'aria-label': a.titre,
      onchange: () => geste(`/taches/${enc(tk.id)}/livrables/basculer`, { index: a.index }, recharger) }),
    h('span', null, a.titre),
    a.produit ? null : h('span', { class: 'liv-disparu' }, t('livrables.manquant')),
    h('button', { class: 'btn petit', type: 'button', 'aria-label': t('livrables.retirer'), title: t('livrables.retirer'),
      onclick: () => geste(`/taches/${enc(tk.id)}/livrables/retirer`, { index: a.index }, recharger) }, '×'));
}

// Un Entrée dans un champ ne doit pas fermer le volet (formulaire de dialogue) : il valide le champ.
const entree = (f) => (e) => { if (e.key === 'Enter') { e.preventDefault(); f(); } };
const champ = (id, cle, max) => h('input', { type: 'text', placeholder: t(cle), 'aria-label': t(cle), 'data-id': id, maxlength: max });

export async function volet(tk) {
  const filtre = { type: '', q: '' };
  const zone = h('div', { class: 'liv-zone', 'data-id': 'livrables' });
  const sel = h('select', { 'aria-label': t('livrables.filtre_type'), 'data-id': 'liv-filtre-type', onchange: () => { filtre.type = sel.value; charger(); } },
    h('option', { value: '' }, t('livrables.tous_types')), TYPES.map((x) => h('option', { value: x }, libelleType(x))));
  const rech = h('input', { type: 'search', placeholder: t('livrables.recherche'), 'aria-label': t('livrables.recherche'), 'data-id': 'liv-recherche',
    onkeydown: entree(() => {}), oninput: () => { filtre.q = rech.value; charger(); } });
  const barre = h('div', { class: 'liv-filtres' }, sel, rech);
  const cible = champ('liv-cible', 'livrables.cible_placeholder', 2000);
  const titre = champ('liv-titre', 'livrables.titre_placeholder', 300);
  const att = champ('liv-attendu', 'livrables.attendu_placeholder', 300);
  const ajouterLiv = async () => {
    if (!cible.value.trim()) return;
    try { await post(`/taches/${enc(tk.id)}/livrables`, { cible: cible.value, titre: titre.value }); cible.value = ''; titre.value = ''; } catch (e) { erreur(e.message); }
    charger();
  };
  const ajouterAtt = async () => {
    if (!att.value.trim()) return;
    try { await post(`/taches/${enc(tk.id)}/livrables/attendre`, { titre: att.value }); att.value = ''; } catch (e) { erreur(e.message); }
    charger();
  };
  cible.addEventListener('keydown', entree(ajouterLiv)); titre.addEventListener('keydown', entree(ajouterLiv)); att.addEventListener('keydown', entree(ajouterAtt));
  const ajout = h('div', { class: 'liv-ajout' },
    h('div', { class: 'liv-form' }, cible, titre, h('button', { class: 'btn petit', type: 'button', 'data-id': 'liv-ajouter', onclick: ajouterLiv }, t('livrables.ajouter'))),
    h('div', { class: 'liv-form' }, att, h('button', { class: 'btn petit', type: 'button', 'data-id': 'liv-annoncer', onclick: ajouterAtt }, t('livrables.annoncer'))));

  async function charger() {
    let r;
    try { r = await api(`/livrables?de=${enc(tk.id)}&type=${enc(filtre.type)}&q=${enc(filtre.q)}`); } catch (e) { erreur(e.message); return; }
    barre.hidden = !(r.agrege || r.total > 5 || filtre.type || filtre.q);
    const entete = (g) => (!r.agrege ? null : h('h4', null, g.id === tk.id ? t('livrables.cette_tache')
      : h('a', { href: `#t=${enc(g.id)}`, onclick: (e) => { e.preventDefault(); fermerVolet(); ouvrir(g.id); } }, g.titre)));
    const groupes = r.groupes.map((g) => h('section', { class: 'liv-groupe', 'data-tache': g.id }, entete(g),
      g.attendus.length ? h('ul', { class: 'liv-attendus' }, g.attendus.map((a) => (g.id === tk.id ? attendu(tk, a, charger)
        : h('li', { class: `liv-att${a.produit ? ' fait' : ''}` }, `${a.produit ? '☑' : '☐'} ${a.titre}`)))) : null,
      g.livrables.length ? h('ul', { class: 'liv-liste' }, g.livrables.map((x) => ligne(tk, g, x, charger))) : null));
    remplacer(zone, r.manquants ? h('p', { class: 'note liv-manque' }, t('livrables.manquants', { n: r.manquants })) : null,
      groupes.length ? groupes : h('p', { class: 'note' }, filtre.type || filtre.q ? t('livrables.aucun_filtre') : t('livrables.vide')));
  }
  await charger();
  await formulaire({ titre: t('livrables.titre_volet', { titre: tk.titre }), texte: t('livrables.consigne'), corps: h('div', { class: 'liv-volet' }, barre, zone, ajout),
    valider: t('livrables.fermer'), annuler: null, large: true });
}
