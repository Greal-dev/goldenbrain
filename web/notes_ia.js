// Bouton « IA » du panneau Notes : résumer, corriger, synthétiser la sélection ou toutes les notes.
// Rôle : déterminer la portée (sélection dans une note, sinon toutes les notes), demander une proposition
// (POST /notes/ia), l'afficher (différence pour « corriger »), l'appliquer d'un geste par PUT /notes/{n},
// et permettre d'annuler en réécrivant le texte d'origine.
// Frontières : rien n'est écrit sans le geste « Remplacer » ou « Insérer » ; seule la portée part au modèle.
// Invariant porté : INV-EXECUTANT-3.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { rendreMd } from './md.js';
import { t } from './langues.js';

const enc = encodeURIComponent;
const ACTIONS = [['resumer', t('notes_ia.resumer')], ['corriger', t('notes_ia.corriger')], ['synthetiser', t('notes_ia.synthetiser')]];
const LIBELLE = Object.fromEntries(ACTIONS);

// Différence mot à mot (plus longue sous-suite commune) ; au-delà d'une taille raisonnable, rien.
function difference(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/), n = A.length, m = B.length;
  if (n * m > 2e6) return null;
  const L = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && A[i] === B[j]) { out.push(A[i]); i++; j++; }
    else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) out.push(h('ins', null, B[j++]));
    else out.push(h('del', null, A[i++]));
  }
  return h('div', { class: 'ia-diff' }, ...out);
}

// Portée : la sélection si elle tombe dans la liste des notes, sinon toutes les notes.
function portee(liste, notes) {
  const s = window.getSelection();
  const txt = s && !s.isCollapsed ? s.toString().trim() : '';
  if (txt && liste.contains(s.anchorNode) && liste.contains(s.focusNode)) {
    const li = (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement).closest('.note-t');
    const autre = (s.focusNode.nodeType === 1 ? s.focusNode : s.focusNode.parentElement).closest('.note-t');
    const n = li && li === autre ? Number(li.dataset.n) : null;
    // La sélection se retrouve-t-elle telle quelle dans le texte source de la note ? (Markdown rendu)
    const debut = n === null ? -1 : notes[n].texte.indexOf(txt);
    return { nom: t('notes_ia.portee_selection'), texte: txt, n, debut: debut >= 0 && notes[n].texte.indexOf(txt, debut + 1) < 0 ? debut : -1 };
  }
  const texte = notes.length === 1 ? notes[0].texte : notes.map((x) => `### ${x.quand}\n${x.texte}`).join('\n\n');
  return { nom: t('notes_ia.portee_toutes'), texte, n: notes.length === 1 ? 0 : null, debut: notes.length === 1 ? 0 : -1, tout: true };
}

