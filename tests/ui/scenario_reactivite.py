"""Réactivité de l'interface (tâche « Interface réactive ») : budget de temps mesuré sur un vault chargé comme le vrai.

Charge : 260 tâches, 150 décisions, une tâche au fil de 200 messages (`charge.py`). Budget (1366×768 et téléphone 390×844) :
premier affichage utile ≤ 1,5 s · ouverture d'une tâche → derniers messages visibles ≤ 300 ms · clic sur un intercalaire → volet ouvert
≤ 150 ms sans saut de mise en page · frappe < 50 ms même fil long · défilement fluide (images ≤ 50 ms) · aucun rechargement de l'arbre ou du
fil sur l'événement d'une autre tâche · poids des requêtes du chargement mesuré, sans appel en double.
Les mesures s'impriment (`pytest -s`) et s'écrivent dans le fichier de `GB_MESURES` s'il est défini. Marge de bruit : GB_MARGE (défaut 1).
"""
from __future__ import annotations

import json
import os
import time

import pytest

import charge
import univers
from conftest import demarrer

MARGE = float(os.environ.get("GB_MARGE", "1"))
ECRANS = {"bureau": (1366, 768), "telephone": (390, 844)}
RESULTATS: dict = {}

JS_ATTENDRE = """
async (cond) => { const f = new Function('return (' + cond + ')');
  const t0 = performance.now();
  while (!f()) { if (performance.now() - t0 > 8000) return -1; await new Promise((r) => requestAnimationFrame(r)); }
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));  // jusqu'à l'image peinte
  return performance.now() - t0; }
"""


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("charge"), ttl=2):  # le défaut réel de l'index
        charge.peupler(s.vault)
        yield s


@pytest.fixture(scope="module", autouse=True)
def rapport():
    yield
    print("\nMESURES " + json.dumps(RESULTATS, indent=1, ensure_ascii=False))
    if chemin := os.environ.get("GB_MESURES"):
        open(chemin, "w", encoding="utf-8").write(json.dumps(RESULTATS, indent=1, ensure_ascii=False))


def contexte(navigateur, ecran):
    w, h = ECRANS[ecran]
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR", has_touch=ecran == "telephone", is_mobile=ecran == "telephone")
    return ctx


def nouvelle(ctx):
    p = ctx.new_page()
    p.erreurs = []
    p.on("console", lambda m: p.erreurs.append(m.text) if m.type in ("error", "warning") else None)
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.requetes = []
    p.on("response", lambda r: p.requetes.append((r.request.method, r.url, int(r.headers.get("content-length") or 0) or None, r)) if "/api/" in r.url and "/api/evenements" not in r.url else None)  # le flux SSE ne se termine jamais
    return p


def silence(p, ms=1200):
    """Attend que plus aucune requête API ne parte pendant `ms` (le flux SSE, jamais inactif, interdit `networkidle`)."""
    n = -1
    while n != len(p.requetes):
        n = len(p.requetes)
        p.wait_for_timeout(ms)


def noter(ecran, cle, val):
    RESULTATS.setdefault(ecran, {})[cle] = round(val, 1) if isinstance(val, float) else val


@pytest.mark.parametrize("ecran", ECRANS)
def test_premier_affichage_utile_et_poids_du_chargement(navigateur, srv, ecran):
    ctx = contexte(navigateur, ecran)
    p = nouvelle(ctx)
    t0 = time.perf_counter()
    p.goto(srv.url + "/", wait_until="commit")
    p.wait_for_selector("#volet-gauche .ligne", timeout=60000)
    util = (time.perf_counter() - t0) * 1000
    silence(p)
    api = [(m, u.split("/api", 1)[1], r) for m, u, _, r in p.requetes if m == "GET"]
    octets = 0
    for _, _, r in api:
        try:
            octets += len(r.body())
        except Exception:
            pass
    doubles = sorted({u for _, u, _ in api if sum(1 for _, v, _ in api if v == u) > 1})
    noter(ecran, "premier_affichage_ms", util)
    noter(ecran, "requetes_api_chargement", len(api))
    noter(ecran, "octets_api_chargement", octets)
    noter(ecran, "appels_en_double", doubles)
    ctx.close()
    assert util <= 1500 * MARGE, f"premier affichage utile {util:.0f} ms"
    assert not doubles, f"appels en double au chargement : {doubles}"
    assert not p.erreurs, p.erreurs


