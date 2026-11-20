// Rôle : avis d'un agent rapide avant une promotion ou une réduction — attente annulable, dialogue « L'agent déconseille… ».
// Frontières : POST /conseil seulement ; ne fait rien d'autre. Un avis `indisponible` (ou une erreur) ne bloque jamais l'action.
import { h } from './dom.js';
import { post } from './api.js';
import { formulaire } from './dialogue.js';
import { ouvert } from './interface.js';
import { t } from './langues.js';

// Résout avec {avis, motif, phrase} pour continuer (`phrase` : texte pour la ligne d'information), ou null si l'utilisateur renonce.
export function consulter(action, cible, quoi) {
  if (!ouvert('conseil')) return Promise.resolve({ avis: 'indisponible', motif: '', phrase: '' }); // INV-INTERFACE-1 : aucun avis lancé
  return new Promise((resolve) => {
    const ctrl = new AbortController();
    let fini = false;
    const attente = h('p', { class: 'dlg-texte', role: 'status' }, h('span', { class: 'tourne' }), ' ' + t('conseil.examine', { quoi }));
    const sans = h('button', { type: 'button', class: 'btn primaire', onclick: () => clore({ avis: 'indisponible', motif: '', phrase: '' }) }, t('conseil.sans_avis'));
    const renoncer = h('button', { type: 'button', class: 'btn', onclick: () => clore(null) }, t('conseil.annuler'));
    const dlg = h('dialog', { class: 'dlg', 'aria-label': t('conseil.avis_agent'), 'aria-busy': 'true' },
      h('div', { class: 'dlg-form' }, h('h3', null, t('conseil.avis_agent')), attente, h('div', { class: 'dlg-actions' }, renoncer, sans)));
    function clore(v) {
      if (fini) return;
      fini = true; ctrl.abort(); dlg.close(); resolve(v);
    }
    dlg.addEventListener('cancel', (e) => { e.preventDefault(); clore(null); }); // Échap = renoncer
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    sans.focus();

    post('/conseil', { action, ...cible }, ctrl.signal).then(async (r) => {
      if (fini) return;
      fini = true; dlg.close();
      const avis = r?.avis, motif = String(r?.motif || '').trim().replace(/[.\s]+$/, ''); // sans point final : la phrase du dialogue en pose un
      if (avis === 'defavorable') {
        const oui = await formulaire({
          titre: t('conseil.deconseille'), valider: t('conseil.oui'), annuler: t('conseil.non'), focus: 'annuler',
          texte: t('conseil.continuer', { motif: (motif || t('conseil.aucun_motif')).trim().replace(/\.+$/, '') }),
        });
        resolve(oui ? { avis, motif, phrase: t('conseil.deconseillait', { motif: motif || t('conseil.aucun_motif_min') }) } : null);
      } else if (avis === 'favorable') resolve({ avis, motif, phrase: (motif ? t('conseil.favorable_motif', { motif }) : t('conseil.favorable')) });
      else resolve({ avis: 'indisponible', motif, phrase: (motif ? t('conseil.indisponible_motif', { motif }) : t('conseil.indisponible')) });
    }).catch((e) => {
      if (fini || e.name === 'AbortError') return;
      fini = true; dlg.close();
      resolve({ avis: 'indisponible', motif: '', phrase: t('conseil.indisponible') }); // jamais bloquant
    });
  });
}
