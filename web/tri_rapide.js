// Rôle : « Tri rapide » des décisions — une carte plein écran à la fois, un geste au clavier, au clic ou au doigt.
// Frontières : file figée à l'ouverture (copie de la liste de decisions.js) ; chaque geste passe par une route existante
// (valider, renvoyer, temps, messages, propositions) ; aucune route nouvelle. À la sortie : emit('recharger') puis `fin`.
import { h, remplacer } from './dom.js';
import { post } from './api.js';
import { ouvrir, emit, erreur } from './store.js';
import { description } from './propositions.js';
import { t } from './langues.js';

// Échéance locale (AAAA-MM-JJ) à sept jours : « sv » donne ce format sans passer par l'UTC.
const dansUneSemaine = () => { const d = new Date(); d.setDate(d.getDate() + 7); return d.toLocaleDateString('sv'); };

// Gestes d'une carte : [touche, clé du libellé, action, clé du champ texte (l'action reçoit alors le texte)].
function gestesDe(d) {
  const tache = `/taches/${d.tache}`, prop = d.proposition && `/propositions/${d.proposition.n}`;
  const reporter = ['p', 'tri.reporter', () => post(`${tache}/temps`, { echeance: dansUneSemaine() })];
  switch (d.genre) {
    case 'validation': return [['a', 'tri.accepter', () => post(`${tache}/valider`, {})],
      ['r', 'tri.refuser', (texte) => post(`${tache}/renvoyer`, { texte }), 'tri.motif'], reporter];
    case 'scan':
    case 'proposition': return [['a', 'tri.accepter', () => post(`${prop}/accepter`)], ['r', 'tri.refuser', () => post(`${prop}/refuser`)]];
    case 'reponse': return [['e', 'tri.repondre', (texte) => post(`${tache}/messages`, { texte }), 'tri.reponse'], reporter];
    case 'echeance': return [reporter];
    default: return [];
  }
}

function texteDe(d) {
  if (d.genre === 'validation') return d.resultat || d.fait || t('decisions.non_indique');
  if (d.proposition) return [description(d.proposition), d.proposition.motif].filter(Boolean).join(' — ');
  return d.question || '';
}

export function triRapide(liste, fin = () => {}) {
  const file = liste.filter((d) => d.genre !== 'lot');
  const traitees = new Set();
  let i = 0, champ = null, occupe = false;
  const dlg = h('dialog', { class: 'tri', 'aria-label': t('tri.titre'), tabindex: '-1' });

  const quitter = () => dlg.close();
  const aller = (j) => { i = j; champ = null; dessiner(); };
  const precedente = () => { let j = i - 1; while (j >= 0 && traitees.has(file[j].id)) j--; if (j >= 0) aller(j); };
  async function jouer(d, geste, texte) {
    if (occupe) return;
    occupe = true;
    try { await geste[2](texte); traitees.add(d.id); aller(i + 1); } catch (e) { erreur(e.message); } finally { occupe = false; }
  }
  function declencher(d, geste) {
    if (geste[3]) { champ = geste; dessiner(); } else jouer(d, geste);
  }

  function dessiner() {
    const d = file[i];
    if (!d) {
      remplacer(dlg, h('p', { class: 'tri-fini' }, t('tri.fini')), h('button', { class: 'btn primaire', type: 'button', id: 'tri-fermer', onclick: quitter }, t('tri.fermer')));
      dlg.querySelector('#tri-fermer').focus();
      return;
    }
    const gestes = gestesDe(d);
    const bouton = (touche, libelle, f, primaire) => h('button', { class: `btn${primaire ? ' primaire' : ''}`, type: 'button', 'data-touche': touche, onclick: f }, libelle);
    const saisie = champ && h('input', { type: 'text', class: 'tri-champ', 'aria-label': t(champ[3]), placeholder: t(champ[3]),
      onkeydown: (e) => {
        if (e.key === 'Enter' && e.target.value.trim()) { e.preventDefault(); jouer(d, champ, e.target.value.trim()); }
        if (e.key === 'Escape') { e.preventDefault(); champ = null; dessiner(); }
      } });
    remplacer(dlg,
      h('p', { class: 'tri-compte' }, t('tri.compteur', { n: i + 1, total: file.length })),
      h('p', { class: 'tri-tete' }, h('span', { class: 'tag' }, d.libelle), ' ', h('b', null, d.titre)),
      h('p', { class: 'tri-texte' }, texteDe(d)),
      saisie,
      h('div', { class: 'tri-actions' },
        gestes.map((g, k) => bouton(g[0], t(g[1], { touche: g[0].toUpperCase() }), () => declencher(d, g), k === 0)),
        d.tache ? bouton('o', t('tri.ouvrir', { touche: 'O' }), () => { quitter(); ouvrir(d.tache); }) : null,
        bouton('arrowleft', t('tri.precedente'), precedente),
        bouton(' ', t('tri.passer'), () => aller(i + 1)),
        bouton('escape', t('tri.quitter'), quitter)));
    (saisie || dlg).focus();
  }

  dlg.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
    const d = file[i], k = e.key.toLowerCase();
    // preventDefault : sinon la touche, rendue au bouton « Tri rapide » qui reprend le focus à la fermeture, rouvrirait le tri
    if (!d) { if (k === 'enter' || k === ' ') { e.preventDefault(); quitter(); } return; }
    if (k === 'arrowright' || k === ' ') { e.preventDefault(); aller(i + 1); }
    else if (k === 'arrowleft') precedente();
    else if (k === 'o' && d.tache) { quitter(); ouvrir(d.tache); }
    else { const g = gestesDe(d).find((x) => x[0] === k); if (g) { e.preventDefault(); declencher(d, g); } }
  });
  dlg.addEventListener('close', () => { dlg.remove(); emit('recharger'); fin(); });
  document.body.append(dlg);
  dlg.showModal();
  dessiner();
}
