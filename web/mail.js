// Rôle : page « Email » (#mail) — dossiers (Boîte de réception, Non lus, Suivis, Envoyés, Tous les messages, libellés), liste paginée,
//        recherche à la syntaxe Gmail, lecture d'un mail (en-têtes, corps, pièces jointes) et ses gestes : lu / non lu, archiver,
//        répondre, répondre à tous, transférer, créer une tâche ou rattacher à une tâche (mail-gestes.js).
// Frontières : parle à /api/mail seulement ; chargée au clic (app.js, INV-REACTIVITE-1). INV-MAIL-3 : le HTML d'un mail n'entre jamais
//        dans la page — il vit dans un <iframe sandbox> servi par le serveur sous CSP sans script ; le texte brut passe par textContent.
import { t } from './langues.js';
import { h, remplacer, heure } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { composer, versTache } from './mail-gestes.js';

const enc = encodeURIComponent;
const E = { vue: 'inbox', q: '', page: 0, uid: null, images: false, racine: null, jeton: 0 };
const NOMS = { inbox: 'mail.inbox', 'non-lus': 'mail.non_lus', suivis: 'mail.suivis', envoyes: 'mail.envoyes', tous: 'mail.tous' };
const zone = (id) => E.racine?.querySelector(`[data-id="${id}"]`);

export async function dessinerMail(racine) {
  E.racine = racine;
  let r;
  try { r = await api('/mail/reglages'); } catch (e) { erreur(e.message); return; }
  if (!r.adresse || !r.mdp) {
    remplacer(racine, h('section', { class: 'mail-page', 'data-id': 'mail' }, h('h2', null, t('mail.titre')),
      h('p', { class: 'note' }, t('mail.non_reglee')),
      h('button', { type: 'button', class: 'btn primaire', onclick: () => { location.hash = '#reglages/messagerie'; } }, t('mail.aller_reglages'))));
    return;
  }
  const champ = h('input', { type: 'search', class: 'mail-q', 'data-id': 'mail-q', value: E.q, placeholder: t('mail.rechercher'), 'aria-label': t('mail.rechercher') });
  champ.addEventListener('keydown', (e) => { if (e.key === 'Enter') { E.q = champ.value.trim(); E.page = 0; liste(); } });
  remplacer(racine, h('section', { class: 'mail-page', 'data-id': 'mail' },
    h('div', { class: 'mail-tete' }, h('h2', null, t('mail.titre')), h('span', { class: 'note' }, r.adresse), champ),
    h('div', { class: 'mail-grille' },
      h('nav', { class: 'mail-dossiers', 'data-id': 'mail-dossiers', 'aria-label': t('mail.dossiers') }),
      h('div', { class: 'mail-liste', 'data-id': 'mail-liste' }),
      h('article', { class: 'mail-lecture', 'data-id': 'mail-lecture' }))));
  dossiers();
  liste();
  if (E.uid) lire(E.uid);
}

async function dossiers() {
  let d;
  try { d = await api('/mail/dossiers'); } catch (e) { erreur(e.message); return; }
  const z = zone('mail-dossiers');
  if (!z) return;
  remplacer(z, d.map((x) => h('button', { type: 'button', class: `mail-dossier${x.id === E.vue ? ' sel' : ''}`, 'data-vue': x.id,
    'aria-pressed': String(x.id === E.vue), onclick: () => { E.vue = x.id; E.page = 0; E.uid = null; dessinerDossiers(z); liste(); lecture(null); } },
  x.genre === 'libelle' ? x.nom : t(NOMS[x.genre]))));
}
function dessinerDossiers(z) { for (const b of z.children) { b.classList.toggle('sel', b.dataset.vue === E.vue); b.setAttribute('aria-pressed', String(b.dataset.vue === E.vue)); } }

export async function liste() {
  const z = zone('mail-liste'), mien = ++E.jeton;
  if (!z) return;
  remplacer(z, h('p', { class: 'note' }, t('mail.chargement')));
  let r;
  try { r = await api(`/mail/messages?vue=${enc(E.vue)}&q=${enc(E.q)}&page=${E.page}`); } catch (e) { if (mien === E.jeton) remplacer(z, h('p', { class: 'note' }, e.message)); return; }
  if (mien !== E.jeton) return;
  const pages = Math.max(1, Math.ceil(r.total / r.par_page));
  remplacer(z, r.messages.length ? h('ul', { class: 'mail-lignes' }, r.messages.map(ligne)) : h('p', { class: 'note' }, t('mail.aucun')),
    h('div', { class: 'mail-pages' },
      h('button', { type: 'button', class: 'btn petit', disabled: E.page === 0 ? true : null, onclick: () => { E.page -= 1; liste(); } }, t('mail.precedent')),
      h('span', { class: 'note' }, t('mail.page', { page: E.page + 1, pages, total: r.total })),
      h('button', { type: 'button', class: 'btn petit', disabled: E.page + 1 >= pages ? true : null, onclick: () => { E.page += 1; liste(); } }, t('mail.suivant'))));
}

