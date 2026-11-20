// Rôle : dialogue du plan d'alignement (déplacements, réécritures avec exemples, références externes, avertissements),
// application avec état d'attente (plusieurs secondes possibles) et compte rendu.
// Sert aussi au geste d'arbre sur un projet ou une opération (INV-ARBRE-2) : plan par POST /arbre/plan, même application.
// Frontières : API POST /alignement/plan ou /arbre/plan (simulation, n'écrit rien) et /alignement/appliquer ; l'arbre renvoyé remplace S.arbre.
// Le serveur tient l'atomicité (INV-ALIGN-1) : ici, un 409 est présenté tel quel, avec « Refaire le plan » quand il a pu changer.
import { t, tn } from './langues.js';
import { h, remplacer } from './dom.js';
import { S, emit, erreur } from './store.js';
import { post } from './api.js';

const MAX_FICHIERS = 100;

// `geste` (facultatif) : {corps, titre, fini(r)} — plan d'un geste d'arbre ; `fini` reçoit le compte rendu.
export async function voirPlan(conteneurs, geste = null) {
  let plan;
  try { plan = await (geste ? post('/arbre/plan', geste.corps) : post('/alignement/plan', { conteneurs })); } catch (e) { erreur(e.message); return; }
  dialogue(plan, conteneurs, geste);
}
const CLES = { parent: t('alignement_plan.cle_parent'), casquette: t('alignement_plan.cle_casquette') };
const cles = (m) => Object.entries(m).map(([k, v]) => (v === null ? t('alignement_plan.cle_retire', { cle: CLES[k] || k }) : `${CLES[k] || k} → ${v}`)).join(', ');

function section(titre, ...contenu) { return h('section', { class: 'pl-sec' }, h('h4', null, titre), contenu); }

function reecriture(r) {
  return h('details', { class: 'pl-fichier' },
    h('summary', null, h('code', null, r.fichier), h('span', { class: 'pl-n' }, tn('alignement_plan.lignes', r.lignes))),
    (r.exemples || []).length ? h('div', { class: 'pl-exemples' }, r.exemples.map((x) => h('div', { class: 'pl-ex' },
      h('div', { class: 'pl-avant' }, h('span', { 'aria-label': t('alignement_plan.avant') }, '−'), h('code', null, x.avant)),
      h('div', { class: 'pl-apres' }, h('span', { 'aria-label': t('alignement_plan.apres') }, '+'), h('code', null, x.apres))))) : h('p', { class: 'vide' }, t('alignement_plan.sans_exemple')));
}

