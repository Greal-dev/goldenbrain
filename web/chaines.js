// Rôle : chaînes de phases dans l'interface — liste et éditeur des modèles, lancement sur un dossier, bloc du détail
// (phases, état, validation humaine, reprise, ajustements de l'IA).
// Frontières : lit et écrit via /api/chaines ; l'enchaînement, la validation et les ajustements sont décidés par le
// serveur (INV-CHAINE-1, INV-CHAINE-3), rien n'est calculé ici ; la surveillance d'un dossier reste côté serveur (INV-CHAINE-4).
import { t, LOCALE } from './langues.js';
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { formulaire } from './dialogue.js';
import { chargerHarnais, listeHarnais } from './moteur.js';
import { emit, erreur, ouvrir } from './store.js';

const enc = encodeURIComponent;
const vide = () => ({ titre: '', consigne: '', entrees: '', livrable: '', harnais: '', modele: '', validation: false });
const ETATS_PHASE = ['a_venir', 'en_cours', 'faite', 'sautee', 'echec'];
const ETATS_CHAINE = ['en_cours', 'attente_validation', 'echec', 'terminee'];
const ACTIONS = ['sauter', 'ajouter', 'dedoubler', 'consigne'];

async function conteneursDe() {
  try { return await api('/conteneurs'); } catch (e) { erreur(e.message); return []; }
}
const optionsProjet = (cs) => [{ valeur: '', libelle: t('chaines.arrivee') }, ...cs.map((c) => ({ valeur: c.id, libelle: c.titre, groupe: c.casquette || '' }))];

// ---- Liste des modèles ----------------------------------------------------------------------------------------------

export async function ouvrirChaines() {
  let modeles;
  try { modeles = await api('/chaines'); } catch (e) { erreur(e.message); return; }
  const dlg = h('dialog', { class: 'dlg large chaines-dlg', 'aria-label': t('chaines.titre_dialogue') });
  let suite = null; // geste choisi : exécuté après la fermeture, jamais dans le dialogue lui-même
  const geste = (f) => () => { suite = f; dlg.close(); };
  const bt = (txt, f, cls = '') => h('button', { type: 'button', class: `btn petit ${cls}`, onclick: geste(f) }, txt);
  const ligne = (m) => h('li', { class: 'chaine-modele', 'data-modele': m.id },
    h('div', { class: 'cm-texte' }, h('strong', null, m.titre), ' ', h('span', { class: `cm-origine o-${m.origine}` }, t(`chaines.origine_${m.origine}`)),
      h('span', { class: 'cm-n' }, ' · ', t('chaines.n_phases', { n: m.phases.length })), m.resume ? h('p', { class: 'note' }, m.resume) : null),
    h('div', { class: 'cm-actions' },
      bt(t('chaines.lancer'), () => lancerChaine('', m.id), 'primaire'), bt(t('chaines.modifier'), () => editerModele(m)),
      m.origine === 'vault' ? bt(t('chaines.retirer'), () => retirerModele(m)) : null));
  dlg.append(h('div', { class: 'dlg-form' }, h('h3', null, t('chaines.titre_dialogue')), h('p', { class: 'dlg-texte' }, t('chaines.aide')),
    modeles.length ? h('ul', { class: 'chaines-liste' }, modeles.map(ligne)) : h('p', { class: 'note' }, t('chaines.aucune')),
    h('div', { class: 'dlg-actions' },
      h('button', { type: 'button', class: 'btn', 'data-refus': '', onclick: () => dlg.close() }, t('chaines.fermer')),
      h('button', { type: 'button', class: 'btn primaire', onclick: geste(() => editerModele(null)) }, t('chaines.nouvelle')))));
  dlg.addEventListener('close', () => { dlg.remove(); if (suite) suite(); });
  document.body.append(dlg);
  dlg.showModal();
}

async function retirerModele(m) {
  const v = await formulaire({ titre: t('chaines.retirer_titre'), texte: t('chaines.retirer_texte', { titre: m.titre }), valider: t('chaines.retirer'), focus: 'annuler' });
  if (v) { try { await post(`/chaines/${enc(m.id)}/retirer`); } catch (e) { erreur(e.message); } }
  ouvrirChaines();
}

// ---- Éditeur d'un modèle --------------------------------------------------------------------------------------------

function selecteurMoteur(p) {
  const liste = listeHarnais(), info = liste.find((x) => x.nom === p.harnais);
  const noms = liste.filter((x) => x.disponible || x.nom === p.harnais).map((x) => x.nom);
  if (p.harnais && !info) noms.push(p.harnais);
  const modeles = [...(info?.modeles || [])];
  if (p.modele && !modeles.includes(p.modele)) modeles.push(p.modele);
  const opt = (v, l, cur) => h('option', { value: v, selected: v === cur ? true : null }, l);
  const zone = h('span', { class: 'cp-moteur' });
  const dessiner = () => remplacer(zone,
    h('select', { 'aria-label': t('chaines.phase_assistant'), onchange: (e) => { p.harnais = e.target.value; p.modele = ''; remplacer(zone.parentNode, selecteurMoteur(p)); } },
      opt('', t('chaines.defaut'), p.harnais), noms.map((n) => opt(n, n, p.harnais))),
    h('select', { 'aria-label': t('chaines.phase_modele'), onchange: (e) => { p.modele = e.target.value; } },
      opt('', t('chaines.defaut'), p.modele), modeles.map((m) => opt(m, m, p.modele))));
  dessiner();
  return zone;
}

