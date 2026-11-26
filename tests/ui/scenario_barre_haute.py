"""Barre haute (INV-BARRE-1) : elle ne déborde jamais de la fenêtre à 1366, 1280 et 1024 px, en mode discussion comme en disposition
complète, en français et en allemand (libellés longs), compteurs à trois chiffres et tous les repères allumés (pire cas) ; « Nouvelle tâche » et
« Menu » restent visibles ; les trois pastilles « À moi » portent leur libellé tant que la place le permet, sinon icône + nombre + infobulle.
Vault temporaire chargé (260 tâches), harnais factice.
"""
import pytest

import charge
from conftest import demarrer

LARGEURS = [1366, 1280, 1024]
PIRE_CAS = """() => {
  for (const id of ['btn-align', 'btn-etat']) { const b = document.getElementById(id); if (b) b.hidden = false; }
  document.getElementById('n-avalider').textContent = '186'; document.getElementById('n-questions').textContent = '150';
  document.getElementById('n-afaire').textContent = '122'; document.getElementById('n-props').textContent = '12';
  let e = document.getElementById('eco-repere');
  if (!e) { e = document.createElement('span'); e.id = 'eco-repere'; e.className = 'eco-repere'; document.querySelector('.b-haut').insertBefore(e, document.getElementById('btn-nouvelle')); }
  e.hidden = false; e.textContent = 'Intelligent → Économie : quota à 82 %, reprise 03:00';
}"""
MESURE = """() => {
  const barre = document.querySelector('.b-haut'), vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  const sortants = [];
  for (const e of barre.querySelectorAll(':scope > *, :scope > .rel > button, :scope > .b-menu-zone > button')) {
    if (!vis(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.right > innerWidth + 0.5 || r.left < -0.5) sortants.push((e.id || e.className) + ' ' + Math.round(r.left) + '→' + Math.round(r.right));
  }
  const vue = (id) => { const e = document.getElementById(id); return !!e && vis(e) && e.getBoundingClientRect().right <= innerWidth + 0.5; };
  return { sortants, barre: barre.scrollWidth - barre.clientWidth, page: document.documentElement.scrollWidth - innerWidth,
           discussion: document.body.classList.contains('discussion'), nouvelle: vue('btn-nouvelle'), menu: vue('btn-menu'),
           niveau: [...barre.attributes].filter((a) => /^data-r\\d$/.test(a.name)).length,
           textes: ['btn-avalider', 'btn-questions', 'btn-afaire'].map((i) => document.getElementById(i).innerText.trim()),
           titres: ['btn-avalider', 'btn-questions', 'btn-afaire'].map((i) => document.getElementById(i).title) };
}"""


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("barre"), '\n[interface]\nmode = "avance"\n', avant=charge.peupler):
        yield s


def ouvrir(navigateur, srv, largeur, langue, discussion):
    ctx = navigateur.new_context(viewport={"width": largeur, "height": 768}, locale=langue)
    ctx.add_init_script("try{localStorage.setItem('gb.disposition-vu','1')}catch(e){}")
    if not discussion:
        ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")
    p = ctx.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.goto(srv.url + ("/#t=" + charge.FIL_LONG if discussion else "/"))
    p.wait_for_selector(".composer textarea" if discussion else "#volet-gauche .ligne", timeout=90000)
    p.ctx = ctx
    return p


@pytest.mark.parametrize("discussion", [True, False], ids=["discussion", "complete"])
@pytest.mark.parametrize("langue", ["fr-FR", "de-DE"])
@pytest.mark.parametrize("largeur", LARGEURS)
def test_la_barre_ne_deborde_jamais_meme_au_pire_cas(navigateur, srv, largeur, langue, discussion):
    p = ouvrir(navigateur, srv, largeur, langue, discussion)
    try:
        p.evaluate(PIRE_CAS)
        p.wait_for_timeout(300)
        m = p.evaluate(MESURE)
        assert m["discussion"] == discussion
        assert not m["sortants"], f"éléments hors fenêtre à {largeur} px : {m['sortants']}"
        assert m["barre"] <= 0 and m["page"] <= 0, f"débordement barre {m['barre']} px, page {m['page']} px"
        assert m["nouvelle"], "« Nouvelle tâche » sortie de la fenêtre"
        assert m["menu"] or not discussion, "« Menu » sorti de la fenêtre"
        if m["niveau"] >= 5:  # repli des pastilles « À moi » : icône + nombre, l'infobulle porte le libellé
            assert all(t and not t.isdigit() for t in m["titres"]), m["titres"]
    finally:
        p.ctx.close()


