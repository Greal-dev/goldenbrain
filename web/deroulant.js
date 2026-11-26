// Rôle : composant « déroulant » unique (INV-DEROULANT-1) — une pastille (ou un intercalaire) avec compteur déroule un panneau
// flottant : au survol après un délai d'intention, au clic, au clavier, au toucher (= clic). Il se referme en sortant (survol),
// au reclic, à Échap ou au clic extérieur ; l'épingle le garde ouvert. Un seul déroulant ouvert à la fois, hors épinglés.
// Frontières : DOM seulement ; le contenu est dessiné par le module appelant (`remplir(corps)`), la mise en page est dans
// deroulant.css (flotte au-dessus du contenu, feuille montante au téléphone). Les rails (arbre, notes) partagent `intention()`.
import { h } from './dom.js';
import { t } from './langues.js';

export const OUVRIR = 150, FERMER = 350; // ms : délai d'intention ; tolérance de sortie (diagonale vers le panneau)
const souris = (e) => e.pointerType === 'mouse';
const tous = new Set();

// Survol à la souris : ouvre après OUVRIR ms de présence, referme FERMER ms après la sortie ; rentrer annule la fermeture.
export function intention(zones, ouvrir, fermer, permis = () => true) {
  let m = 0;
  for (const z of zones) {
    z.addEventListener('pointerenter', (e) => { if (!souris(e) || !permis()) return; clearTimeout(m); m = setTimeout(ouvrir, OUVRIR); });
    z.addEventListener('pointerleave', (e) => { if (!souris(e)) return; clearTimeout(m); m = setTimeout(fermer, FERMER); });
  }
  return () => clearTimeout(m);
}

// o : { bouton, panneau, remplir?(corps), garder?, titre?, toutVoir?: { libelle, agir }, epingle?: bool initial, surEpingle?(bool), permis?() }
export function deroulant(o) {
  const { bouton, panneau } = o;
  const corps = o.garder ? panneau : h('div', { class: 'der-corps' }); // garder : le panneau a déjà son contenu, tenu à jour par l'appelant
  const pin = h('button', { type: 'button', class: 'der-epingle', 'aria-pressed': 'false', title: t('deroulant.epingler'), 'aria-label': t('deroulant.epingler'),
    onclick: () => epingler(!d.epingle) }, '📌');
  const tout = o.toutVoir ? h('button', { type: 'button', class: 'btn petit der-tout', 'data-tout-voir': '', onclick: () => { fermer(true); o.toutVoir.agir(); } }, o.toutVoir.libelle) : null;
  panneau.classList.add('deroulant');
  const tete = h('div', { class: 'der-tete' }, o.titre ? h('b', { class: 'der-titre' }, o.titre) : null, tout, pin);
  if (o.garder) panneau.prepend(tete); else panneau.replaceChildren(tete, corps);
  bouton.setAttribute('aria-expanded', 'false');
  bouton.setAttribute('aria-haspopup', 'true');
  if (panneau.id) bouton.setAttribute('aria-controls', panneau.id);
  const d = { mode: null, epingle: false, bouton, panneau, ouvrir: () => ouvrir('clic'), fermer: () => fermer(true), ouvert: () => !!d.mode, epingler: (v) => epingler(v), redessiner: () => { if (d.mode) o.remplir?.(corps); } };

  function ouvrir(mode) {
    for (const x of tous) if (x !== d && x.mode && !x.epingle) x.fermer();
    const deja = !!d.mode;
    d.mode = mode;
    panneau.hidden = false;
    bouton.setAttribute('aria-expanded', 'true');
    if (!deja) o.remplir?.(corps);
    recaler();
  }
  // Une pastille près du bord droit : le panneau glisse vers la gauche plutôt que de déborder de l'écran.
  function recaler() {
    panneau.style.translate = '';
    if (getComputedStyle(panneau).position !== 'absolute') return; // feuille du bas, ou « Détails » épinglé dans le flux
    const r = panneau.getBoundingClientRect(), trop = r.right - (innerWidth - 8);
    if (trop > 0) panneau.style.translate = `${-Math.min(trop, r.left - 8)}px 0`;
  }
  function fermer(force) {
    if (!d.mode || (d.epingle && !force)) return;
    if (d.epingle) epingler(false);
    d.mode = null;
    panneau.hidden = true;
    bouton.setAttribute('aria-expanded', 'false');
    if (panneau.contains(document.activeElement)) bouton.focus();
  }
  function epingler(v) {
    d.epingle = v;
    pin.setAttribute('aria-pressed', String(v));
    panneau.classList.toggle('epingle', v);
    if (v && !d.mode) ouvrir('clic');
    o.surEpingle?.(v);
  }
  const annuler = intention([bouton, panneau], () => { if (!d.mode) ouvrir('survol'); }, () => { if (d.mode === 'survol') fermer(); }, o.permis || (() => true));
  bouton.addEventListener('click', (e) => {
    annuler();
    if (d.mode === 'survol') d.mode = 'clic'; // le clic fixe ce que le survol a montré
    else if (d.mode) fermer(true);
    else {
      ouvrir('clic');
      if (e.detail === 0) panneau.querySelector('button, a[href], input, select, textarea, summary, [tabindex]')?.focus(); // ouvert au clavier
    }
  });
  if (o.epingle) epingler(true);
  for (const x of tous) if (!x.bouton.isConnected) tous.delete(x); // « Détails » d'une tâche refermée
  tous.add(d);
  return d;
}

// Un seul jeu d'écouteurs pour tous les déroulants. pointerdown (et non click) : un redessin du panneau pendant le clic
// détacherait la cible, qui paraîtrait alors extérieure.
document.addEventListener('pointerdown', (e) => {
  const chemin = e.composedPath();
  for (const d of tous) if (d.mode && !d.epingle && !chemin.includes(d.bouton) && !chemin.includes(d.panneau)) d.fermer();
}, true);
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  for (const d of tous) if (d.mode && (!d.epingle || d.panneau.contains(document.activeElement))) d.fermer();
});