async function editerModele(m) {
  try { await chargerHarnais(); } catch { /* sans liste, les choix restent « par défaut » */ }
  const cs = await conteneursDe();
  const phases = (m?.phases || [vide()]).map((p) => ({ ...vide(), ...p }));
  const zone = h('div', { class: 'cp-phases' });
  const champ = (p, cle, label, long) => h('label', { class: 'cp-champ' }, label,
    h(long ? 'textarea' : 'input', { ...(long ? { rows: 4 } : { type: 'text', autocomplete: 'off' }), required: cle === 'titre' || cle === 'consigne' ? true : null,
      oninput: (e) => { p[cle] = e.target.value; } }, ...(long ? [p[cle]] : [])));
  function dessiner() {
    remplacer(zone, phases.map((p, i) => {
      const titre = champ(p, 'titre', t('chaines.phase_titre')), cible = titre.querySelector('input');
      cible.value = p.titre;
      const b = (txt, label, f, off) => h('button', { type: 'button', class: 'btn petit', 'aria-label': label, disabled: off ? true : null, onclick: f }, txt);
      const lignes = [champ(p, 'entrees', t('chaines.phase_entrees')), champ(p, 'livrable', t('chaines.phase_livrable'))];
      lignes.forEach((l, k) => { l.querySelector('input').value = p[k ? 'livrable' : 'entrees']; });
      return h('fieldset', { class: 'cp-phase', 'data-phase': i + 1 },
        h('legend', null, t('chaines.phase_n', { n: i + 1 })),
        titre, champ(p, 'consigne', t('chaines.phase_consigne'), true), ...lignes,
        h('div', { class: 'cp-ligne' }, h('span', { class: 'cp-champ' }, t('chaines.phase_assistant_modele')), ' ', h('span', { class: 'cp-m' }, selecteurMoteur(p))),
        h('label', { class: 'case' }, h('input', { type: 'checkbox', checked: p.validation ? true : null, onchange: (e) => { p.validation = e.target.checked; } }), ' ', t('chaines.phase_validation')),
        h('div', { class: 'cp-barre' },
          b('↑', t('chaines.monter_phase', { n: i + 1 }), () => { [phases[i - 1], phases[i]] = [phases[i], phases[i - 1]]; dessiner(); }, i === 0),
          b('↓', t('chaines.descendre_phase', { n: i + 1 }), () => { [phases[i + 1], phases[i]] = [phases[i], phases[i + 1]]; dessiner(); }, i === phases.length - 1),
          b('✕', t('chaines.supprimer_phase', { n: i + 1 }), () => { phases.splice(i, 1); dessiner(); }, phases.length === 1)));
    }));
  }
  dessiner();
  const corps = h('div', null, h('h4', null, t('chaines.phases')), zone,
    h('button', { type: 'button', class: 'btn petit', 'data-act': 'ajouter-phase', onclick: () => { phases.push(vide()); dessiner(); } }, t('chaines.ajouter_phase')));
  const v = await formulaire({
    titre: m ? t('chaines.editer_titre', { titre: m.titre }) : t('chaines.nouvelle'), valider: t('chaines.enregistrer'), large: true, corps,
    champs: [
      { nom: 'titre', label: t('chaines.champ_titre'), requis: true, valeur: m?.titre || '' },
      { nom: 'resume', label: t('chaines.champ_resume'), valeur: m?.resume || '' },
      { nom: 'contexte', label: t('chaines.champ_contexte'), type: 'textarea', valeur: m?.contexte || '' },
      { nom: 'surveiller', label: t('chaines.champ_surveiller'), aide: t('chaines.surveiller_aide'), valeur: m?.surveiller || '' },
      { nom: 'conteneur', label: t('chaines.champ_projet'), type: 'select', valeur: m?.conteneur || '', options: optionsProjet(cs) },
    ],
  });
  if (v) {
    try {
      await post('/chaines', { id: m?.origine === 'vault' ? m.id : '', titre: v.titre.trim(), resume: v.resume.trim(), contexte: v.contexte.trim(),
        surveiller: v.surveiller.trim(), conteneur: v.conteneur, phases: phases.map((p) => ({ ...p, titre: p.titre.trim(), consigne: p.consigne.trim() })) });
    } catch (e) { erreur(e.message); }
  }
  ouvrirChaines();
}

// ---- Lancement ------------------------------------------------------------------------------------------------------