function dialogue(plan, conteneurs, geste) {
  const dep = plan.deplacements || [], ree = plan.reecritures || [], ext = plan.externes || [], av = plan.avertissements || [], fic = plan.fiches || [];
  const lignes = ree.reduce((s, r) => s + (r.lignes || 0), 0);
  const git = h('input', { type: 'checkbox', checked: true });
  const statut = h('div', { class: 'pl-statut', role: 'status', 'aria-live': 'polite' });
  const alerte = h('div', { class: 'pl-alerte', role: 'alert', hidden: true });
  const annuler = h('button', { type: 'button', class: 'btn', onclick: () => dlg.close() }, t('alignement_plan.annuler'));
  const appliquer = h('button', { type: 'button', class: 'btn primaire', onclick: lancer }, t('alignement_plan.appliquer'));
  const form = h('div', { class: 'dlg-form' });
  const dlg = h('dialog', { class: 'dlg plan', 'aria-labelledby': 'pl-titre' }, form);
  let occupe = false;

  remplacer(form,
    h('h3', { id: 'pl-titre' }, geste ? geste.titre : t('alignement_plan.titre')),
    h('p', { class: 'dlg-texte' }, t('alignement_plan.resume', { dossiers: tn('alignement_plan.dossiers', dep.length), fichiers: tn('alignement_plan.fichiers', ree.length), lignes: tn('alignement_plan.lignes', lignes) })),
    dep.length ? section(t('alignement_plan.deplacements'), h('ul', { class: 'pl-dep' }, dep.map((d) => h('li', null, h('code', null, d.de), ' → ', h('code', null, d.vers))))) : null,
    fic.length ? section(t('alignement_plan.fiches'), h('ul', { class: 'pl-dep' }, fic.map((f) => h('li', null, h('code', null, f.fichier), ' : ', cles(f.cles))))) : null,
    ree.length ? section(t('alignement_plan.references'), ree.slice(0, MAX_FICHIERS).map(reecriture),
      ree.length > MAX_FICHIERS ? h('p', { class: 'vide' }, t('alignement_plan.autres_fichiers', { n: ree.length - MAX_FICHIERS })) : null) : null,
    ext.length ? section(t('alignement_plan.hors_vault'),
      h('ul', { class: 'pl-ext' }, ext.map((x) => h('li', null, h('code', null, x.fichier), h('span', { class: 'pl-n' }, tn('alignement_plan.occurrences', x.occurrences)))))) : null,
    av.length ? section(t('alignement_plan.avertissements'), h('ul', { class: 'pl-avert' }, av.map((a) => h('li', null, a)))) : null,
    h('label', { class: 'case' }, git, t('alignement_plan.point_restauration')),
    alerte, statut,
    h('div', { class: 'dlg-actions' }, annuler, appliquer));

  // Pendant l'application, le dialogue ne se ferme pas (Échap compris) : l'opération est tout ou rien côté serveur.
  dlg.addEventListener('cancel', (e) => { if (occupe) e.preventDefault(); });
  dlg.addEventListener('close', () => dlg.remove());

  function echec(e) {
    const refaire = e.statut === 409;
    alerte.hidden = false;
    remplacer(alerte, h('p', null, e.message), refaire ? h('button', { type: 'button', class: 'btn petit', onclick: () => { dlg.close(); voirPlan(conteneurs, geste); } }, t('alignement_plan.refaire')) : null);
    remplacer(statut);
    annuler.disabled = false; annuler.textContent = t('alignement_plan.fermer');
    appliquer.hidden = true;
    alerte.querySelector('button')?.focus();
  }
  function compteRendu(r) {
    remplacer(form,
      h('h3', { id: 'pl-titre' }, t('alignement_plan.termine')),
      h('ul', { class: 'pl-compte', role: 'status' },
        h('li', null, tn('alignement_plan.deplaces', r.deplacements)),
        h('li', null, tn('alignement_plan.reecrits', r.fichiers_reecrits)),
        h('li', null, r.commit ? [t('alignement_plan.point'), h('code', null, r.commit)] : t('alignement_plan.sans_point')),
        ext.length ? h('li', { class: 'al-conflit' }, tn('alignement_plan.hors_vault_a_corriger', ext.length)) : null),
      h('div', { class: 'dlg-actions' }, h('button', { type: 'button', class: 'btn primaire', onclick: () => dlg.close() }, t('alignement_plan.fermer'))));
    form.querySelector('.primaire').focus();
  }
  async function lancer() {
    occupe = true;
    dlg.setAttribute('aria-busy', 'true');
    appliquer.disabled = annuler.disabled = git.disabled = true;
    alerte.hidden = true;
    remplacer(statut, h('span', { class: 'tourne' }), t('alignement_plan.attente'));
    try {
      const r = await post('/alignement/appliquer', { jeton: plan.jeton, point_git: git.checked });
      occupe = false; dlg.removeAttribute('aria-busy');
      if (r.arbre?.noeuds) S.arbre = r.arbre.noeuds;
      emit('arbre');
      emit('vault-change');
      if (geste) { dlg.close(); geste.fini(r); } else compteRendu(r);
    } catch (e) { occupe = false; dlg.removeAttribute('aria-busy'); echec(e); }
  }

  document.body.append(dlg);
  dlg.showModal();
  appliquer.focus();
}
