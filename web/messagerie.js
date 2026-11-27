// Rôle : section « Messagerie » des Réglages — adresse Gmail, saisie du mot de passe d'application dans un terminal du poste
//        (commande exacte montrée puis lancée, comme le jeton Telegram), essai de connexion, état lisible, lien d'aide Google.
// Frontières : parle à /api/mail/reglages, /api/mail/mdp/terminal et /api/mail/tester ; le mot de passe ne passe jamais par le
//        navigateur et n'en revient jamais (INV-MAIL-1) : seule sa présence (et sa source) est montrée. Chargée avec la section.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

const SOURCES = { variable: 'messagerie.source_variable', fichier: 'messagerie.source_fichier' };

export function sectionMessagerie() {
  const el = h('section', { class: 'rg-messagerie', 'data-id': 'messagerie' });
  const E = { r: null, essai: null, terminal: '', attente: 0 };
  const attraper = (f) => async () => { try { await f(); } catch (x) { erreur(x.message); } };
  const lire = (id) => el.querySelector(`[data-id="${id}"]`);

  const enregistrer = attraper(async () => { E.r = await api('/mail/reglages', { methode: 'PUT', corps: { adresse: lire('mg-adresse').value.trim() } }); E.essai = null; dessiner(); });
  const essayer = attraper(async () => { E.essai = await post('/mail/tester', {}); dessiner(); });
  const terminal = attraper(async () => {
    const cmd = E.r.commande_mdp;
    if (!confirm(t('messagerie.confirmer_terminal', { cmd }))) return;
    const r = await post('/mail/mdp/terminal', { accord: cmd });
    E.terminal = r.ok ? t('messagerie.terminal_ouvert') : t('messagerie.terminal_echec', { motif: r.motif, cmd });
    clearInterval(E.attente);
    // Le terminal enregistre hors de la page : on guette la présence du mot de passe, puis on essaie.
    E.attente = setInterval(async () => {
      if (!el.isConnected) { clearInterval(E.attente); return; }
      try { const x = await api('/mail/reglages'); if (x.mdp) { clearInterval(E.attente); E.r = x; E.terminal = ''; await essayer(); } } catch { /* serveur en redémarrage : on réessaie */ }
    }, 2000);
    dessiner();
  });

  function etat() {
    if (!E.r.adresse) return t('messagerie.etat_adresse');
    if (!E.r.mdp) return t('messagerie.etat_mdp');
    if (!E.essai) return t('messagerie.etat_pret', { source: t(SOURCES[E.r.source] || 'messagerie.source_fichier') });
    return E.essai.ok ? t('messagerie.etat_connecte', { adresse: E.r.adresse }) : t('messagerie.etat_erreur', { motif: E.essai.motif });
  }

  function dessiner() {
    if (!E.r) return;
    remplacer(el,
      h('p', { class: 'note' }, t('messagerie.intro'), ' ', h('a', { href: E.r.aide, target: '_blank', rel: 'noopener noreferrer' }, t('messagerie.aide_google'))),
      h('div', { class: 'champ' }, h('label', { for: 'mg-adresse' }, t('messagerie.adresse')),
        h('input', { id: 'mg-adresse', 'data-id': 'mg-adresse', type: 'email', value: E.r.adresse, autocomplete: 'off', placeholder: t('messagerie.adresse_aide') }),
        h('button', { type: 'button', class: 'btn', 'data-id': 'mg-enregistrer', onclick: enregistrer }, t('messagerie.enregistrer'))),
      h('div', { class: 'dlg-actions' },
        h('button', { type: 'button', class: 'btn', 'data-id': 'mg-terminal', disabled: E.r.adresse ? null : true, onclick: terminal }, t('messagerie.saisir_mdp')),
        h('button', { type: 'button', class: 'btn', 'data-id': 'mg-tester', disabled: E.r.adresse && E.r.mdp ? null : true, onclick: essayer }, t('messagerie.tester'))),
      E.terminal ? h('p', { class: 'note' }, E.terminal) : null,
      h('p', { class: `note${E.essai && !E.essai.ok ? ' erreur' : ''}`, 'data-id': 'mg-etat', role: 'status' }, etat()));
  }

  attraper(async () => { E.r = await api('/mail/reglages'); dessiner(); })();
  return el;
}
