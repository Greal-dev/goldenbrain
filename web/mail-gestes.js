// Rôle : gestes de la page « Email » qui ouvrent un dialogue — compositeur (répondre, répondre à tous, transférer ; l'envoi est le clic
//        « Envoyer »), « Créer une tâche » (instruction puis nouvelleTache(pre) du bandeau, titre = objet) et « Rattacher à une tâche ».
// Frontières : POST /api/mail/envoyer et /api/mail/tache ; la création passe par le dialogue « Nouvelle tâche » existant, dont le « Lancer »
//        est différé jusqu'à ce que le mail soit rangé (INV-MAIL-2 : le premier tour reçoit le mail comme donnée, avec l'instruction).
import { t } from './langues.js';
import { api, post } from './api.js';
import { S, parcourir, chemin, erreur, emit, ouvrir } from './store.js';
import { formulaire } from './dialogue.js';
import { nouvelleTache } from './bandeau.js';
import { filLisible } from './dom.js';

const enc = encodeURIComponent;
const INSTRUCTIONS = ['payer', 'investiguer', 'sauvegarder', 'etudier', 'repondre'];
const FERMES = new Set(['fait', 'cloture', 'abandonne']);
const TITRES = { repondre: 'mail.repondre', repondre_tous: 'mail.repondre_tous', transferer: 'mail.transferer' };

export async function composer(mode, vue, m) {
  let b;
  try { b = await api(`/mail/brouillon?mode=${mode}&vue=${enc(vue)}&uid=${m.uid}`); } catch (e) { erreur(e.message); return; }
  const v = await formulaire({
    titre: t(TITRES[mode]), valider: t('mail.envoyer'), large: true, texte: t('mail.envoi_aide'),
    champs: [
      { nom: 'a', label: t('mail.a'), requis: true, valeur: b.a },
      { nom: 'cc', label: t('mail.cc'), valeur: b.cc },
      { nom: 'objet', label: t('mail.objet'), valeur: b.objet },
      { nom: 'texte', label: t('mail.message'), type: 'textarea', lignes: 10 },
    ],
  });
  if (!v) return;
  try {
    await post('/mail/envoyer', { mode, vue, uid: m.uid, a: v.a, cc: v.cc, objet: v.objet, texte: v.texte });
    erreur(t('mail.envoye'), 'info');
  } catch (e) { erreur(e.message); }
}

const champsInstruction = () => [
  { nom: 'instruction', label: t('mail.instruction'), type: 'select', valeur: 'payer',
    options: [...INSTRUCTIONS.map((x) => ({ valeur: x, libelle: t(`mail.instr_${x}`) })), { valeur: '', libelle: t('mail.instr_libre') }] },
  { nom: 'libre', label: t('mail.instr_texte'), type: 'textarea', lignes: 2, aide: t('mail.instr_texte_aide') },
];
const libelle = (v) => [v.instruction ? t(`mail.instr_${v.instruction}`) : '', v.libre.trim()].filter(Boolean).join(' : ');

function tachesOuvertes() {
  const r = [];
  for (const n of parcourir(S.arbre || [])) {
    if (n.type !== 'tache' || FERMES.has(n.statut)) continue;
    r.push({ valeur: n.id, libelle: n.titre, groupe: filLisible(chemin(S.arbre, (x) => x === n).slice(0, -1).map((x) => x.titre)).join(' › ') });
  }
  return r;
}

export async function versTache(vue, m, creer) {
  const options = creer ? [] : tachesOuvertes();
  const v = await formulaire({
    titre: t(creer ? 'mail.creer_tache' : 'mail.rattacher'), valider: t(creer ? 'mail.suivant_etape' : 'mail.rattacher'), texte: t('mail.tache_aide'),
    champs: [...(creer ? [] : [{ nom: 'tache', label: t('mail.tache'), type: 'select', valeur: S.selection, options }]), ...champsInstruction()],
  });
  if (!v) return;
  if (!v.instruction && !v.libre.trim()) { erreur(t('mail.instr_requise')); return; }
  let cible = { id: v.tache, lancer: false };
  if (creer) {
    cible = await nouvelleTache({ titre: m.objet || t('mail.sans_objet'), description: t('mail.description', { instruction: libelle(v), de: m.de }), differer: true });
    if (!cible) return;
  }
  try {
    await post('/mail/tache', { vue, uid: m.uid, tache: cible.id, instruction: v.instruction, libre: v.libre, lancer: !!cible.lancer });
    emit('recharger');
    if (creer) ouvrir(cible.id); else erreur(t('mail.rattache'), 'info');
  } catch (e) { erreur(e.message); }
}
