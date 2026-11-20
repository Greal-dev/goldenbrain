// Rôle : page « Équipe » du volet droit — personas : liste, création, édition, désactivation, retrait.
// Frontières : API /equipe seule ; un persona est un regard (mandat + focus), jamais un agent à droits propres.
import { h, remplacer } from './dom.js';
import { api } from './api.js';
import { erreur } from './store.js';
import { formulaire } from './dialogue.js';
import { chargerHarnais, listeHarnais, libelleMoteur } from './moteur.js';
import { boutonAide } from './guide.js';
import { t, tn } from './langues.js';
import { garnir } from './garnir.js';

const enc = encodeURIComponent;
const DECL = { toujours: t('equipe.decl_toujours'), filtre: t('equipe.decl_filtre'), 'a-la-demande': t('equipe.decl_demande') };
const csv = (a) => (a || []).join(', ');
const liste = (s) => String(s || '').split(',').map((x) => x.trim()).filter(Boolean);
let racine = null;

function resume(p) {
  if (p.declenchement === 'a-la-demande') return t('equipe.resume_demande');
  if (p.declenchement === 'toujours') return t('equipe.resume_toujours');
  const parts = [];
  if ((p.casquettes || []).length) parts.push(t('equipe.resume_casquettes', { liste: csv(p.casquettes) }));
  if ((p.conteneurs || []).length) parts.push(tn('equipe.resume_conteneurs', p.conteneurs.length));
  if ((p.mots || []).length) parts.push(t('equipe.resume_mots', { liste: csv(p.mots) }));
  return parts.join(' · ') || t('equipe.resume_aucun');
}

async function enregistrer(p) {
  const { id, ...corps } = p;
  try { await api(`/equipe/${enc(id)}`, { methode: 'PUT', corps }); return true; } catch (e) { erreur(e.message); return false; }
}

async function editer(p) {
  const neuf = !p;
  const moteurs = listeHarnais();
  const optsH = [{ valeur: '', libelle: t('equipe.par_defaut') }, ...moteurs.map((x) => ({ valeur: x.nom, libelle: x.disponible ? x.nom : t('equipe.indisponible_parens', { nom: x.nom }) }))];
  if (p?.harnais && !moteurs.some((x) => x.nom === p.harnais)) optsH.push({ valeur: p.harnais, libelle: p.harnais });
  const v = await formulaire({
    titre: neuf ? t('equipe.nouvel_expert') : t('equipe.modifier_titre', { nom: p.nom || p.id }), valider: neuf ? t('equipe.creer') : t('equipe.enregistrer'), large: true,
    champs: [
      { nom: 'id', label: t('equipe.identifiant'), requis: true, valeur: p?.id, lecture: !neuf, motif: '[a-z0-9\\-]+', aide: t('equipe.identifiant_aide') },
      { nom: 'nom', label: t('equipe.nom'), requis: true, valeur: p?.nom, aide: t('equipe.nom_aide') },
      { nom: 'declenchement', label: t('equipe.declenchement'), type: 'select', valeur: p?.declenchement || 'filtre', options: Object.entries(DECL).map(([valeur, libelle]) => ({ valeur, libelle })) },
      { nom: 'actif', label: t('equipe.actif'), type: 'checkbox', valeur: p ? p.actif : true },
      { nom: 'casquettes', label: t('equipe.casquettes_filtre'), valeur: csv(p?.casquettes), aide: 'C1, META' },
      { nom: 'mots', label: t('equipe.mots_filtre'), valeur: csv(p?.mots), aide: t('equipe.mots_aide') },
      { nom: 'conteneurs', label: t('equipe.conteneurs_filtre'), valeur: csv(p?.conteneurs), aide: 'Projets/C1-ORION-V2' },
      { nom: 'harnais', label: t('equipe.assistant'), type: 'select', valeur: p?.harnais || '', options: optsH },
      { nom: 'modele', label: t('equipe.modele'), valeur: p?.modele },
      { nom: 'mandat', label: t('equipe.mandat'), type: 'textarea', lignes: 7, valeur: p?.mandat },
      { nom: 'focus', label: t('equipe.focus'), type: 'textarea', lignes: 4, valeur: p?.focus },
    ],
  });
  if (!v) return;
  const ok = await enregistrer({ id: v.id.trim(), nom: v.nom.trim(), actif: v.actif, declenchement: v.declenchement, casquettes: liste(v.casquettes),
    conteneurs: liste(v.conteneurs), mots: liste(v.mots), harnais: v.harnais, modele: v.modele.trim(), mandat: v.mandat, focus: v.focus });
  if (ok) await dessinerEquipe(racine);
}
async function basculerActif(p) { if (await enregistrer({ ...p, actif: !p.actif })) await dessinerEquipe(racine); }
async function retirer(p) {
  const v = await formulaire({ titre: t('equipe.retirer_titre'), valider: t('equipe.retirer'),
    texte: t('equipe.retirer_texte', { nom: p.nom || p.id }) });
  if (!v) return;
  try { await api(`/equipe/${enc(p.id)}`, { methode: 'DELETE' }); } catch (e) { erreur(e.message); }
  await dessinerEquipe(racine);
}

