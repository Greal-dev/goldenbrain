// Rôle : causes des échecs et arrêts (INV-INCIDENT-1) — panneau « Incidents » du bandeau (jauge par compte, liste
// datée : moteur, cause lisible, action de GoldenBrain, geste proposé) et bandeau de la conversation d'une tâche.
// Frontières : lit GET /api/incidents et GET /api/economie ; aucun geste automatique.
import { h, $, heure, remplacer } from './dom.js';
import { on, ouvrir, erreur } from './store.js';
import { api } from './api.js';
import { t, LOCALE } from './langues.js';
import { deroulant } from './deroulant.js';

const enc = encodeURIComponent;
const quand = (iso) => { const d = new Date(iso); return `${d.toLocaleDateString(LOCALE)} ${heure(iso)}`; };

// Bandeau de la conversation : dernier incident encore ouvert de la tâche (levé au prochain tour abouti).
export function bandeauIncident(inc) {
  if (!inc) return null;
  return h('div', { class: 'incident', role: 'status', 'data-id': 'incident', title: inc.motif },
    h('b', null, inc.libelle), ' ' + (inc.role && inc.role !== 'tache' ? t('incidents.suite_role', { assistant: inc.harnais, role: inc.role, date: quand(inc.date) }) : t('incidents.suite', { assistant: inc.harnais, date: quand(inc.date) })),
    h('div', null, t('incidents.action', { action: inc.action })), h('div', { class: 'note' }, t('incidents.geste_propose', { geste: inc.geste })));
}

// Jauge par compte : épuisé jusqu'à l'heure de reprise, sinon la fenêtre la plus entamée.
function jauge(eco, epuises) {
  const comptes = Object.keys(eco.quotas || {});
  return h('ul', { class: 'inc-jauge', 'data-id': 'inc-jauge' }, comptes.map((c) => {
    if (epuises[c]) return h('li', { class: 'epuise' }, h('b', null, c), ' ' + t('incidents.epuise', { date: quand(epuises[c]) }));
    const f = (eco.quotas[c] || []).reduce((a, x) => (!a || x.part > a.part ? x : a), null);
    if (!f) return h('li', null, h('b', null, c), ' ' + t('incidents.disponible'));
    return h('li', null, h('b', null, c), ' : ', h('meter', { min: 0, max: 1, value: f.part, high: 0.8 }),
      ' ' + t('incidents.utilise', { part: Math.round(f.part * 100), date: new Date(f.renouvellement * 1000).toLocaleString(LOCALE) }));
  }));
}

let der = null;
async function dessinerPanneau(corps) {
  try {
    const [d, eco] = await Promise.all([api('/incidents?limite=50'), api('/economie')]);
    if (!der.ouvert()) return;
    remplacer(corps, h('h4', null, t('incidents.comptes')), jauge(eco, d.epuises || {}),
      h('h4', null, t('incidents.derniers')),
      d.incidents.length ? h('ul', { class: 'inc-liste', 'data-id': 'inc-liste' }, d.incidents.map((i) => h('li', { class: i.clos ? 'clos' : '', title: i.motif },
        h('span', { class: 'note' }, (i.role !== 'tache' ? t('incidents.ligne_role', { date: quand(i.date), assistant: i.harnais, role: i.role }) : t('incidents.ligne', { date: quand(i.date), assistant: i.harnais }))),
        h('a', { href: `#t=${enc(i.tache)}`, onclick: (e) => { e.preventDefault(); ouvrir(i.tache); } }, i.titre),
        h('div', null, h('b', null, i.libelle), ' — ' + t('incidents.action', { action: i.action })),
        h('div', { class: 'note' }, t('incidents.geste', { geste: i.geste })))))
        : h('p', { class: 'note' }, t('incidents.aucun')));
  } catch (e) { erreur(e.message); }
}

async function compter() {
  try {
    const d = await api('/incidents?limite=50');
    const n = d.incidents.filter((i) => !i.clos).length + Object.keys(d.epuises || {}).length;
    $('#n-incidents').textContent = String(n);
    $('#btn-incidents').classList.toggle('alerte', n > 0);
  } catch { /* le compteur attendra le prochain incident */ }
}

export function initIncidents() {
  der = deroulant({ bouton: $('#btn-incidents'), panneau: $('#panneau-incidents'), titre: t('index.incidents'), remplir: dessinerPanneau }); // INV-DEROULANT-1
  on('incident', () => { compter(); der.redessiner(); });
  compter();
}