@pytest.mark.parametrize("discussion", [True, False], ids=["discussion", "complete"])
@pytest.mark.parametrize("largeur", [1366, 1280])
def test_les_trois_pastilles_a_moi_portent_leur_libelle_quand_la_place_le_permet(navigateur, srv, largeur, discussion):
    p = ouvrir(navigateur, srv, largeur, "fr-FR", discussion)
    try:
        p.wait_for_function("() => /\\d/.test(document.getElementById('n-avalider').textContent)", timeout=30000)
        m = p.evaluate(MESURE)
        for texte, libelle in zip(m["textes"], ("À valider", "Questions", "À faire")):
            assert texte.startswith(libelle), f"pastille sans libellé à {largeur} px : {m['textes']} niveau {m['niveau']}"
            assert any(c.isdigit() for c in texte), m["textes"]
    finally:
        p.ctx.close()


DISJOINTS = """() => {
  const barre = document.querySelector('.b-haut');
  const ok = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden' && !e.closest('.panneau, .rech-liste, .b-menu, [hidden]'); };
  const els = [...barre.querySelectorAll('button, input, a, #eco-repere, #conn, .etat-zone')].filter(ok)
    .filter((e) => !e.matches('.etat-zone') || ![...e.querySelectorAll('button')].some(ok));
  const nom = (e) => e.id || e.className || e.tagName;
  const rects = els.map((e) => [nom(e), e.getBoundingClientRect()]);
  const chevauche = [], dehors = [];
  rects.forEach(([n, r]) => { if (r.left < -0.5 || r.right > innerWidth + 0.5) dehors.push(n + ' ' + Math.round(r.left) + '→' + Math.round(r.right)); });
  for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
    const a = rects[i][1], b = rects[j][1];
    if (a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5) chevauche.push(rects[i][0] + ' × ' + rects[j][0]);
  }
  const coupes = els.filter((e) => e.matches('.btn-compte, #btn-nouvelle, #marque') && e.scrollWidth > e.clientWidth + 0.5).map((e) => nom(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  const vue = (id) => { const e = document.getElementById(id); return !!e && ok(e); };
  return { chevauche, dehors, coupes, noms: rects.map(([n]) => n),
           a_moi: ['btn-avalider', 'btn-questions', 'btn-afaire'].map(vue), nouvelle: vue('btn-nouvelle'), menu: vue('btn-menu') };
}"""


@pytest.mark.parametrize("discussion", [True, False], ids=["discussion", "complete"])
@pytest.mark.parametrize("pire", [False, True], ids=["normal", "pire"])
@pytest.mark.parametrize("largeur", [1366, 1280, 1024, 390])
def test_aucun_element_de_la_barre_ne_chevauche_un_autre_ni_n_est_rogne(navigateur, srv, largeur, pire, discussion):
    p = ouvrir(navigateur, srv, largeur, "fr-FR", discussion)
    try:
        p.wait_for_function("() => /\\d/.test(document.getElementById('n-avalider').textContent)", timeout=30000)
        if pire:
            p.evaluate(PIRE_CAS)
        p.wait_for_timeout(400)
        m = p.evaluate(DISJOINTS)
        assert not p.erreurs, p.erreurs
        assert not m["chevauche"], f"chevauchements à {largeur} px : {m['chevauche']} ({m['noms']})"
        assert not m["dehors"], f"hors fenêtre à {largeur} px : {m['dehors']}"
        assert not m["coupes"], f"texte rogné à {largeur} px : {m['coupes']}"
        assert m["nouvelle"], "« Nouvelle tâche » absente ou invisible"
        if largeur >= 1024:
            assert all(m["a_moi"]), f"pastille « À moi » absente à {largeur} px : {m['a_moi']}"
    finally:
        p.ctx.close()