export async function lancerChaine(conteneur = '', modele = '') {
  let modeles;
  try { modeles = await api('/chaines'); } catch (e) { erreur(e.message); return; }
  const cs = await conteneursDe();
  const v = await formulaire({
    titre: t('chaines.lancer_titre'), valider: t('chaines.lancer'), texte: t('chaines.lancer_texte'),
    champs: [
      { nom: 'modele', label: t('chaines.champ_modele'), type: 'select', valeur: modele || modeles[0]?.id, options: modeles.map((m) => ({ valeur: m.id, libelle: m.titre })) },
      { nom: 'conteneur', label: t('chaines.champ_projet'), type: 'select', valeur: conteneur, options: optionsProjet(cs) },
      { nom: 'dossier', label: t('chaines.champ_dossier'), aide: t('chaines.dossier_aide') },
      { nom: 'titre', label: t('chaines.champ_titre_lancement') },
    ],
  });
  if (!v) return;
  try {
    const r = await post('/chaines/lancer', { modele: v.modele, conteneur: v.conteneur || null, dossier: v.dossier.trim(), titre: v.titre.trim() });
    emit('recharger');
    ouvrir(r.id);
  } catch (e) { erreur(e.message); }
}

// ---- Bloc du détail -------------------------------------------------------------------------------------------------

const quand = (iso) => (iso ? new Date(iso).toLocaleString(LOCALE, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');

// `id` : tâche ouverte (parente ou phase) ; `apres` recharge la tâche et l'arbre. Rien ne s'affiche hors chaîne.
export function blocChaine(id, apres) {
  const el = h('section', { class: 'chaine-bloc', 'aria-label': t('chaines.bloc_aria') });
  const agir = async (f) => { try { await f(); } catch (e) { erreur(e.message); } apres(); };
  let minuterie = null;
  async function dessiner() {
    let x;
    try { x = await api(`/chaines/executions/${enc(id)}`); } catch { return; }
    if (!el.isConnected && minuterie) { clearInterval(minuterie); return; }
    const b = (txt, f, cls = '') => h('button', { type: 'button', class: `btn petit ${cls}`, onclick: () => agir(f) }, txt);
    remplacer(el,
      h('div', { class: 'ch-tete' }, h('strong', { class: `ch-etat e-${x.etat}` }, t(`chaines.etat_${ETATS_CHAINE.includes(x.etat) ? x.etat : 'en_cours'}`)),
        h('span', { class: 'note' }, ` ${x.titre}${x.dossier ? ` · ${t('chaines.dossier', { dossier: x.dossier })}` : ''}`),
        x.id !== id ? h('button', { type: 'button', class: 'btn petit', onclick: () => ouvrir(x.id) }, t('chaines.ouvrir_chaine')) : null),
      x.erreur ? h('p', { class: 'ch-erreur', role: 'alert' }, t('chaines.erreur', { erreur: x.erreur })) : null,
      h('ol', { class: 'ch-phases' }, x.phases.map((p) => h('li', { class: `ch-phase p-${p.etat}${p.tache === id ? ' ici' : ''}`, 'data-etat': p.etat },
        h('span', { class: 'ch-num' }, `${p.num}. `),
        p.tache && p.tache !== id ? h('a', { href: '#', class: 'ch-lien', onclick: (e) => { e.preventDefault(); ouvrir(p.tache); } }, p.titre) : p.titre, ' ',
        h('span', { class: 'ch-etat-phase' }, t(`chaines.phase_etat_${ETATS_PHASE.includes(p.etat) ? p.etat : 'a_venir'}`)),
        p.validation ? h('span', { class: 'note', title: t('chaines.validation_requise') }, ` · ${t('chaines.validation_court')}`) : null,
        p.livrable ? h('span', { class: 'note' }, ` · ${p.livrable}`) : null))),
      x.etat === 'attente_validation' || x.etat === 'echec' ? h('div', { class: 'ch-actions' },
        x.etat === 'attente_validation' ? b(t('chaines.poursuivre'), () => post(`/chaines/executions/${enc(x.id)}/poursuivre`), 'primaire') : null,
        x.etat === 'echec' ? b(t('chaines.reprendre'), () => post(`/chaines/executions/${enc(x.id)}/reprendre`), 'primaire') : null) : null,
      x.ajustements.length ? h('details', { class: 'ch-ajust', open: true }, h('summary', null, t('chaines.ajustements', { n: x.ajustements.length })),
        h('ul', null, x.ajustements.map((a) => h('li', null,
          t('chaines.ajustement', { quand: quand(a.a), action: ACTIONS.includes(a.action) ? t(`chaines.action_${a.action}`) : a.action, phase: a.phase, motif: a.motif }))))) : null);
    // L'enchaînement se fait sans geste : relire tant que la chaîne avance.
    if (x.etat === 'en_cours' && !minuterie) minuterie = setInterval(dessiner, 4000);
    if (x.etat !== 'en_cours' && minuterie) { clearInterval(minuterie); minuterie = null; }
  }
  dessiner();
  return el;
}
