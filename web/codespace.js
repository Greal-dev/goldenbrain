// Rôle : bloc « codespace » de l'en-tête d'une tâche (état, Ouvrir dans VS Code / le navigateur, Arrêter, réglage « Où »).
// Frontières : GET/POST /taches/{id}/codespace et /ou ; ne dessine rien si le projet ne déclare aucun codespace.
// L'état vient de `gh` (lent) : le bloc se dessine d'emblée depuis le dernier état connu et se met à jour sans bloquer.
import { h, remplacer } from './dom.js';
import { api, post } from './api.js';
import { erreur } from './store.js';
import { t } from './langues.js';

const enc = encodeURIComponent;
const FRAICHEUR_MS = 20000;
const etats = new Map(); // id de tâche -> { vue, quand }
const derniers = new Map(); // id de tâche -> dernier bloc dessiné (l'en-tête se redessine souvent)
const LIBELLES = { Available: t('codespace.etat_disponible'), Shutdown: t('codespace.etat_arrete'), Starting: t('codespace.etat_demarrage'), ShuttingDown: t('codespace.etat_arret_en_cours'), Rebuilding: t('codespace.etat_reconstruction') };

function dessiner(el, x, vue, surTache) {
  if (!vue?.declaration) { remplacer(el); el.hidden = true; return; }
  el.hidden = false;
  const b = (txt, f, titre, off) => h('button', { class: 'btn petit', type: 'button', title: titre, disabled: off ? true : null, onclick: f }, txt);
  const geste = async (quoi) => {
    try { etats.set(x.id, { vue: await post(`/taches/${enc(x.id)}/codespace/${quoi}`), quand: Date.now() }); } catch (e) { erreur(e.message); }
    dessiner(el, x, etats.get(x.id)?.vue, surTache);
  };
  const ou = h('select', { 'aria-label': t('codespace.ou_aria'), title: t('codespace.ou_titre') },
    h('option', { value: 'poste', selected: vue.ou !== 'codespace' ? true : null }, t('codespace.ou_poste')),
    h('option', { value: 'codespace', selected: vue.ou === 'codespace' ? true : null }, t('codespace.ou_codespace')));
  ou.addEventListener('change', async () => {
    try { surTache(await post(`/taches/${enc(x.id)}/ou`, { ou: ou.value })); etats.delete(x.id); } catch (e) { erreur(e.message); ou.value = vue.ou; }
  });
  const nom = vue.nom || vue.declaration;
  const etat = vue.erreur ? t('codespace.indisponible', { motif: vue.erreur }) : (vue.etat ? (LIBELLES[vue.etat] || vue.etat) : '…');
  remplacer(el, h('span', { class: 'cs-nom', title: vue.depot || nom }, `☁ ${nom}`), h('span', { class: `cs-etat cs-${(vue.etat || 'inconnu').toLowerCase()}` }, etat),
    b('VS Code', () => geste('code'), t('codespace.vscode_titre'), !!vue.erreur),
    b(t('codespace.navigateur'), () => geste('web'), t('codespace.navigateur_titre'), !!vue.erreur),
    b(t('codespace.arreter'), () => geste('arreter'), t('codespace.arreter_titre'), !!vue.erreur || vue.etat === 'Shutdown'),
    ou);
}

export function blocCodespace(x, surTache) {
  const el = h('span', { class: 'codespace', hidden: true });
  derniers.set(x.id, el);
  const connu = etats.get(x.id);
  dessiner(el, x, connu?.vue, surTache);
  if (!connu || Date.now() - connu.quand > FRAICHEUR_MS) {
    etats.set(x.id, { vue: connu?.vue, quand: Date.now() }); // une seule demande à la fois
    api(`/taches/${enc(x.id)}/codespace`).then((vue) => {
      etats.set(x.id, { vue, quand: Date.now() });
      const e = derniers.get(x.id);
      if (e?.isConnected) dessiner(e, x, vue, surTache);
    }).catch(() => etats.delete(x.id));
  }
  return el;
}