// `etat()` : { id, notes } de la tâche affichée ; `apres()` relit la tâche après une écriture.
export function creerIA(liste, etat, apres, erreur) {
  const zone = h('div', { class: 'ia-zone' });
  const fermer = () => remplacer(zone);

  async function ecrire(n, texte, bouton) {
    bouton.disabled = true;
    try { await api(`/taches/${enc(etat().id)}/notes/${etat().notes[n]?.n ?? n}`, { methode: 'PUT', corps: { texte } }); apres(); return true; }
    catch (e) { erreur(e.message); bouton.disabled = false; return false; }
  }

  // Après application : l'original reste récupérable d'un clic.
  function annulable(n, avant) {
    const b = h('button', { class: 'btn petit', type: 'button' }, t('notes_ia.annuler_modif'));
    b.addEventListener('click', async () => { if (await ecrire(n, avant, b)) fermer(); });
    remplacer(zone, h('div', { class: 'ia-fait' }, h('span', null, t('notes_ia.appliquee')), b,
      h('button', { class: 'btn petit', type: 'button', onclick: fermer }, t('notes_ia.fermer'))));
  }

  function montrer(action, p, r) {
    const cout = r.cout == null ? t('notes_ia.cout_inconnu') : t('notes_ia.cout', { cout: r.cout.toFixed(4) });
    const tete = h('div', { class: 'ia-tete' }, h('b', null, t('notes_ia.titre_portee', { action: LIBELLE[action], portee: p.nom })),
      h('span', { class: 'ia-cout' }, `${cout} · ${r.harnais}${r.modele ? ' / ' + r.modele : ''}`));
    if (r.erreur) {
      remplacer(zone, h('div', { class: 'ia-prop' }, tete, h('p', { class: 'erreur' }, r.erreur),
        h('div', { class: 'note-gestes' }, h('button', { class: 'btn petit', type: 'button', onclick: fermer }, t('notes_ia.fermer'))))); return;
    }
    const corps = action === 'corriger' ? (difference(r.original, r.proposition) || rendreMd(h('div', { class: 'md' }), r.proposition))
      : rendreMd(h('div', { class: 'md' }), r.proposition);
    const notes = etat().notes;
    // Remplacer exige de retrouver la portée dans le texte source d'une note ; « Insérer » ajoute sous la portée
    // (sous la dernière note pour « toutes les notes »).
    const cible = p.debut >= 0 ? p.n : (p.tout ? notes.length - 1 : p.n);
    const avant = cible == null ? null : notes[cible].texte;
    const fin = p.debut >= 0 ? p.debut + p.texte.length : (avant || '').length;
    const remplacerB = h('button', { class: 'btn primaire petit', type: 'button', disabled: p.debut < 0 ? true : null,
      title: p.debut < 0 ? t('notes_ia.hors_portee') : null }, t('notes_ia.remplacer'));
    const insererB = h('button', { class: 'btn petit', type: 'button', disabled: cible == null || (!p.tout && p.debut < 0) ? true : null }, t('notes_ia.inserer'));
    remplacerB.addEventListener('click', async () => {
      if (await ecrire(cible, avant.slice(0, p.debut) + r.proposition + avant.slice(fin), remplacerB)) annulable(cible, avant);
    });
    insererB.addEventListener('click', async () => {
      const ajout = `\n\n**${LIBELLE[action]} (IA)**\n\n${r.proposition}`;
      if (await ecrire(cible, avant.slice(0, fin) + ajout + avant.slice(fin), insererB)) annulable(cible, avant);
    });
    remplacer(zone, h('div', { class: 'ia-prop' }, tete, corps, h('div', { class: 'note-gestes' },
      h('button', { class: 'btn petit', type: 'button', onclick: fermer }, t('notes_ia.annuler')), insererB, remplacerB)));
  }

  async function lancer(action) {
    const { id, notes } = etat();
    if (!notes.length) { erreur(t('notes_ia.aucune_note')); return; }
    const p = portee(liste, notes);
    remplacer(zone, h('div', { class: 'ia-prop' }, h('div', { class: 'ia-tete' }, h('b', null, t('notes_ia.titre_portee', { action: LIBELLE[action], portee: p.nom })), h('span', null, t('notes_ia.en_cours')))));
    try { montrer(action, p, await post(`/taches/${enc(id)}/notes/ia`, { action, texte: p.texte })); }
    catch (e) { fermer(); erreur(e.message); }
  }

  // `mousedown` empêché : le clic sur un bouton ne doit pas effacer la sélection qui fixe la portée.
  const barre = h('div', { class: 'ia-barre', role: 'toolbar', 'aria-label': t('notes_ia.barre') },
    h('span', { class: 'ia-label', title: t('notes_ia.ia_titre') }, t('notes_ia.ia')),
    ...ACTIONS.map(([a, lib]) => h('button', { class: 'btn petit', type: 'button', 'data-ia': a,
      onmousedown: (e) => e.preventDefault(), onclick: () => lancer(a) }, lib)));
  return { barre, zone };
}
