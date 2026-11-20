// Rôle : liens fonctionnels d'une tâche — carte « Liens » du volet droit et dialogue « Lier… » (recherche de la cible).
// Frontières : API seule (/liens, /recherche) ; l'appelant redessine à partir de la Tache renvoyée.
import { t, tn } from './langues.js';
import { h, pastille, remplacer } from './dom.js';
import { ouvrir, erreur } from './store.js';
import { api, post } from './api.js';

const enc = encodeURIComponent;
export const TYPES_LIEN = [
  { valeur: 'alimente', libelle: t('liens.alimente'), aide: t('liens.alimente_aide') },
  { valeur: 'prerequis', libelle: t('liens.prerequis'), aide: t('liens.prerequis_aide') },
  { valeur: 'voir_aussi', libelle: t('liens.voir_aussi'), aide: t('liens.voir_aussi_aide') },
];

export async function lier(source, type, cible) {
  try { return await post(`/taches/${enc(source)}/liens`, { type, cible }); } catch (e) { erreur(e.message); return null; }
}
async function retirer(source, type, cible) {
  try { return await post(`/taches/${enc(source)}/liens/retirer`, { type, cible }); } catch (e) { erreur(e.message); return null; }
}

function ligneLien(ref, type, source, surChangement) {
  return h('li', { class: 'lien' }, pastille(ref.statut),
    h('button', { class: 'lien-titre', type: 'button', title: t('liens.ouvrir', { titre: ref.titre }), onclick: () => ouvrir(ref.id) }, ref.titre || ref.id),
    type ? h('button', { class: 'btn-discret', type: 'button', 'aria-label': t('liens.retirer_label', { titre: ref.titre }),
      onclick: async () => { const r = await retirer(source, type, ref.id); if (r) surChangement(r); } }, t('liens.retirer'))
      : h('span', { class: 'lien-note', title: t('liens.calcule_titre') }, t('liens.calcule')));
}
function groupe(titre, refs, type, source, surChangement) {
  if (!refs.length) return null;
  return h('div', { class: 'lien-groupe' }, h('h4', null, titre),
    h('ul', null, refs.map((r) => ligneLien(r, type, source, surChangement))));
}

export function carteLiens(tache, surChangement) {
  const l = tache.liens || {};
  const [al, ap, va] = [l.alimente || [], l.alimente_par || [], l.voir_aussi || []];
  const [pr, rp] = [l.prerequis || [], l.requis_par || []];
  return h('section', { class: 'liens-carte', 'aria-label': t('liens.titre') },
    h('div', { class: 'liens-tete' }, h('h3', null, t('liens.titre')),
      h('button', { class: 'btn petit', type: 'button', onclick: async () => { const r = await dialogueLier(tache); if (r) surChangement(r); } }, t('liens.lier'))),
    al.length + ap.length + va.length + pr.length + rp.length ? null : h('p', { class: 'vide' }, t('liens.aucun')),
    groupe(t('liens.g_alimente'), al, 'alimente', tache.id, surChangement),
    groupe(t('liens.g_alimente_par'), ap, null, tache.id, surChangement),
    groupe(t('liens.g_prerequis'), pr, 'prerequis', tache.id, surChangement),
    groupe(t('liens.g_requis_par'), rp, null, tache.id, surChangement),
    groupe(t('liens.g_voir_aussi'), va, 'voir_aussi', tache.id, surChangement));
}