@pytest.mark.parametrize("ecran", ECRANS)
def test_ouverture_d_une_tache_au_long_fil_montre_les_derniers_messages_vite(navigateur, srv, ecran):
    ctx = contexte(navigateur, ecran)
    p = nouvelle(ctx)
    p.goto(srv.url + "/")
    p.wait_for_selector("#volet-gauche .ligne", timeout=60000)
    silence(p)
    ms = p.evaluate(JS_ATTENDRE.replace("async (cond) => {", "async (cond) => { location.hash = '#t=" + charge.FIL_LONG + "';"),
                    "(() => { const m = [...document.querySelectorAll('.conv .msg')]; const d = document.querySelector('.d-defile'); "
                    "return m.some((x) => x.textContent.includes('Message 199')) && d && d.scrollHeight - d.scrollTop - d.clientHeight < 80; })()")
    noter(ecran, "ouverture_tache_ms", ms)
    ctx.close()
    assert 0 < ms <= 300 * MARGE, f"derniers messages visibles en {ms:.0f} ms"


def ouvrir_fil(navigateur, srv, ecran="bureau"):
    ctx = contexte(navigateur, ecran)
    p = nouvelle(ctx)
    p.goto(srv.url + "/")
    p.wait_for_selector("#volet-gauche .ligne", timeout=30000)
    silence(p)
    p.evaluate("location.hash = '#t=" + charge.FIL_LONG + "'")
    for _ in range(100):  # pas de wait_for_function : la CSP de la page interdit l'évaluation de chaîne
        if p.evaluate("[...document.querySelectorAll('.conv .msg')].some((x) => x.textContent.includes('Message 199'))"):
            break
        p.wait_for_timeout(100)
    else:
        raise AssertionError("le long fil ne s'affiche pas")
    silence(p)
    return ctx, p


def decalage(p, js_action, cond):
    """Temps jusqu'à `cond` peint (ms) et somme des décalages de mise en page (layout-shift) pendant le geste."""
    src = """async () => {
      let saut = 0; const po = new PerformanceObserver((l) => l.getEntries().forEach((e) => { if (!e.hadRecentInput) saut += e.value; }));
      po.observe({ type: 'layout-shift', buffered: false });
      const f = () => (COND); const t0 = performance.now();
      ACTION;
      while (!f()) { if (performance.now() - t0 > 4000) return { ms: -1, saut }; await new Promise((r) => requestAnimationFrame(r)); }
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const ms = performance.now() - t0; await new Promise((r) => setTimeout(r, 300)); po.disconnect(); return { ms, saut }; }"""
    return p.evaluate(src.replace("ACTION", js_action).replace("COND", cond))


def test_intercalaires_ouvrent_leur_volet_en_150_ms_sans_saut(navigateur, srv):
    ctx, p = ouvrir_fil(navigateur, srv)
    cas = {
        "menu": ("document.querySelector('#btn-menu').click()", "document.querySelector('#b-menu').offsetHeight > 0"),
        "notes": ("document.querySelector('.volet-t-notes .p-replier').click()", "!document.querySelector('.volet-t-notes').classList.contains('replie')"),
    }
    for nom, (action, cond) in cas.items():
        r = decalage(p, action, cond)
        noter("bureau", f"intercalaire_{nom}_ms", r["ms"])
        noter("bureau", f"intercalaire_{nom}_saut", round(r["saut"], 3))
        assert 0 < r["ms"] <= 150 * MARGE, f"{nom} : {r['ms']:.0f} ms"
        assert r["saut"] <= 0.1, f"{nom} : décalage de mise en page {r['saut']:.2f}"
    # Épingler l'arbre (clic) repousse volontairement la conversation : sa durée est bornée, son décalage est le geste lui-même.
    r = decalage(p, "document.querySelector('#rail-arbre').click()", "document.body.classList.contains('arbre-epingle') && document.querySelector('#volet-gauche-corps').offsetWidth > 200")
    noter("bureau", "intercalaire_arbre_epingle_ms", r["ms"])
    assert 0 < r["ms"] <= 150 * MARGE, f"arbre épinglé : {r['ms']:.0f} ms"
    ctx.close()


