// Rôle : lignes de tâche (carte du détail), nature des tâches (repère, sélecteur), réglage du rangement, dialogue de rangement.
// Frontières : API HTTP uniquement ; ne calcule jamais la nature ni le plafond (le serveur les porte : rangement.py).
// INV-LIGNES-1 : une ligne est un travail court d'une tâche, pas une tâche. INV-PLAFOND-1 / INV-NATURE-1 : rangement proposé, jamais imposé.
import { t } from './langues.js';
import { h } from './dom.js';
import { api, post } from './api.js';
import { erreur, ouvrir } from './store.js';
import { formulaire } from './dialogue.js';

export const NATURES = ['developpement', 'operation', 'pilotage'];
export const libelleNature = (g) => (g ? t(`lignes.nature_${g}`) : t('lignes.nature_aucune'));

// Repère de l'arbre : pastille courte par nature, et compteur de lignes cochées.
export const pastilleNature = (n) => (n.genre
  ? h('span', { class: `nature nat-${n.genre}`, title: libelleNature(n.genre), 'data-nature': n.genre }, t(`lignes.court_${n.genre}`)) : null);
export const compteLignes = (n) => (n.lignes?.[1]
  ? h('span', { class: 'compte-lignes', title: t('lignes.compte_titre', { faites: n.lignes[0], total: n.lignes[1] }) }, `☑ ${n.lignes[0]}/${n.lignes[1]}`) : null);

// Sélecteur de nature (en-tête du détail) : « automatique » rend la main à la déduction.
export function selecteurNature(tk, appliquer) {
  const sel = h('select', { class: 'sel-nature', 'aria-label': t('lignes.nature'), title: t('lignes.nature_titre'), 'data-id': 'sel-nature',
    onchange: async () => {
      try { appliquer(await post(`/taches/${encodeURIComponent(tk.id)}/genre`, { genre: sel.value })); } catch (e) { erreur(e.message); }
    } },
  h('option', { value: '', selected: tk.genre_pose ? null : true }, t('lignes.nature_auto', { nature: libelleNature(tk.genre) })),
  NATURES.map((g) => h('option', { value: g, selected: tk.genre_pose && tk.genre === g ? true : null }, libelleNature(g))));
  return sel;
}

// Carte « Lignes » du détail. `appliquer(tk)` : détail à jour ; `recharger()` : relire la tâche.
export function carteLignes(tk, recharger) {
  const lignes = tk.fiche?.lignes || [];
  const base = `/taches/${encodeURIComponent(tk.id)}/lignes`;
  const geste = async (chemin, corps) => { try { return await post(chemin, corps); } catch (e) { erreur(e.message); return null; } finally { recharger(); } };
  const champ = h('input', { type: 'text', class: 'ligne-saisie', maxlength: 300, placeholder: t('lignes.ajouter_placeholder'), 'aria-label': t('lignes.ajouter'), 'data-id': 'ligne-saisie' });
  const ajouter = async (e) => {
    e.preventDefault();
    const texte = champ.value.trim();
    if (!texte) return;
    champ.value = '';
    await geste(base, { texte });
  };
  const item = (l, i) => h('li', { class: l.fait ? 'fait' : '', 'data-ligne': i },
    h('input', { type: 'checkbox', checked: l.fait ? true : null, 'aria-label': l.texte, onchange: () => geste(`${base}/basculer`, { index: i }) }),
    h('span', { class: 'ligne-texte' }, l.texte),
    h('span', { class: 'ligne-meta' }, `${l.date} · ${l.auteur === 'ia' ? t('lignes.par_ia') : t('lignes.par_moi')}`),
    l.lien ? h('span', { class: 'ligne-lien' }, l.lien) : null,
    h('button', { class: 'btn petit', type: 'button', title: t('lignes.promouvoir_titre'), 'data-promouvoir': i,
      onclick: async () => { const r = await geste(`${base}/promouvoir`, { index: i }); if (r?.id) ouvrir(r.id); } }, t('lignes.promouvoir')),
    h('button', { class: 'btn petit', type: 'button', title: t('lignes.retirer_titre'), 'aria-label': t('lignes.retirer_titre'), onclick: () => geste(`${base}/retirer`, { index: i }) }, '×'));
  return h('section', { class: 'lignes', 'data-id': 'lignes' },
    h('h3', null, t('lignes.titre'), lignes.length ? h('span', { class: 'compte' }, `${lignes.filter((l) => l.fait).length}/${lignes.length}`) : null),
    lignes.length ? h('ul', { class: 'lignes-liste' }, lignes.map(item)) : h('p', { class: 'note' }, t('lignes.vide')),
    h('form', { class: 'ligne-ajout', onsubmit: ajouter }, champ, h('button', { class: 'btn petit', type: 'submit' }, t('lignes.ajouter'))));
}

