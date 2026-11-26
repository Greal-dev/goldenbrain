// Rôle : signe de vie des tours (INV-VIGIE-1, INV-VIGIE-2) — phrase d'activité, raison d'attente, alerte de silence
// ou d'exploration prolongée, et gestes humains (arrêter le processus bloquant, arrêter le tour, attendre).
// Frontières : lit `signe` / `raison` servis par l'API ; aucun geste sans clic.
import { h, depuis, remplacer } from './dom.js';
import { emit, erreur, ouvrir } from './store.js';
import { post } from './api.js';
import { t } from './langues.js';

const enc = encodeURIComponent;
const geste = (chemin, corps = {}) => post(chemin, corps).then(() => emit('recharger')).catch((x) => erreur(x.message));

function gestes(ident, s) {
  const b = (txt, f, titre, cls = '') => h('button', { type: 'button', class: `btn petit${cls}`, title: titre, onclick: (e) => { e.stopPropagation(); f(); } }, txt);
  const bloquant = s.diagnostic?.bloquant;
  return h('span', { class: 'vie-gestes' },
    bloquant ? b(t('vigie.arreter_bloquant', { nom: bloquant.nom }), () => geste(`/taches/${enc(ident)}/vigie/arreter-enfant`, { pid: bloquant.pid }),
      t('vigie.arreter_bloquant_titre', { commande: bloquant.commande }), ' danger') : null,
    b(t('vigie.arreter_seance'), () => geste(`/taches/${enc(ident)}/arret`), t('vigie.arreter_seance_titre'), ' danger'),
    b(t('vigie.attendre'), () => geste(`/taches/${enc(ident)}/vigie/attendre`), t('vigie.attendre_titre')));
}

const texteSilence = (s) => t('vigie.silencieux', { duree: depuis(s.depuis) });
const diagnostic = (s) => s.diagnostic?.phrase || t('vigie.diagnostic_en_cours');
const texteExploration = (s) => t('vigie.exploration_texte', { n: s.lectures });

// Ligne d'activité de la tâche ouverte : phrase et fraîcheur, silence diagnostiqué, ou raison d'attente.
export function ligneVie(ident, s, raison) {
  if (s?.silencieux) {
    return h('div', { class: 'vie silence', role: 'alert', 'data-id': 'vie-silence' },
      h('b', null, texteSilence(s)), h('span', { class: 'vie-diag', 'data-id': 'vie-diag' }, ` — ${diagnostic(s)}`), gestes(ident, s));
  }
  if (s) {
    return h('div', { class: 'vie', 'data-id': 'vie-phrase', title: s.etape ? t('vigie.derniere_etape', { etape: s.etape }) : null },
      h('span', { class: 'vie-t' }, s.phrase), h('span', { class: 'vie-age' }, t('vigie.age', { duree: depuis(s.depuis) })),
      s.exploration ? h('span', { class: 'vie-alerte', 'data-id': 'vie-exploration' }, ` — ${texteExploration(s)}`) : null);
  }
  return raison ? h('div', { class: 'vie', 'data-id': 'vie-attente' }, t('vigie.en_attente', { raison })) : null;
}

// Bandeau : une ligne par tour silencieux ou en exploration prolongée, avec ses gestes.
export function dessinerAlertes(zone, liste) {
  // Barre fine : le silence colore la pastille « En cours » et s'y lit ; le détail et les gestes sont dans son déroulant et la fiche.
  const pastille = document.getElementById('btn-travaux'), muet = liste?.find((a) => a.silencieux);
  if (pastille) {
    pastille.classList.toggle('silence', !!muet);
    let note = pastille.querySelector('.tr-silence');
    if (muet && !note) pastille.append(note = h('span', { class: 'tr-silence', 'data-id': 'pastille-silence' }));
    if (note) { note.hidden = !muet; if (muet) note.textContent = ` · ${texteSilence(muet).toLowerCase()}`; }
  }
  zone.hidden = !liste?.length;
  if (!liste?.length) return;
  remplacer(zone, liste.map((a) => h('div', { class: 'vie-ligne', 'data-id': a.tache },
    h('span', { class: 'maj-t' }, h('b', null, a.silencieux ? texteSilence(a) : t('vigie.exploration')), ' : ',
      h('a', { href: `#t=${enc(a.tache)}`, onclick: (e) => { e.preventDefault(); ouvrir(a.tache); } }, a.titre),
      ` — ${a.silencieux ? diagnostic(a) : texteExploration(a)}`),
    a.silencieux ? gestes(a.tache, a) : null)));
}
