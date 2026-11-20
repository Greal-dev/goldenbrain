// Rôle : page d'appairage d'un téléphone, ouverte par le code QR de Réglages → Appareils.
// INV-DISTANT-5 : le code voyage dans le fragment (location.hash), jamais envoyé dans l'adresse ni écrit dans un journal HTTP ;
// il est échangé une fois contre le cookie de l'appareil (HttpOnly, posé par le serveur), puis effacé de l'adresse.
// Frontières : POST /api/appareils/echange seulement (et la langue, INV-LANGUE-1) ; page autonome, sans le reste de l'interface.
import { t, traduireDom } from './langues.js';

traduireDom();
const message = document.getElementById('message');
const code = decodeURIComponent(location.hash.slice(1));
history.replaceState(null, '', location.pathname);

async function echanger() {
  if (!code) { message.textContent = t('appairer.sans_code'); return; }
  try {
    const r = await fetch('/api/appareils/echange', { method: 'POST',
      headers: { 'X-Orchestrateur': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { message.textContent = t('appairer.refuse', { motif: d.detail || r.status }); return; }
    message.textContent = t('appairer.ok', { nom: d.nom });
    location.replace('/');
  } catch { message.textContent = t('appairer.injoignable'); }
}
echanger();
