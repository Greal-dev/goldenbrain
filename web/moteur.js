// Rôle : sélecteur de moteur (harnais + modèle) d'une tâche, d'après GET /harnais.
// Frontières : ne poste rien lui-même — il rend un nœud et appelle `surChoix(harnais, modele)`.
// INV-MOTEUR-1 : un harnais indisponible n'est pas proposé (grisé, motif affiché), sauf s'il est déjà celui de la tâche.
import { h } from './dom.js';
import { api } from './api.js';
import { simple } from './interface.js';
import { t } from './langues.js';

let cache = null;
export async function chargerHarnais() { cache = await api('/harnais'); return cache; }
export const listeHarnais = () => cache || [];

const AUTRE = '__autre';

export function libelleMoteur(harnais, modele) { return simple() ? (modele || t('moteur.modele_defaut_min')) : `${harnais || t('moteur.assistant_defaut_min')} · ${modele || t('moteur.modele_defaut_min')}`; }

export function selecteurMoteur(harnais, modele, surChoix) {
  const liste = listeHarnais();
  const info = liste.find((x) => x.nom === harnais);
  const modeles = info?.modeles || [];
  const dansListe = !modele || modeles.includes(modele);
  const optH = (x) => {
    const off = !x.disponible && x.nom !== harnais;
    return h('option', { value: x.nom, disabled: off ? true : null, selected: x.nom === harnais ? true : null, title: x.disponible ? null : x.motif || t('moteur.indisponible') },
      x.disponible ? x.nom : t('moteur.indisponible_motif', { nom: x.nom, motif: x.motif || t('moteur.raison_inconnue') }));
  };
  const selH = h('select', { class: 'f-moteurs', 'aria-label': t('moteur.assistant'), title: t('moteur.assistant_titre') },
    h('option', { value: '', selected: !harnais ? true : null }, t('moteur.assistant_defaut')),
    harnais && !info ? h('option', { value: harnais, selected: true }, harnais) : null, liste.map(optH));
  const selM = h('select', { 'aria-label': t('moteur.modele') },
    h('option', { value: '', selected: !modele ? true : null }, info?.modele_defaut ? t('moteur.modele_defaut_avec', { modele: info.modele_defaut }) : t('moteur.modele_defaut')),
    modeles.map((m) => h('option', { value: m, selected: m === modele ? true : null }, m)),
    h('option', { value: AUTRE, selected: !dansListe ? true : null }, t('moteur.autre')));
  const saisie = h('input', { type: 'text', 'aria-label': t('moteur.modele_libre'), placeholder: t('moteur.modele_identifiant'), value: dansListe ? '' : modele, hidden: dansListe ? true : null, autocomplete: 'off' });
  selH.addEventListener('change', () => surChoix(selH.value, ''));
  selM.addEventListener('change', () => {
    if (selM.value === AUTRE) { saisie.hidden = false; saisie.focus(); } else { saisie.hidden = true; surChoix(selH.value, selM.value); }
  });
  const valider = () => { if (!saisie.hidden && saisie.value.trim() !== (dansListe ? '' : modele)) surChoix(selH.value, saisie.value.trim()); };
  saisie.addEventListener('change', valider);
  saisie.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); valider(); } });
  return h('span', { class: 'moteur' }, h('span', { class: 'moteur-lib' }, t('moteur.libelle')), selH, selM, saisie);
}
