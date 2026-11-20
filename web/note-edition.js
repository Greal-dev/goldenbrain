// Rôle : éditeur de texte brut d'une note (textarea à chasse fixe), enregistrement, protection des modifications, conflit 409.
// Frontières : API PUT /vault/note ; ne rend pas la note (note-vue.js le fait via `surFin`) ; une seule édition à la fois.
// INV-NOTE-2 (côté interface) : l'enregistrement renvoie le mtime_ns lu ; en cas de 409 rien n'est écrasé sans choix explicite.
import { h, remplacer, heure } from './dom.js';
import { S, emit, erreur } from './store.js';
import { api } from './api.js';
import { t, tn } from './langues.js';

const enc = encodeURIComponent;
let actif = null, dernierSave = 0;
const avantDecharge = (e) => { e.preventDefault(); e.returnValue = ''; };
const sale = () => !!actif && actif.ta.value !== actif.original;
export const enEdition = () => !!actif;
export const enregistrementRecent = () => Date.now() - dernierSave < 2000; // l'événement SSE de notre propre écriture n'est pas « ailleurs »

function nettoyer() {
  window.removeEventListener('beforeunload', avantDecharge);
  if (S.garde === garde) S.garde = null;
  actif = null;
}
// Garde de navigation (store.js) : confirmer avant de perdre des modifications.
function garde() {
  if (sale() && !confirm(t('note_edition.garde'))) return false;
  nettoyer();
  return true;
}

function insérer(ta, x) {
  if (!document.execCommand('insertText', false, x)) { ta.setRangeText(x, ta.selectionStart, ta.selectionEnd, 'end'); ta.dispatchEvent(new Event('input')); }
}
// Tabulation = 2 espaces ; sur plusieurs lignes, indentation (Maj+Tab : retrait) du bloc entier.
function indenter(ta, sens) {
  const { selectionStart: a, selectionEnd: b, value: v } = ta;
  if (sens > 0 && a === b) return insérer(ta, '  ');
  const debut = v.lastIndexOf('\n', a - 1) + 1;
  const bloc = v.slice(debut, b);
  const nv = sens > 0 ? bloc.replace(/^/gm, '  ') : bloc.replace(/^( {1,2}|\t)/gm, '');
  ta.setSelectionRange(debut, b);
  insérer(ta, nv);
  ta.setSelectionRange(debut, debut + nv.length);
}

// Deux versions côte à côte ; renvoie 'mienne' | 'courante' | null (continuer à éditer).
function trancher(mienne, courante) {
  return new Promise((resolve) => {
    const lignes = (t) => t.split('\n');
    const [lm, lc] = [lignes(mienne), lignes(courante.contenu)];
    const [sm, sc] = [new Set(lm), new Set(lc)];
    const col = (titre, ls, autre) => h('section', { class: 'cf-col' }, h('h4', null, titre),
      h('pre', { class: 'cf-texte', tabindex: '0', 'aria-label': titre }, ls.map((l, i) => h('span', { class: autre.has(l) ? 'cf-l' : 'cf-l cf-diff', 'data-n': i + 1 }, l || ' ', '\n'))));
    let choix = null;
    // La date vient s'intercaler en gras dans la phrase traduite : l'ordre des mots change selon la langue.
    const [avant, apres] = t('note_edition.conflit_texte', { heure: '\u0001' }).split('\u0001');
    const fin = (c) => () => { choix = c; dlg.close(); };
    const dlg = h('dialog', { class: 'dlg conflit', 'aria-labelledby': 'cf-titre' }, h('div', { class: 'dlg-form' },
      h('h3', { id: 'cf-titre' }, t('note_edition.conflit_titre')),
      h('p', { class: 'dlg-texte' }, avant, h('b', null, heure(courante.maj) || t('note_edition.maintenant')), apres),
      h('div', { class: 'cf-grille' }, col(tn('note_edition.ma_version', lm.length), lm, sc), col(tn('note_edition.version_courante', lc.length), lc, sm)),
      h('div', { class: 'dlg-actions' },
        h('button', { type: 'button', class: 'btn', onclick: fin(null) }, t('note_edition.continuer')),
        h('button', { type: 'button', class: 'btn', onclick: fin('courante') }, t('note_edition.reprendre')),
        h('button', { type: 'button', class: 'btn primaire', onclick: fin('mienne') }, t('note_edition.garder')))));
    dlg.addEventListener('close', () => { dlg.remove(); resolve(choix); });
    document.body.append(dlg);
    dlg.showModal();
    dlg.querySelector('.primaire').focus();
  });
}

