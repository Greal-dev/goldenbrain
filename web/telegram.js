// Rôle : section « Telegram » de la page Réglages — assistant pas à pas (une étape visible à la fois, état coché, guide à côté)
// pour créer le bot, saisir le jeton, confirmer son nom, se faire reconnaître, lever un ancien webhook et essayer la connexion ;
// réglages avancés (discussions, réception, projet de tri) repliés dessous.
// Frontières : parle à /api/telegram seulement ; le jeton part au serveur, qui le range dans le coffre du poste : jamais relu ni affiché
// (INV-TELEGRAM-2). Saisie de préférence dans un terminal (commande exacte montrée puis lancée, INV-INSTALL-1) ; le champ du navigateur est le repli.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur, emit } from './store.js';
import { ETAPES, AIDE } from './telegram-aide.js';
import { t } from './langues.js';
import { garnir } from './garnir.js';

const SOURCES = { variable: t('telegram.source_variable'), fichier: t('telegram.source_fichier'), '': t('telegram.source_aucune') };
const COMMANDES_BOTFATHER = ['/newbot', '/mybots'];

// État de l'assistant hors de la section : la page Réglages se redessine à chaque événement du serveur et
// recrée la section ; un état local repartait de zéro et redemandait le nom du bot (retour d'essai, 18/11).
const ETAT = { t: null, el: null, dessiner: () => {}, bot: null, nomEnCours: false, vuBotfather: false, bonBot: false,
  terminal: '', attente: null, essai: null, termine: false };

