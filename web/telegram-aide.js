// Rôle : étapes de l'assistant Telegram et texte du panneau d'aide (quoi, pourquoi, si ça bloque), une entrée par étape.
// Frontières : texte seul, aucune logique ; c'est le repli de la section Telegram du guide (docs/GUIDE.md, quand elle existe).
import { t } from './langues.js';

export const ETAPES = [
  { id: 'botfather', titre: t('telegram_aide.etape_botfather') },
  { id: 'jeton', titre: t('telegram_aide.etape_jeton') },
  { id: 'nom', titre: t('telegram_aide.etape_nom') },
  { id: 'discussion', titre: t('telegram_aide.etape_discussion') },
  { id: 'webhook', titre: t('telegram_aide.etape_webhook') },
  { id: 'test', titre: t('telegram_aide.etape_test') },
];

export const AIDE = {
  botfather: {
    quoi: t('telegram_aide.botfather_quoi'),
    pourquoi: t('telegram_aide.botfather_pourquoi'),
    bloque: t('telegram_aide.botfather_bloque'),
  },
  jeton: {
    quoi: t('telegram_aide.jeton_quoi'),
    pourquoi: t('telegram_aide.jeton_pourquoi'),
    bloque: t('telegram_aide.jeton_bloque'),
  },
  nom: {
    quoi: t('telegram_aide.nom_quoi'),
    pourquoi: t('telegram_aide.nom_pourquoi'),
    bloque: t('telegram_aide.nom_bloque'),
  },
  discussion: {
    quoi: t('telegram_aide.discussion_quoi'),
    pourquoi: t('telegram_aide.discussion_pourquoi'),
    bloque: t('telegram_aide.discussion_bloque'),
  },
  webhook: {
    quoi: t('telegram_aide.webhook_quoi'),
    pourquoi: t('telegram_aide.webhook_pourquoi'),
    bloque: t('telegram_aide.webhook_bloque'),
  },
  test: {
    quoi: t('telegram_aide.test_quoi'),
    pourquoi: t('telegram_aide.test_pourquoi'),
    bloque: t('telegram_aide.test_bloque'),
  },
};
