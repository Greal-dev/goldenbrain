// Rôle : aperçus déroulants de la barre haute (INV-DEROULANT-1) — « Aujourd'hui », « Décisions », « À moi », « En cours » : cinq lignes
// au plus et « Tout voir » vers la page pleine ; pastille « Infos » qui déroule les bandeaux d'information (poste réservé, mise à jour,
// réseau), une alerte qui exige un geste restant, elle, dans la pile des bandeaux (bandeaux.js).
// Frontières : lit GET /aujourdhui et GET /decisions à l'ouverture, S (arbre, état) sinon ; n'écrit rien ; les bandeaux d'information
// sont dessinés par leurs modules (bandeau.js, version.js, maj-auto.js), ce module ne fait que les compter.
import { t } from './langues.js';
import { h, $, remplacer, pastille, pourMoi, libelleStatut, depuis } from './dom.js';
import { S, on, emit, ouvrir, ouvrirVue, parcourir, erreur } from './store.js';
import { api } from './api.js';
import { libelleEcheance } from './temps.js';
import { deroulant } from './deroulant.js';

const MAX = 5;
let version = 0;

function liste(items, vide) {
  if (!items.length) return h('p', { class: 'vide' }, vide);
  return h('ul', { class: 'apercu-liste' }, items.slice(0, MAX).map((x) => h('li', null,
    h('button', { type: 'button', 'data-id': x.id, title: x.titre, onclick: () => ouvrir(x.id) },
      x.statut ? pastille(x.statut) : null, h('span', { class: 'ap-titre' }, x.titre), h('span', { class: `ap-sous${x.retard ? ' retard' : ''}` }, x.sous || '')))));
}

// Un appel lent ne redessine pas un panneau refermé ou rouvert depuis.
async function charger(corps, d, chemin, lignes, vide) {
  const moi = ++version;
  remplacer(corps, h('p', { class: 'vide' }, t('apercus.chargement')));
  try {
    const r = await api(chemin);
    if (moi === version && d.ouvert()) remplacer(corps, liste(lignes(r), vide));
  } catch (e) { erreur(e.message); }
}

function lignesAujourdhui(r) {
  const vus = new Set(), l = [];
  for (const g of r.groupes) for (const x of g.taches) if (!vus.has(x.id)) { vus.add(x.id); l.push({ ...x, sous: libelleEcheance(x.echeance, x.retard) || g.titre }); }
  return l;
}
const lignesDecisions = (r) => r.decisions.map((x) => ({ id: x.tache, titre: x.titre, statut: x.statut, sous: x.libelle }));
const aMoi = () => [...parcourir(S.arbre)].filter((n) => n.type === 'tache' && pourMoi(n)).map((n) => ({ id: n.id, titre: n.titre, statut: n.statut, sous: libelleStatut(n.statut) }));
const enCours = () => [...(S.etat.tours || []).map((x) => ({ id: x.tache, titre: x.titre, sous: depuis(x.depuis) })),
  ...(S.etat.file || []).map((f) => ({ id: f.tache, titre: f.titre, sous: t('apercus.en_file') }))];

// Infos : compteur des bandeaux d'information visibles ; « alerte » si l'un demande un geste (réseau perdu, serveur à redémarrer).
function compterInfos(d) {
  const vus = [...$('#panneau-etat').querySelectorAll(':scope > [role="status"]')].filter((el) => !el.hidden);
  const b = $('#btn-etat');
  b.hidden = !vus.length;
  $('#n-etat').textContent = String(vus.length);
  b.classList.toggle('alerte', vus.some((el) => ['reseau-perdu', 'maj-serveur'].includes(el.id)));
  if (!vus.length) d.fermer(); // plus rien à dire : un panneau vide, même épinglé, ne reste pas ouvert
}

export function initApercus() {
  const tv = t('apercus.tout_voir');
  const auj = deroulant({ bouton: $('#btn-aujourdhui'), panneau: $('#panneau-aujourdhui'), titre: t('apercus.aujourdhui'),
    toutVoir: { libelle: tv, agir: () => ouvrirVue('aujourdhui') },
    remplir: (c) => charger(c, auj, '/aujourdhui', lignesAujourdhui, t('apercus.rien_aujourdhui')) });
  const dec = deroulant({ bouton: $('#btn-decisions'), panneau: $('#panneau-decisions'), titre: t('apercus.decisions'),
    toutVoir: { libelle: tv, agir: () => ouvrirVue('decisions') },
    remplir: (c) => charger(c, dec, '/decisions', lignesDecisions, t('apercus.rien_decisions')) });
  const moi = deroulant({ bouton: $('#btn-amoi'), panneau: $('#panneau-amoi'), titre: t('apercus.a_moi'),
    toutVoir: { libelle: t('apercus.filtrer_arbre'), agir: () => { S.filtreAMoi = true; emit('filtre'); } },
    remplir: (c) => remplacer(c, liste(aMoi(), t('apercus.rien_a_moi'))) });
  const trav = deroulant({ bouton: $('#btn-travaux'), panneau: $('#panneau-travaux'), titre: t('apercus.en_cours'),
    toutVoir: { libelle: tv, agir: () => ouvrirVue('travaux') },
    remplir: (c) => remplacer(c, liste(enCours(), t('apercus.rien_en_cours'))) });
  on('etat', () => { trav.redessiner(); moi.redessiner(); });
  on('arbre', () => moi.redessiner());
  const infos = deroulant({ bouton: $('#btn-etat'), panneau: $('#panneau-etat'), titre: t('apercus.infos'), garder: true });
  new MutationObserver(() => compterInfos(infos)).observe($('#panneau-etat'), { subtree: true, attributes: true, attributeFilter: ['hidden'] });
  compterInfos(infos);
}
