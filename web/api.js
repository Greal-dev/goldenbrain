// Rôle : client de l'API HTTP (/api) et flux SSE avec reconnexion.
// Frontières : ne touche pas au DOM (la confirmation INV-VERROU-1 est injectée par verrou.js). INV-API-1 : tout non-GET porte X-Orchestrateur: 1.
// INV-VERSION-1 : une erreur portant `perime: true` (serveur plus ancien que le code) prévient `surPerime` et reçoit un message neutre.
import { t } from './langues.js';
export const MSG_PERIME = t('api.perime');
let surPerime = null;
export const brancherPerime = (f) => { surPerime = f; };
// INV-VERROU-1 : 409 `occupee` → `surOccupee(occupee)` (confirmation, verrou.js) ; oui : même requête avec `forcer: true` ;
// non : erreur `annule` au message MSG_ANNULE, que la bannière tait (rien n'a changé).
export const MSG_ANNULE = t('api.annule');
let surOccupee = null;
export const brancherOccupee = (f) => { surOccupee = f; };

// INV-DISTANT-7 : depuis un appareil distant, un geste à risque répond 428 ; confirmé, il repart avec X-Orch-Confirmation.
export async function api(chemin, { methode = 'GET', corps, signal, confirme = false } = {}) {
  const opts = { method: methode, headers: {}, signal };
  if (methode !== 'GET') {
    opts.headers['X-Orchestrateur'] = '1';
    if (confirme) opts.headers['X-Orch-Confirmation'] = '1';
    if (corps !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(corps); }
  }
  let r;
  try { r = await fetch('/api' + chemin, opts); } catch (e) { if (e.name === 'AbortError') throw e; throw new Error(t('api.injoignable')); }
  let data = null;
  try { data = await r.json(); } catch { /* corps vide */ }
  if (r.status === 409 && data?.occupee && surOccupee && methode !== 'GET' && !corps?.forcer) {
    if (await surOccupee(data.occupee)) return api(chemin, { methode, corps: { ...(corps || {}), forcer: true }, signal });
    const e = new Error(MSG_ANNULE); e.annule = true;
    throw e;
  }
  if (r.status === 428 && !confirme && globalThis.confirm?.(t('api.confirmer', { geste: data?.detail || t('api.geste_risque') }))) {
    return api(chemin, { methode, corps, signal, confirme: true });
  }
  if (!r.ok) {
    const d = data && data.detail;
    const e = new Error((typeof d === 'string' ? d : d && d.message) || t('api.erreur', { statut: r.status }));
    e.statut = r.status; e.corps = data; // 409 / 501 : l'appelant décide (conflit de note, route absente)
    if (data?.perime) { e.perime = true; e.message = MSG_PERIME; surPerime?.(); }
    throw e;
  }
  return data;
}
export const post = (chemin, corps, signal) => api(chemin, { methode: 'POST', corps, signal });

// Sonde sans effet de bord pour attendre le retour du serveur : null s'il ne répond pas dans le délai.
export async function sonder(delaiMs = 2500) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), delaiMs);
  try { const r = await fetch('/api/etat', { signal: c.signal, cache: 'no-store' }); return r.ok ? await r.json() : null; } catch { return null; } finally { clearTimeout(t); }
}

export function ouvrirFlux(surEvenement, surConnexion) {
  let es;
  const connecter = () => {
    es = new EventSource('/api/evenements');
    es.onopen = () => surConnexion(true);
    es.onmessage = (m) => { try { surEvenement(JSON.parse(m.data)); } catch { /* ligne ignorée */ } };
    es.onerror = () => {
      surConnexion(false);
      if (es.readyState === EventSource.CLOSED) { es.close(); setTimeout(connecter, 2000); }
    };
  };
  connecter();
}