// Tâche → ligne de sa mère (bouton de l'en-tête). Renvoie vrai si la tâche est devenue une ligne.
export async function enLigne(tk) {
  const ok = await formulaire({ titre: t('lignes.en_ligne_titre'), texte: t('lignes.en_ligne_texte', { titre: tk.titre }), valider: t('lignes.en_ligne') });
  if (!ok) return false;
  try { await post(`/taches/${encodeURIComponent(tk.id)}/en-ligne`, {}); return true; } catch (e) { erreur(e.message); return false; }
}

// 409 `rangement` à la création : propositions du serveur (ligne, sous-groupe, nouveau groupe) ou « Créer quand même ».
// Renvoie la tâche créée ou concernée, ou null (annulé).
export async function dialogueRangement(corps, rangement) {
  let resultat = null;
  const motif = rangement.raison === 'nature'
    ? t('lignes.rangement_nature', { nature: libelleNature(rangement.genre) })
    : t('lignes.rangement_plafond', { ouvertes: rangement.ouvertes, plafond: rangement.plafond });
  const choisir = async (p, bouton) => {
    try {
      if (p.geste === 'ligne') {
        await post(`/taches/${encodeURIComponent(p.tache)}/lignes`, { texte: corps.titre });
        resultat = { id: p.tache };
      } else if (p.geste === 'sous_groupe') resultat = await post('/taches', { ...corps, conteneur: undefined, parent: p.tache, forcer: true });
      else resultat = await post('/taches', { ...corps, groupe: p.titre });
      bouton.closest('dialog').close();
    } catch (e) { erreur(e.message); }
  };
  const gestes = { ligne: 'lignes.geste_ligne', sous_groupe: 'lignes.geste_sous_groupe', nouveau_groupe: 'lignes.geste_nouveau_groupe' };
  const ok = await formulaire({
    titre: t('lignes.rangement_titre'), texte: motif, valider: t('bandeau.creer_quand_meme'),
    corps: h('ul', { class: 'props proches', 'data-id': 'rangement' }, rangement.propositions.map((p) => h('li', { class: 'proche', 'data-geste': p.geste },
      h('span', { class: 'proche-titre' }, t(gestes[p.geste], { titre: p.titre || '' })),
      h('button', { type: 'button', class: 'btn', onclick: (e) => choisir(p, e.currentTarget) }, t('lignes.choisir'))))),
  });
  if (resultat) return resultat;
  return ok ? post('/taches', { ...corps, forcer: true }) : null;
}

// Section Réglages « Rangement » : plafond d'ouvertes par parent, séparation des natures.
export function sectionRangement() {
  const corps = h('div', { class: 'rg-rangement', 'data-id': 'rangement-reglage' });
  const dessiner = (c) => {
    const plafond = h('input', { type: 'number', min: 2, max: 100, value: c.plafond, id: 'rg-plafond', 'aria-label': t('lignes.plafond') });
    const separees = h('input', { type: 'checkbox', id: 'rg-natures', checked: c.natures_separees ? true : null });
    const sauver = async () => {
      try { dessiner(await api('/rangement', { methode: 'PUT', corps: { plafond: Number(plafond.value), natures_separees: separees.checked } })); } catch (e) { erreur(e.message); dessiner(c); }
    };
    plafond.addEventListener('change', sauver); separees.addEventListener('change', sauver);
    corps.replaceChildren(
      h('label', { class: 'rg-ligne', for: 'rg-plafond' }, h('span', null, t('lignes.plafond')), plafond),
      h('label', { class: 'rg-ligne', for: 'rg-natures' }, separees, h('span', null, t('lignes.natures_separees'))));
  };
  api('/rangement').then(dessiner).catch((e) => erreur(e.message));
  return corps;
}