function ligne(p) {
  const b = (txt, f, cls = '') => h('button', { class: `btn petit ${cls}`, type: 'button', onclick: f, 'aria-label': t('equipe.aria_bouton', { action: txt, nom: p.nom || p.id }) }, txt);
  return h('tr', { class: p.actif ? '' : 'inactif' },
    h('th', { scope: 'row' }, h('div', { class: 'eq-nom' }, p.nom || p.id), h('div', { class: 'eq-id' }, p.id)),
    h('td', null, h('span', { class: `pill ${p.actif ? 'pill-ok' : 'pill-off'}` }, p.actif ? t('equipe.actif') : t('equipe.inactif'))),
    h('td', null, DECL[p.declenchement] || p.declenchement),
    h('td', { class: 'eq-filtre', title: resume(p) }, resume(p)),
    h('td', { class: 'eq-mot' }, p.harnais || p.modele ? libelleMoteur(p.harnais, p.modele) : t('equipe.par_defaut_min')),
    h('td', { class: 'eq-act' }, b(t('equipe.modifier'), () => editer(p)), b(p.actif ? t('equipe.desactiver') : t('equipe.activer'), () => basculerActif(p)), b(t('equipe.retirer'), () => retirer(p), 'danger')));
}

export async function dessinerEquipe(el) {
  racine = el;
  let equipe = [];
  try { [equipe] = await Promise.all([api('/equipe'), chargerHarnais().catch(() => null)]); } catch (e) { erreur(e.message); }
  if (racine !== el || !el.isConnected) return;
  remplacer(el, h('div', { class: 'equipe' },
    h('div', { class: 'eq-tete' }, h('h2', null, t('equipe.titre')), boutonAide('equipe'), h('button', { class: 'btn primaire', type: 'button', onclick: () => editer(null) }, t('equipe.nouvel_expert_btn'))),
    h('aside', { class: 'encart' },
      h('p', null, garnir(t('equipe.encart_1'), { ok: h('b', null, t('equipe.encart_ok')), reserves: h('b', null, t('equipe.encart_reserves')) })),
      h('p', null, garnir(t('equipe.encart_2'), { fichier: h('code', null, 'config.toml'), section: h('code', null, '[validation]'), humain: h('code', null, 'mode = "humain"'), persona: h('code', null, 'mode = "persona"'), boucles: h('code', null, 'boucles_max') }))),
    equipe.length ? h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, [t('equipe.col_expert'), t('equipe.col_etat'), t('equipe.col_declenchement'), t('equipe.col_filtre'), t('equipe.col_moteur'), ''].map((x) => h('th', { scope: 'col' }, x)))),
      h('tbody', null, equipe.map(ligne)))
      : h('p', { class: 'vide' }, t('equipe.aucun'))));
}
