"""Audit L4 (23/11) — cohérence et mise en page des écrans : un test par symptôme constaté (A5 à A22).

Chaque test s'exécute au viewport et dans la langue du constat. Vault temporaire, harnais factice.
"""
import time
import urllib.request

import pytest

import univers
from conftest import demarrer

LANGUES = ("fr", "de", "es")
LONG = "Préparer la réponse complète au dossier de consultation du marché de maintenance des bâtiments"


@pytest.fixture(scope="module", params=LANGUES)
def srv(request, tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("audit"), f'\n[interface]\nmode = "avance"\nlangue = "{request.param}"\n'):
        s.code = request.param
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/valider.md", univers.tache("À relire", "fait", "session: abc123\n"))
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/longue.md", univers.tache(LONG))
        for _ in range(40):
            if "À relire" in urllib.request.urlopen(f"{s.url}/api/arbre").read().decode("utf-8") and "Préparer la réponse" in urllib.request.urlopen(f"{s.url}/api/arbre").read().decode("utf-8"):
                break
            time.sleep(0.25)
        yield s


@pytest.fixture(scope="module")
def srv_simple(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("simple"), '\n[interface]\nmode = "simple"\nlangue = "fr"\n'):
        yield s


def ouvrir(navigateur, srv, route="/", w=1366, h=768):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")  # INV-DISCUSSION-1 : disposition complète
    p = ctx.new_page()
    p.goto(srv.url + route)
    p.wait_for_timeout(900)
    p.ctx = ctx
    return p


def test_fil_d_ariane_sans_interrogation_ni_meta(navigateur, srv):
    p = ouvrir(navigateur, srv, "/#t=fermee")
    fil = p.inner_text("body")
    assert "_meta" not in fil, "le dossier technique _meta s'affiche tel quel"
    assert "? ›" not in fil and "› ?" not in fil, "la casquette inconnue « ? » s'affiche"
    arbre = p.inner_text('[role="tree"]')
    assert "_meta" not in arbre and "\n?\n" not in f"\n{arbre}\n"
    p.ctx.close()


def test_statut_a_valider_meme_libelle_partout(navigateur, srv):
    p = ouvrir(navigateur, srv, "/#t=valider")
    p.click("#btn-avalider")  # INV-DEROULANT-1 : l'aperçu déroule, « Filtrer l'arbre » pose le filtre
    p.click("#panneau-avalider [data-tout-voir]")
    badge = p.get_attribute('.badge-st[data-statut="a-valider"]', "data-main")  # la pastille dit « à qui la main » (INV-MAIN-1) ; le sélecteur garde le libellé du statut
    sel = p.eval_on_selector('select[aria-label]', "e => e.options[e.selectedIndex].text")
    assert badge == "humain" and sel.strip(), f"sélecteur « {sel} », pastille « {badge} »"
    p.ctx.close()


def test_taches_proches_sans_statut_brut(navigateur, srv):
    p = ouvrir(navigateur, srv)
    p.click("#btn-nouvelle")
    p.fill('[name="titre"]', "Bail")
    p.wait_for_selector(".proche-titre", timeout=4000)
    texte = p.inner_text("dialog")
    assert "a-faire" not in texte and "en-cours" not in texte
    p.ctx.close()


def test_titres_tronques_portent_une_info_bulle(navigateur, srv):
    for route in ("/", "/#en-cours", "/#aujourdhui", "/#decisions"):
        p = ouvrir(navigateur, srv, route)
        sans = p.evaluate("""() => [...document.querySelectorAll('.c-t, .au-titre, .tr-titre, .dc-titre')].filter(e => e.offsetParent
          && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1) && !(e.title || '').trim()).map(e => e.textContent.trim())""")
        assert not sans, f"{route} : titres coupés sans info-bulle : {sans}"
        p.ctx.close()