// Dialogue : type + recherche (combobox). Résout avec la Tache mise à jour, ou null.
export function dialogueLier(source) {
  return new Promise((resolve) => {
    let cible = null, resultats = [], actif = -1, minuteur = 0, seq = 0, fait = false;
    const fin = (v) => { if (!fait) { fait = true; resolve(v); } };
    const radios = h('fieldset', { class: 'radios' }, h('legend', null, t('liens.type_lien')),
      TYPES_LIEN.map((x, i) => h('label', { class: 'radio-aide' },
        h('input', { type: 'radio', name: 'type', value: x.valeur, checked: i === 0 ? true : null }), ' ', h('b', null, x.libelle),
        h('span', { class: 'aide' }, x.aide))));
    const champ = h('input', { id: 'lier-q', type: 'text', role: 'combobox', 'aria-expanded': 'false', 'aria-controls': 'lier-liste',
      'aria-autocomplete': 'list', autocomplete: 'off', placeholder: t('liens.chercher') });
    const liste = h('ul', { id: 'lier-liste', class: 'resultats', role: 'listbox', 'aria-label': t('liens.resultats'), hidden: true });
    const statut = h('p', { class: 'note', 'aria-live': 'polite' });
    const choix = h('p', { class: 'choix', hidden: true });
    const ok = h('button', { type: 'submit', class: 'btn primaire', disabled: true }, t('liens.valider'));
    const dlg = h('dialog', { class: 'dlg', 'aria-label': t('liens.dlg_label') });
    const form = h('form', { method: 'dialog', class: 'dlg-form' }, h('h3', null, t('liens.dlg_label')), radios,
      h('div', { class: 'champ' }, h('label', { for: 'lier-q' }, t('liens.tache_cible')), champ, liste, statut, choix),
      h('div', { class: 'dlg-actions' }, h('button', { type: 'button', class: 'btn', onclick: () => dlg.close() }, t('liens.annuler')), ok));
    dlg.append(form);

    const marquer = () => {
      [...liste.children].forEach((li, i) => { li.setAttribute('aria-selected', String(i === actif)); li.classList.toggle('actif', i === actif); });
      if (actif >= 0) { champ.setAttribute('aria-activedescendant', `lier-r${actif}`); liste.children[actif]?.scrollIntoView({ block: 'nearest' }); }
      else champ.removeAttribute('aria-activedescendant');
    };
    const choisir = (r) => {
      cible = r; ok.disabled = false; liste.hidden = true; champ.setAttribute('aria-expanded', 'false');
      choix.hidden = false;
      remplacer(choix, t('liens.cible'), h('b', null, r.titre), ' ', h('span', { class: 'fil-mini' }, (r.fil_ariane || []).join(' › ')));
      statut.textContent = '';
    };
    const afficher = () => {
      liste.hidden = !resultats.length; champ.setAttribute('aria-expanded', String(resultats.length > 0));
      remplacer(liste, resultats.map((r, i) => h('li', { id: `lier-r${i}`, role: 'option', 'aria-selected': 'false',
        onmousedown: (e) => { e.preventDefault(); choisir(r); } },
      pastille(r.statut), h('span', { class: 'res-titre' }, r.titre), h('span', { class: 'fil-mini' }, (r.fil_ariane || []).join(' › ')))));
      actif = -1; marquer();
    };
    async function chercher() {
      const q = champ.value.trim(), mon = ++seq;
      if (!q) { resultats = []; afficher(); statut.textContent = ''; return; }
      try {
        const rs = await api(`/recherche?q=${enc(q)}&limite=12`);
        if (mon !== seq) return;
        resultats = (rs || []).filter((r) => r.id !== source.id);
        afficher();
        statut.textContent = resultats.length ? tn('liens.resultats_n', resultats.length) : t('liens.aucune_trouvee');
      } catch (e) { if (mon === seq) statut.textContent = e.message; }
    }
    champ.addEventListener('input', () => {
      cible = null; ok.disabled = true; choix.hidden = true;
      clearTimeout(minuteur); minuteur = setTimeout(chercher, 250);
    });
    champ.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' && resultats.length) { e.preventDefault(); actif = (actif + 1) % resultats.length; marquer(); }
      else if (e.key === 'ArrowUp' && resultats.length) { e.preventDefault(); actif = (actif - 1 + resultats.length) % resultats.length; marquer(); }
      else if (e.key === 'Enter' && actif >= 0) { e.preventDefault(); choisir(resultats[actif]); }
      else if (e.key === 'Escape' && !liste.hidden) { e.stopPropagation(); e.preventDefault(); liste.hidden = true; champ.setAttribute('aria-expanded', 'false'); }
    });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!cible) return;
      ok.disabled = true;
      const r = await lier(source.id, new FormData(form).get('type'), cible.id);
      if (r) { fin(r); dlg.close(); } else ok.disabled = false;
    });
    dlg.addEventListener('close', () => { clearTimeout(minuteur); fin(null); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
    champ.focus();
  });
}