export function sectionTelegram() {
  const el = h('section', { class: 'rg-telegram', 'data-id': 'telegram' }, h('h3', null, 'Telegram'));
  // État propre à l'assistant ; le serveur ne garde que le jeton, les discussions et l'activation.
  const e = ETAT;
  e.el = el;

  const lire = (id) => el.querySelector(`[data-id="${id}"]`);
  const rafraichir = async () => { e.t = await api('/telegram'); ETAT.dessiner(); };
  const attraper = (f) => async (...a) => { try { await f(...a); } catch (x) { erreur(x.message); } };

  // --- actions ---------------------------------------------------------------------------------------------------
  const reconnaitre = attraper(async () => { e.bot = await post('/telegram/reconnaitre', {}); e.nomEnCours = false; ETAT.dessiner(); });
  const ouvrirTerminal = attraper(async () => {
    const cmd = e.t.commande_jeton;
    if (!confirm(t('telegram.confirmer_terminal', { cmd }))) return;
    const r = await post('/telegram/jeton/terminal', { accord: cmd });
    e.terminal = r.ok ? t('telegram.terminal_ouvert') : t('telegram.terminal_echec', { motif: r.motif, cmd });
    suivre();
    ETAT.dessiner();
  });
  const saisirNavigateur = attraper(async () => {
    const jeton = lire('tg-jeton').value.trim();
    if (!jeton) return;
    e.t = await api('/telegram', { methode: 'PUT', corps: { jeton } });
    e.bot = null; e.bonBot = false;
    ETAT.dessiner();
  });
  const autoriser = attraper(async () => {
    const ids = [...el.querySelectorAll('[data-id^="tg-trouvee-"]:checked')].map((c) => c.value);
    if (!ids.length) return;
    e.t = await api('/telegram', { methode: 'PUT', corps: { discussions: [...new Set([...e.t.discussions, ...ids])] } });
    ETAT.dessiner();
  });
  const levierWebhook = attraper(async () => {
    const r = await post('/telegram/webhook/desactiver', {});
    if (!r.ok) return erreur(r.motif);
    await reconnaitre();
  });
  const essayer = attraper(async () => { e.essai = await post('/telegram/tester', {}); ETAT.dessiner(); });
  const terminer = attraper(async () => {
    e.t = await api('/telegram', { methode: 'PUT', corps: { actif: true } });
    e.termine = true;
    ETAT.dessiner();
  });
  const recommencer = () => { Object.assign(e, { bot: null, bonBot: false, vuBotfather: false, essai: null, termine: false, terminal: '' }); ETAT.dessiner(); };

  // Le terminal enregistre le jeton hors de la page : on guette l'enregistrement pour passer à l'étape suivante.
  const suivre = () => {
    clearInterval(e.attente);
    e.attente = setInterval(async () => {
      try {
        const etat = await api('/telegram');
        if (etat.jeton) { clearInterval(e.attente); e.t = etat; e.bot = null; e.bonBot = false; e.terminal = ''; ETAT.dessiner(); }
      } catch { /* le serveur redémarre peut-être : on réessaie */ }
    }, 2000);
  };

  // --- étapes ----------------------------------------------------------------------------------------------------
  const fait = {
    botfather: () => e.vuBotfather || !!e.t.jeton,
    jeton: () => !!e.t.jeton,
    nom: () => e.bonBot,
    discussion: () => e.t.discussions.length > 0,
    webhook: () => !e.bot?.webhook,
    test: () => e.termine || (e.t.actif && e.t.en_marche && e.t.discussions.length > 0),
  };
  const courante = () => {
    if (e.t.jeton && e.bonBot && e.bot?.webhook) return 'webhook'; // un webhook actif empêche toute lecture : à lever avant de chercher la discussion
    return ETAPES.find((s) => s.id !== 'webhook' && !fait[s.id]())?.id ?? null;
  };

  const bouton = (id, lib, f, attrs = {}) => h('button', { class: 'btn', type: 'button', 'data-id': id, onclick: f, ...attrs }, lib);
  const copiable = (texte) => h('code', { class: 'tg-copie' }, texte);

  const corps = {
    botfather: () => [
      h('p', null, garnir(t('telegram.ouvrir_botfather'), { lien: h('a', { href: 'https://t.me/BotFather', target: '_blank', rel: 'noopener noreferrer' }, 't.me/BotFather') })),
      h('ul', null, h('li', null, garnir(t('telegram.newbot'), { cmd: copiable(COMMANDES_BOTFATHER[0]) })),
        h('li', null, garnir(t('telegram.mybots'), { cmd: copiable(COMMANDES_BOTFATHER[1]) }))),
      h('p', null, t('telegram.garder_cle')),
      bouton('tg-botfather-ok', t('telegram.bot_ok'), () => { e.vuBotfather = true; ETAT.dessiner(); })],
    jeton: () => [
      h('p', null, t('telegram.saisie_recommandee')),
      h('p', { class: 'note', 'data-id': 'tg-commande' }, garnir(t('telegram.va_etre_fait'), { cmd: copiable(e.t.commande_jeton) })),
      bouton('tg-terminal', t('telegram.saisir_terminal'), ouvrirTerminal),
      e.terminal ? h('pre', { class: 'note', 'data-id': 'tg-terminal-etat', 'aria-live': 'polite' }, e.terminal) : null,
      h('details', { 'data-id': 'tg-repli' }, h('summary', null, t('telegram.repli')),
        h('label', { class: 'tg-champ' }, h('span', null, t('telegram.cle_bot', { source: SOURCES[e.t.jeton] ?? e.t.jeton })),
          h('input', { 'data-id': 'tg-jeton', type: 'password', autocomplete: 'off', placeholder: t('telegram.coller_cle') })),
        bouton('tg-jeton-ok', t('telegram.enregistrer_cle'), saisirNavigateur))],
    nom: () => {
      if (!e.bot && !e.nomEnCours) { e.nomEnCours = true; reconnaitre(); }
      if (!e.bot) return [h('p', null, t('telegram.lecture_nom'))];
      if (!e.bot.ok) return [h('p', { class: 'note', 'data-id': 'tg-nom-erreur' }, t('telegram.lecture_impossible', { motif: e.bot.motif })), bouton('tg-reessayer', t('telegram.reessayer'), () => { e.bot = null; ETAT.dessiner(); })];
      return [h('p', null, garnir(t('telegram.cle_commande'), { nom: h('b', { 'data-id': 'tg-nom' }, e.bot.bot) })),
        bouton('tg-bon-bot', t('telegram.bon_bot'), () => { e.bonBot = true; ETAT.dessiner(); })];
    },
    discussion: () => {
      const trouvees = (e.bot?.discussions ?? []).map((d) => h('label', { class: 'case' },
        h('input', { type: 'checkbox', 'data-id': `tg-trouvee-${d.id}`, value: d.id, checked: e.t.discussions.includes(d.id) ? true : null }), `${d.nom} (${d.id})`));
      return [h('p', null, t('telegram.envoyer_message', { bot: e.bot?.bot ?? t('telegram.votre_bot') })),
        bouton('tg-reconnaitre', t('telegram.reconnaitre'), reconnaitre),
        e.bot && !e.bot.ok ? h('p', { class: 'note' }, e.bot.motif) : null,
        trouvees.length ? h('div', { 'data-id': 'tg-trouvees' }, h('p', null, t('telegram.trouvees')), ...trouvees,
          bouton('tg-autoriser', t('telegram.autoriser'), autoriser))
          : (e.bot?.ok ? h('p', { class: 'note', 'data-id': 'tg-aucune' }, t('telegram.aucune_discussion')) : null)];
    },
    webhook: () => [h('p', { 'data-id': 'tg-webhook' }, t('telegram.webhook_actif')),
      bouton('tg-webhook-off', t('telegram.webhook_off'), levierWebhook)],
    test: () => {
      const r = e.essai;
      return [h('p', null, t('telegram.bienvenue_va')),
        bouton('tg-essai', t('telegram.envoyer_test'), essayer),
        r && !r.ok ? h('p', { class: 'note', 'data-id': 'tg-essai-erreur' }, t('telegram.echec', { motif: r.motif })) : null,
        r?.ok && r.bienvenue ? h('div', null, h('p', { 'data-id': 'tg-essai-ok' }, t('telegram.message_envoye', { bot: r.bot })),
          bouton('tg-terminer', t('telegram.terminer'), terminer)) : null];
    },
  };

  // --- réglages avancés ------------------------------------------------------------------------------------------
  const champ = (id, lib, valeur) => h('label', { class: 'tg-champ' }, h('span', null, lib), h('input', { 'data-id': id, value: valeur ?? '' }));
  const avance = () => {
    const resultat = h('p', { class: 'note', 'data-id': 'tg-resultat', 'aria-live': 'polite' },
      e.t.erreur ? t('telegram.derniere_erreur', { motif: e.t.erreur }) : (e.t.en_marche ? t('telegram.ecoute') : t('telegram.arretee')));
    const enregistrer = attraper(async () => {
      e.t = await api('/telegram', { methode: 'PUT', corps: {
        actif: lire('tg-actif').checked,
        discussions: lire('tg-discussions').value.split(/[\s,;]+/).filter(Boolean),
        reception: lire('tg-reception').value.trim(),
        conteneur: lire('tg-conteneur').value.trim(),
      } });
      ETAT.dessiner();
    });
    const tester = attraper(async () => {
      const r = await post('/telegram/tester', {});
      resultat.textContent = r.ok
        ? (r.en_marche ? (r.bienvenue ? t('telegram.connexion_ok_marche_bienvenue', { bot: r.bot }) : t('telegram.connexion_ok_marche_sans', { bot: r.bot }))
          : (r.bienvenue ? t('telegram.connexion_ok_arret_bienvenue', { bot: r.bot }) : t('telegram.connexion_ok_arret_sans', { bot: r.bot })))
        : t('telegram.echec', { motif: r.motif });
    });
    return h('details', { 'data-id': 'tg-avance', class: 'tg-avance' }, h('summary', null, t('telegram.avance')),
      h('label', { class: 'case' }, h('input', { type: 'checkbox', 'data-id': 'tg-actif', checked: e.t.actif ? true : null }), h('b', null, t('telegram.activer'))),
      champ('tg-discussions', t('telegram.ids_discussions'), e.t.discussions.join(', ')),
      champ('tg-reception', t('telegram.dossier_reception'), e.t.reception),
      champ('tg-conteneur', t('telegram.projet_tri'), e.t.conteneur),
      h('div', { class: 'rg-mode' }, bouton('tg-enregistrer', t('telegram.enregistrer'), enregistrer), bouton('tg-tester', t('telegram.tester'), tester)),
      resultat,
      h('p', { class: 'note' }, (e.t.transcription ? t('telegram.envois_transcrit', { n: e.t.envois }) : t('telegram.envois_sans', { n: e.t.envois }))));
  };

  // --- dessin ----------------------------------------------------------------------------------------------------
  ETAT.dessiner = () => { if (ETAT.el === el) dessiner(); };
  function dessiner() {
    const ouvert = lire('tg-avance')?.open;
    // INV-REGLAGES-1 : une saisie en cours survit au redessin (réponse de GET /telegram arrivée après la frappe).
    const saisies = [...el.querySelectorAll('.tg-avance input:not([type=checkbox])')].filter((x) => x.value !== x.defaultValue).map((x) => [x.dataset.id, x.value]);
    const cur = courante();
    emit('resume', ['telegram', cur ? t('telegram.a_configurer') : (e.bot?.bot ? t('telegram.connecte_a', { bot: e.bot.bot }) : t('telegram.connecte'))]);
    const aide = AIDE[cur ?? 'test'];
    const liste = h('ol', { class: 'tg-etapes' }, ETAPES.map((s, i) => {
      const ok = s.id === 'webhook' ? (fait.webhook() && !!e.bot) : fait[s.id]();
      return h('li', { 'data-id': `tg-etape-${s.id}`, class: `${ok ? 'fait' : ''}${s.id === cur ? ' courante' : ''}`, 'aria-current': s.id === cur ? 'step' : null },
        h('span', { class: 'tg-num' }, ok ? '✓' : String(i + 1)), ' ', s.titre, s.id === 'webhook' && !e.bot?.webhook && ok ? ' ' + t('telegram.aucun') : '');
    }));
    const principal = cur
      ? h('div', { class: 'tg-corps', 'data-id': 'tg-corps', 'data-etape': cur }, h('h4', null, ETAPES.find((s) => s.id === cur).titre), ...corps[cur]())
      : h('div', { class: 'tg-corps', 'data-id': 'tg-corps', 'data-etape': 'fini' }, h('h4', { 'data-id': 'tg-fini' }, t('telegram.est_connecte')),
        h('p', null, (e.t.en_marche ? t('telegram.fini_ecoute', { bot: e.bot?.bot ?? '', n: e.t.discussions.length }) : t('telegram.fini_arrete', { bot: e.bot?.bot ?? '', n: e.t.discussions.length }))),
        bouton('tg-recommencer', t('telegram.refaire'), recommencer));
    remplacer(el,
      h('h3', null, 'Telegram'),
      h('p', { class: 'note' }, t('telegram.intro')),
      h('div', { class: 'tg-assistant' }, h('div', { class: 'tg-colonne' }, liste, principal),
        h('aside', { class: 'tg-aide', 'data-id': 'tg-aide' }, h('h4', null, t('telegram.a_savoir')),
          h('p', null, h('b', null, t('telegram.quoi')), aide.quoi), h('p', null, h('b', null, t('telegram.pourquoi')), aide.pourquoi), h('p', null, h('b', null, t('telegram.si_bloque')), aide.bloque))),
      avance());
    if (ouvert) lire('tg-avance').open = true;
    for (const [id, v] of saisies) { const x = lire(id); if (x) x.value = v; }
  }

  if (e.t) dessiner();  // section recréée : on redessine aussitôt l'état connu, sans clignoter
  api('/telegram').then((etat) => { e.t = etat; ETAT.dessiner(); })
    .catch((x) => remplacer(el, h('h3', null, 'Telegram'), h('p', { class: 'note' }, x.message)));
  return el;
}
