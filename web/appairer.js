// Rôle : page d'appairage d'un téléphone, ouverte par le code QR de Réglages → Appareils.
// INV-DISTANT-5 : le code voyage dans le fragment (location.hash), jamais envoyé dans l'adresse ni écrit dans un journal HTTP ;
// il est échangé une fois contre le cookie de l'appareil (HttpOnly, posé par le serveur), puis effacé de l'adresse.
// Frontières : POST /api/appareils/echange seulement (et la langue, INV-LANGUE-1) ; page autonome, sans le reste de l'interface.
import { t, traduireDom } from './langues.js';

traduireDom();
document.title = t('appairer.titre');
const message = document.getElementById('message');
const code = decodeURIComponent(location.hash.slice(1));
history.replaceState(null, '', location.pathname);

// Échec : le code reste en mémoire de la page (jamais dans l'adresse), « Réessayer » rejoue l'échange sans re-scanner.
function echec(texte, rejouable) {
  message.textContent = texte;
  if (!rejouable) return;   // un code refusé est périmé ou déjà utilisé : seul un nouveau code sur le poste aide
  const b = Object.assign(document.createElement('button'), { type: 'button', className: 'btn', textContent: t('appairer.reessayer') });
  b.style.cssText = 'display:block;margin-top:12px;min-height:48px';
  b.addEventListener('click', echanger);
  message.append(b);
}

async function echanger() {
  message.textContent = t('appairer.appairage_de_cet_appareil');
  if (!code) { message.textContent = t('appairer.sans_code'); return; }
  try {
    const r = await fetch('/api/appareils/echange', { method: 'POST',
      headers: { 'X-Orchestrateur': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { echec(t('appairer.refuse', { motif: d.detail || r.status })); return; }
    message.textContent = t('appairer.ok', { nom: d.nom });
    location.replace('/');
  } catch { echec(t('appairer.injoignable'), true); }
}
echanger();
