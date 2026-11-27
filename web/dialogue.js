// Rôle : boîte de dialogue à formulaire (<dialog> natif), réutilisée par tous les formulaires.
// Résout avec {nom: valeur} ou null si annulé.
import { h, ajouter } from './dom.js';
import { t } from './langues.js';

// `fin` sur une option : placée après tous les groupes (geste « ＋ … » en dernier).
export function champ(c, i) {
  const id = `f-${c.nom}-${i}`;
  const v = c.valeur;
  if (c.type === 'checkbox') {
    return h('label', { class: 'case' }, h('input', { type: 'checkbox', name: c.nom, checked: v ? true : null, disabled: c.desactive ? true : null }), ' ', c.label);
  }
  if (c.type === 'radio') {
    return h('fieldset', { class: 'radios' }, h('legend', null, c.label),
      c.options.map((o) => h('label', null, h('input', { type: 'radio', name: c.nom, value: o.valeur, checked: o.valeur === v ? true : null }), ' ', o.libelle)));
  }
  let ctrl;
  if (c.type === 'textarea') ctrl = h('textarea', { id, name: c.nom, rows: c.lignes || 4, required: c.requis ? true : null, placeholder: c.aide || null }, v || '');
  else if (c.type === 'select') {
    const groupes = new Map();
    for (const o of c.options.filter((x) => !x.fin)) { const g = o.groupe || ''; if (!groupes.has(g)) groupes.set(g, []); groupes.get(g).push(o); }
    const opt = (o) => h('option', { value: o.valeur, selected: o.valeur === v ? true : null }, o.libelle);
    ctrl = h('select', { id, name: c.nom }, [...groupes].map(([g, os]) => (g ? h('optgroup', { label: g }, os.map(opt)) : os.map(opt))), c.options.filter((x) => x.fin).map(opt));
  } else ctrl = h('input', { id, name: c.nom, type: c.type === 'date' ? 'date' : 'text', value: v || '', required: c.requis ? true : null, autocomplete: 'off', readonly: c.lecture ? true : null, pattern: c.motif || null, title: c.motif ? c.aide : null, placeholder: c.aide || null });
  // `sous` : nœud affiché sous le champ ; `surSaisie(valeur)` : appelée à chaque frappe (suggestions).
  if (c.requis) { // A12 : message natif en anglais remplacé par le nôtre, effacé dès la saisie
    ctrl.addEventListener('invalid', () => ctrl.setCustomValidity(t('dialogue.champ_requis')));
    ctrl.addEventListener('input', () => ctrl.setCustomValidity(''));
  }
  if (c.surSaisie) ctrl.addEventListener('input', () => c.surSaisie(ctrl.value));
  return h('div', { class: 'champ' }, h('label', { for: id }, c.label), ctrl, c.sous || null);
}

// `corps` : nœud inséré sous le texte ; `annuler` : libellé du refus (null : pas de refus, la validation ferme) ; `focus: 'annuler'` : le refus prend le focus (confirmation à risque).
// `exiger` : nom d'une case qui doit être cochée pour valider (geste irréversible) ; `danger` : bouton de validation rouge.
export function formulaire({ titre, texte, champs = [], valider = t('dialogue.valider'), large = false, corps = null, annuler = t('dialogue.annuler'), focus = null, exiger = null, danger = false }) {
  return new Promise((resolve) => {
    let rendu = false;
    const fin = (val) => { if (!rendu) { rendu = true; resolve(val); } };
    const form = h('form', { method: 'dialog', class: 'dlg-form' });
    const dlg = h('dialog', { class: large ? 'dlg large' : 'dlg', 'aria-label': titre }, form);
    ajouter(form, h('h3', null, titre), texte ? h('p', { class: 'dlg-texte' }, texte) : null, corps, champs.map(champ),
      h('div', { class: 'dlg-actions' },
        annuler ? h('button', { type: 'button', class: 'btn', 'data-refus': '', onclick: () => dlg.close() }, annuler) : null,
        h('button', { type: 'submit', class: danger ? 'btn primaire danger-plein' : 'btn primaire' }, valider)));
    if (exiger) {
      const caseExigee = form.querySelector(`input[name="${exiger}"]`), ok = form.querySelector('.primaire');
      const maj = () => { ok.disabled = !caseExigee.checked; };
      caseExigee.addEventListener('change', maj); maj();
    }
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const val = {};
      for (const c of champs) val[c.nom] = c.type === 'checkbox' ? fd.has(c.nom) : (fd.get(c.nom) ?? c.valeur ?? '');
      fin(val);
      dlg.close();
    });
    dlg.addEventListener('close', () => { fin(null); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
    if (focus === 'annuler' && annuler) { dlg.querySelector('[data-refus]').focus(); return; }
    (dlg.querySelector('input:not([type=checkbox]):not([type=radio]):not([readonly]), textarea, select') || dlg.querySelector('.primaire'))?.focus();
  });
}