@pytest.mark.parametrize("ecran", ECRANS)
def test_frappe_dans_le_compositeur_d_un_long_fil_sans_latence(navigateur, srv, ecran):
    ctx, p = ouvrir_fil(navigateur, srv, ecran)
    p.evaluate("""() => { window.__pire = 0; new PerformanceObserver((l) => l.getEntries().forEach((e) => { window.__pire = Math.max(window.__pire, e.duration); }))
      .observe({ type: 'event', durationThreshold: 16, buffered: false }); }""")
    p.click(".composer textarea")
    p.keyboard.type("Une phrase assez longue pour sentir la latence de frappe dans un long fil.", delay=15)
    pire = p.evaluate("window.__pire")
    noter(ecran, "frappe_pire_evenement_ms", pire)
    ctx.close()
    assert pire < 50 * MARGE + 8, f"événement de frappe le plus lent : {pire:.0f} ms"  # 8 ms : la durée est arrondie au pas de 8 ms


@pytest.mark.parametrize("ecran", ECRANS)
def test_defilement_du_fil_de_200_messages_fluide(navigateur, srv, ecran):
    ctx, p = ouvrir_fil(navigateur, srv, ecran)
    r = p.evaluate("""async () => { const d = document.querySelector('.d-defile'); d.scrollTop = 0;
      const dt = []; let dernier = performance.now(); const haut = d.scrollHeight - d.clientHeight;
      for (let i = 1; i <= 60; i++) { d.scrollTop = haut * i / 60; await new Promise((r) => requestAnimationFrame(r)); const n = performance.now(); dt.push(n - dernier); dernier = n; }
      dt.sort((a, b) => a - b); return { p95: dt[Math.floor(dt.length * .95)], max: dt.at(-1), n: d.querySelectorAll('.msg').length }; }""")
    noter(ecran, "defilement_image_p95_ms", r["p95"])
    noter(ecran, "defilement_image_max_ms", r["max"])
    ctx.close()
    assert r["p95"] <= 50 * MARGE, f"défilement : 95 % des images en {r['p95']:.0f} ms ou moins"


def test_evenement_d_une_autre_tache_ne_recharge_ni_arbre_ni_fil(navigateur, srv):
    ctx, p = ouvrir_fil(navigateur, srv)
    p.evaluate("() => { document.querySelector('.conv .msg').dataset.temoin = '1'; }")
    avant = len(p.requetes)
    corps = json.dumps({"texte": "[bavard] bonjour"})
    p.evaluate("([u, c]) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Orchestrateur': '1' }, body: c })",
               ["/api/taches/charge-5/messages", corps])
    silence(p, 1500)
    suite = [u.split("/api", 1)[1] for _, u, _, _ in p.requetes[avant:]]
    refait = p.evaluate("!document.querySelector('.conv .msg')?.dataset.temoin")
    noter("bureau", "requetes_apres_evenement_autre_tache", suite)
    noter("bureau", "fil_redessine_par_evenement_autre_tache", refait)
    ctx.close()
    assert sum(u.startswith("/arbre") for u in suite) <= 1, suite  # l'indicateur de ligne de l'arbre dépend du tour : un seul rechargement
    assert not any(u.startswith("/propositions") for u in suite), suite
    assert not any("/conversation" in u for u in suite), suite  # le fil n'est jamais relu
    assert sum(u == f"/taches/{charge.FIL_LONG}" for u in suite) <= 1, suite  # la fiche ouverte se relit au plus une fois (redessinée seulement si elle a changé)
    assert not refait, "le fil ouvert a été redessiné"


@pytest.mark.skipif(not os.environ.get("GB_CAPTURES"), reason="captures à la demande : GB_CAPTURES=<dossier>")
@pytest.mark.parametrize("ecran", ECRANS)
def test_captures_du_fil_long_en_mode_discussion(navigateur, srv, ecran):
    ctx, p = ouvrir_fil(navigateur, srv, ecran)
    p.mouse.move(w := ECRANS[ecran][0] - 1, ECRANS[ecran][1] - 1)
    p.screenshot(path=os.path.join(os.environ["GB_CAPTURES"], f"fil-long-{ecran}.png"))
    ctx.close()