def test_bandeau_deux_rangees_nettes_sans_orphelin(navigateur, srv):
    p = ouvrir(navigateur, srv, "/", 1440, 900)
    rangs = p.evaluate("""() => { const m = {}; const plat = (n) => [...n.children].flatMap(e => getComputedStyle(e).display === 'contents' ? plat(e) : [e]);
      for (const e of plat(document.querySelector('.b-haut'))) { if (!e.offsetParent || !e.getBoundingClientRect().width) continue;
      const r = e.getBoundingClientRect(); const y = Math.round((r.top + r.height / 2) / 30); (m[y] = m[y] || []).push(e.id || e.className); } return m }""")
    assert len(rangs) <= 2, f"bandeau sur {len(rangs)} rangées : {rangs}"
    assert all(len(v) >= 4 for v in rangs.values()), f"éléments orphelins : {rangs}"
    p.ctx.close()


def test_colonnes_recherche_et_manager_non_tronques(navigateur, srv):
    p = ouvrir(navigateur, srv, "/")
    tronques = p.evaluate("""() => [...document.querySelectorAll('.cl-tete > *, #btn-manager, #btn-travaux')].filter(e => e.offsetParent && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent.trim())""")
    assert not tronques, f"libellés tronqués : {tronques}"
    ph = p.evaluate("() => { const r = document.querySelector('#recherche'); return r.scrollWidth > r.clientWidth + 1 }")
    assert not ph, "recherche : texte ou repère tronqué"
    p.ctx.close()


def test_chip_a_moi_dans_son_cadre(navigateur, srv):
    p = ouvrir(navigateur, srv, "/")
    p.click("#btn-avalider")  # INV-DEROULANT-1 : l'aperçu déroule, « Filtrer l'arbre » pose le filtre
    p.click("#panneau-avalider [data-tout-voir]")
    p.wait_for_timeout(300)
    chip = p.query_selector("#chip-filtre")
    assert chip and chip.is_visible()
    deborde = p.evaluate("""() => { const c = document.querySelector('#chip-filtre'), t = c.parentElement.getBoundingClientRect(), r = c.getBoundingClientRect();
      return r.right > t.right + 1 || r.left < t.left - 1 || c.scrollWidth > c.clientWidth + 1 }""")
    assert not deborde
    p.ctx.close()


def test_marges_identiques_entre_ecrans_et_guide_mis_en_page(navigateur, srv):
    gouttieres = {}
    for nom, route, sel in (("decisions", "/#decisions", ".decisions"), ("guide", "/#guide", ".guide"), ("reglages", "/#reglages", ".reglages"),
                            ("aujourdhui", "/#aujourdhui", ".aujourdhui")):
        p = ouvrir(navigateur, srv, route)
        gouttieres[nom] = p.evaluate("""s => { const e = document.querySelector(s); if (!e) return null; const pr = e.parentElement.getBoundingClientRect();
          const f = [...e.querySelectorAll('h1,h2,h3,p,button,input,.guide-sommaire,.dc-carte')].find(x => x.offsetParent); const r = f.getBoundingClientRect();
          return Math.round(r.left - pr.left) }""", sel)
        p.ctx.close()
    valeurs = {k: v for k, v in gouttieres.items() if v is not None}
    assert min(valeurs.values()) >= 12, f"marge gauche trop faible : {valeurs}"
    assert max(valeurs.values()) - min(valeurs.values()) <= 8, f"marges inégales : {valeurs}"


def test_guide_mis_en_page(navigateur, srv):
    p = ouvrir(navigateur, srv, "/#guide")
    r = p.evaluate("""() => { const g = document.querySelector('.guide'); const s = g.querySelector('input[type=search], .guide-recherche input, input');
      const gs = getComputedStyle(g); return { pad: parseFloat(gs.paddingLeft), recherche: s ? s.getBoundingClientRect().left - g.getBoundingClientRect().left : 0 } }""")
    assert r["pad"] >= 12, "le Guide est collé au bord"
    p.ctx.close()


def test_envoi_a_vide_message_traduit(navigateur, srv):
    p = ouvrir(navigateur, srv, "/")
    p.click("#btn-nouvelle")
    p.click("dialog button[type=submit], dialog .primaire")
    p.wait_for_timeout(300)
    msg = p.eval_on_selector('dialog [name="titre"]', "e => e.validationMessage")
    assert msg and "Please" not in msg and "fill out" not in msg, f"message natif non traduit : {msg}"
    p.ctx.close()