function ligne(m) {
  return h('li', null, h('button', { type: 'button', class: `mail-ligne${m.lu ? '' : ' non-lu'}${m.uid === E.uid ? ' sel' : ''}`, 'data-id': 'mail-ligne', 'data-uid': m.uid, onclick: () => lire(m.uid) },
    h('span', { class: 'mail-de' }, m.de), h('span', { class: 'mail-date' }, m.date ? heure(m.date) : ''),
    h('span', { class: 'mail-objet' }, m.piece ? '📎 ' : '', m.objet || t('mail.sans_objet')),
    h('span', { class: 'mail-extrait' }, m.extrait)));
}

async function lire(uid) {
  E.uid = uid; E.images = false;
  let m;
  try { m = await api(`/mail/message?vue=${enc(E.vue)}&uid=${uid}`); } catch (e) { erreur(e.message); return; }
  const b = zone('mail-liste')?.querySelector(`[data-uid="${uid}"]`);
  zone('mail-liste')?.querySelectorAll('.mail-ligne.sel').forEach((x) => x.classList.remove('sel'));
  b?.classList.add('sel'); b?.classList.remove('non-lu');
  lecture(m);
}

function cadre(m) {
  // INV-MAIL-3 : ni allow-scripts ni allow-same-origin ; les liens s'ouvrent dans un onglet hors du cadre.
  return h('iframe', { class: 'mail-cadre', 'data-id': 'mail-cadre', sandbox: 'allow-popups allow-popups-to-escape-sandbox', referrerpolicy: 'no-referrer', title: m.objet || t('mail.sans_objet'),
    src: `/api/mail/html?vue=${enc(E.vue)}&uid=${m.uid}${E.images ? '&images=1' : ''}` });
}

function lecture(m) {
  const z = zone('mail-lecture');
  if (!z) return;
  if (!m) { remplacer(z, h('p', { class: 'note' }, t('mail.choisir'))); return; }
  const geste = (cle, f, id) => h('button', { type: 'button', class: 'btn petit', 'data-id': id, onclick: f }, t(cle));
  const agir = (f) => async () => { try { await f(); } catch (e) { erreur(e.message); } };
  const archivable = E.vue === 'inbox' || E.vue === 'non-lus';
  const corps = m.html ? cadre(m) : h('pre', { class: 'mail-texte', 'data-id': 'mail-texte' }, m.texte);
  remplacer(z,
    h('h3', { 'data-id': 'mail-objet' }, m.objet || t('mail.sans_objet')),
    h('dl', { class: 'mail-entetes' }, h('dt', null, t('mail.de')), h('dd', null, m.de), h('dt', null, t('mail.a')), h('dd', null, m.a),
      m.cc ? [h('dt', null, t('mail.cc')), h('dd', null, m.cc)] : null, h('dt', null, t('mail.date')), h('dd', null, m.date ? heure(m.date) : '')),
    h('div', { class: 'mail-gestes' },
      geste('mail.repondre', () => composer('repondre', E.vue, m), 'mail-repondre'),
      geste('mail.repondre_tous', () => composer('repondre_tous', E.vue, m), 'mail-repondre-tous'),
      geste('mail.transferer', () => composer('transferer', E.vue, m), 'mail-transferer'),
      geste(m.lu ? 'mail.marquer_non_lu' : 'mail.marquer_lu', agir(async () => { await post('/mail/marquer', { vue: E.vue, uid: m.uid, lu: !m.lu }); m.lu = !m.lu; lecture(m); liste(); }), 'mail-lu'),
      archivable ? geste('mail.archiver', agir(async () => { await post('/mail/archiver', { vue: E.vue, uid: m.uid }); E.uid = null; lecture(null); liste(); }), 'mail-archiver') : null,
      geste('mail.creer_tache', () => versTache(E.vue, m, true), 'mail-creer-tache'),
      geste('mail.rattacher', () => versTache(E.vue, m, false), 'mail-rattacher')),
    m.html && !E.images ? h('button', { type: 'button', class: 'btn petit', 'data-id': 'mail-images', onclick: () => { E.images = true; lecture(m); } }, t('mail.afficher_images')) : null,
    corps,
    m.pieces.length ? h('ul', { class: 'mail-pieces', 'data-id': 'mail-pieces' }, m.pieces.map((p) => h('li', null,
      h('a', { href: `/api/mail/piece?vue=${enc(E.vue)}&uid=${m.uid}&n=${p.n}`, download: p.nom }, `📎 ${p.nom}`),
      h('span', { class: 'note' }, ' ', t('mail.ko', { n: Math.max(1, Math.round(p.taille / 1024)) }))))) : null);
}