export function editer({ note, zone, barre, surFin }) {
  if (actif) return;
  const ta = h('textarea', { class: 'n-editeur', spellcheck: 'false', 'aria-label': t('note_edition.edition_aria', { nom: note.nom }), 'aria-describedby': 'n-aide-edition', wrap: 'soft' });
  ta.value = note.contenu;
  actif = { ta, original: ta.value, mtime: note.mtime_ns, note, enCours: false };
  const avert = h('div', { class: 'n-avert', role: 'alert', hidden: true }, h('span', null, t('note_edition.avert')),
    h('button', { type: 'button', class: 'btn petit', onclick: () => comparer() }, t('note_edition.comparer')));
  const etat = h('span', { class: 'n-etat', role: 'status' });
  const pos = h('span', { class: 'n-pos' });
  const btnSave = h('button', { type: 'button', class: 'btn primaire petit', onclick: () => enregistrer() }, t('note_edition.enregistrer'));
  const btnFin = h('button', { type: 'button', class: 'btn petit', onclick: () => terminer(), title: t('note_edition.terminer_titre') }, t('note_edition.terminer'));
  const majPos = () => {
    const v = ta.value, n = v.slice(0, ta.selectionStart).split('\n').length;
    pos.textContent = t('note_edition.ligne', { n, total: v.split('\n').length });
  };
  let raf = 0;
  const majEtat = () => {
    const s = sale();
    etat.textContent = s ? t('note_edition.modifie') : (dernierSave && actif.enregistre ? t('note_edition.enregistre') : t('note_edition.inchange'));
    etat.className = `n-etat${s ? ' modifie' : ''}`;
    btnSave.disabled = !s;
    (s ? window.addEventListener : window.removeEventListener).call(window, 'beforeunload', avantDecharge);
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(majPos);
  };
  const sortir = (n) => { nettoyer(); surFin(n); };
  async function terminer() { if (sale() && !confirm(t('note_edition.abandon'))) return; sortir(actif.note); }

  async function enregistrer() {
    if (!actif || actif.enCours || !sale()) return true;
    const envoye = ta.value;
    actif.enCours = true; dernierSave = Date.now();
    try {
      const n = await api('/vault/note', { methode: 'PUT', corps: { chemin: note.chemin, contenu: envoye, mtime_ns: actif.mtime } });
      if (!actif) return true;
      Object.assign(actif, { mtime: n.mtime_ns, original: envoye, note: n, enregistre: true });
      avert.hidden = true; dernierSave = Date.now();
      emit('note-ecrite', note.chemin);
      majEtat();
      return true;
    } catch (e) {
      dernierSave = 0; // rien n'a été écrit : un événement SSE qui suit vient bien d'ailleurs
      if (e.statut !== 409) { erreur(e.message); return false; }
      return resoudre(envoye);
    } finally { if (actif) actif.enCours = false; }
  }
  // 409 ou comparaison volontaire : la version courante vient du serveur (le corps de l'erreur n'est pas supposé).
  async function resoudre(mienne) {
    let courante;
    try { courante = await api(`/vault/note?chemin=${enc(note.chemin)}`); } catch (e) { erreur(e.message); return false; }
    if (courante.contenu === mienne) { actif.mtime = courante.mtime_ns; actif.original = mienne; actif.note = courante; avert.hidden = true; majEtat(); return true; }
    const [a, b, haut] = [ta.selectionStart, ta.selectionEnd, ta.scrollTop];
    const c = await trancher(mienne, courante);
    if (!actif) return false;
    ta.focus({ preventScroll: true });
    ta.setSelectionRange(a, b); ta.scrollTop = haut; // le dialogue modal a fait perdre le curseur
    if (c === 'courante') {
      ta.value = courante.contenu;
      Object.assign(actif, { original: ta.value, mtime: courante.mtime_ns, note: courante, enregistre: false });
      avert.hidden = true; majEtat();
      return true;
    }
    if (c === 'mienne') { actif.mtime = courante.mtime_ns; actif.enCours = false; return enregistrer(); }
    return false;
  }
  const comparer = () => resoudre(ta.value);

  ta.addEventListener('input', majEtat);
  for (const ev of ['keyup', 'click', 'select']) ta.addEventListener(ev, () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(majPos); });
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.ctrlKey && !e.altKey && !e.metaKey) { e.preventDefault(); indenter(ta, e.shiftKey ? -1 : 1); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); enregistrer(); }
    else if (e.key === 'Escape') { e.preventDefault(); terminer(); }
  });
  S.garde = garde;
  remplacer(barre, btnSave, btnFin, etat, pos);
  remplacer(zone, h('div', { class: 'n-edit' }, avert, ta,
    h('p', { id: 'n-aide-edition', class: 'n-aide' }, t('note_edition.aide'))));
  majEtat();
  ta.focus({ preventScroll: true });
  ta.setSelectionRange(0, 0);
}

// SSE `note` pendant l'édition : on ne remplace rien, on prévient.
export function signalerChangement() {
  const a = document.querySelector('.n-avert');
  if (a && actif) a.hidden = false;
}