def test_description_dit_de_quoi_il_s_agit(navigateur, srv):
    p = ouvrir(navigateur, srv, "/")
    p.click("#btn-nouvelle")
    ph = p.get_attribute('dialog [name="description"]', "placeholder") or ""
    assert ph.strip(), "le champ description n'indique pas ce qu'on y met"
    p.ctx.close()


def test_modale_nouvelle_tache_tient_dans_la_fenetre(navigateur, srv):
    p = ouvrir(navigateur, srv, "/", 1366, 768)
    p.click("#btn-nouvelle")
    p.wait_for_timeout(400)
    h = p.evaluate("() => document.querySelector('dialog[open]').getBoundingClientRect().height")
    interne = p.evaluate("() => { const d = document.querySelector('dialog[open]'); return d.scrollHeight - d.clientHeight }")
    assert h <= 768 * 0.82 and interne <= 1, f"modale haute de {h}px, défilement interne {interne}px"
    p.ctx.close()


def test_graphe_cadre_a_l_ouverture_et_bouton_recentrer(navigateur, srv):
    p = ouvrir(navigateur, srv, "/#g")
    p.wait_for_selector("canvas[data-stable='1']", timeout=15000)
    hors = p.evaluate("() => document.querySelector('.g-canvas').horsCadre()")
    assert p.query_selector('[data-id="graphe-recentrer"]'), "pas de bouton « Recentrer »"
    assert hors == 0, f"{hors} nœuds hors du cadre à l'ouverture"
    p.ctx.close()


def test_mode_simple_sans_prevu_ni_slash_nouveau(navigateur, srv_simple):
    p = ouvrir(navigateur, srv_simple, "/#t=mere")
    txt = p.inner_text("body")
    assert "Prévu" not in txt and "/nouveau" not in txt
    p.click("#btn-manager")
    p.wait_for_timeout(500)
    assert "/nouveau" not in p.inner_text("body"), "jargon « /nouveau » en mode simple"
    p.ctx.close()


def test_mobile_recherche_non_tronquee_et_manager_non_colle(navigateur, srv):
    p = ouvrir(navigateur, srv, "/", 390, 844)
    r = p.evaluate("""() => { const i = document.querySelector('#recherche'); const m = document.querySelector('#btn-manager').getBoundingClientRect();
      return { tronque: i.scrollWidth > i.clientWidth + 1, droite: window.innerWidth - m.right, large: i.getBoundingClientRect().width } }""")
    assert not r["tronque"], "placeholder de recherche tronqué"
    assert r["droite"] >= 6, f"le bouton Manager touche le bord ({r['droite']}px)"
    p.ctx.close()


def test_mobile_decisions_scanner_non_coupe_libelle_sur_deux_lignes_max(navigateur, srv):
    p = ouvrir(navigateur, srv, "/#decisions", 390, 844)
    r = p.evaluate("""() => [...document.querySelectorAll('.decisions button')].filter(e => e.offsetParent).map(e => ({ t: e.textContent.trim(), coupe: e.scrollWidth > e.clientWidth + 1,
      l: (() => { const g = document.createRange(); g.selectNodeContents(e); return new Set([...g.getClientRects()].map(x => Math.round(x.top))).size })(), droite: e.getBoundingClientRect().right > window.innerWidth }))""")
    mauvais = [x for x in r if x["coupe"] or x["droite"] or x["l"] > 2]
    assert not mauvais, f"boutons coupés ou sur trop de lignes : {mauvais}"
    p.ctx.close()


def test_mobile_fiche_de_tache_ne_deborde_pas(navigateur, srv):
    p = ouvrir(navigateur, srv, "/#t=mere", 390, 844)
    hors = p.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => e.offsetParent && !e.closest('select, option, .moteur')
      && e.getBoundingClientRect().right > 391).map(e => e.className)""")
    assert not hors, f"éléments au-delà de 390 px : {hors}"
    p.ctx.close()
