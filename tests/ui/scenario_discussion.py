"""Mode discussion (INV-DISCUSSION-1) : tâche ouverte en 1366×768, la conversation occupe l'essentiel de l'écran.

Mesure : surface du volet de conversation (fil + saisie) rapportée à celle de la fenêtre, objectif ≥ 70 %. Chaque volet reste à un geste.
Vault temporaire, harnais factice, contextes neufs (aucune disposition mémorisée).
"""
import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer


@pytest.fixture(scope="module", params=["fr", "de", "es"])
def srv(request, tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("discussion"), f'\n[interface]\nmode = "avance"\nlangue = "{request.param}"\n'):
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/causerie.md", univers.tache("Causer avec l'agent", "en-cours"))
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/long-titre.md", univers.tache("Audit global de la cohérence des tâches, des projets et des liens du second cerveau", "en-cours"))
        yield s


def ouvrir(navigateur, srv, w=1366, h=768, avant="", tache="causerie"):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    if avant:
        ctx.add_init_script(avant)
    p = ctx.new_page()
    p.goto(srv.url + "/#t=" + tache)
    p.wait_for_selector(".composer textarea", timeout=90000)
    p.ctx = ctx
    return p


def test_la_conversation_couvre_70_pour_cent_de_l_ecran(navigateur, srv):
    p = ouvrir(navigateur, srv)
    try:
        expect(p.locator("body")).to_have_class(__import__("re").compile("discussion"))
        p.wait_for_timeout(600)
        part = p.evaluate("""() => { const r = document.querySelector('.volet-t-conv').getBoundingClientRect();
            return r.width * r.height / (innerWidth * innerHeight) }""")
        assert part >= 0.70, f"conversation = {part:.0%} de l'écran"
        barre = p.evaluate("() => document.querySelector('.b-haut').getBoundingClientRect().height")
        assert barre <= 56, f"barre haute = {barre}px"
    finally:
        p.ctx.close()


def test_menu_rail_et_tout_afficher(navigateur, srv):
    p = ouvrir(navigateur, srv)
    try:
        # menu : jamais invisible, le clic le déroule et donne accès aux écrans
        p.click("#btn-menu")
        expect(p.locator("#btn-reglages")).to_be_visible()
        p.keyboard.press("Escape")
        expect(p.locator("#btn-reglages")).to_be_hidden()
        # rail : le clic épingle l'arbre
        expect(p.locator("#rail-arbre")).to_be_visible()
        p.click("#rail-arbre")
        expect(p.locator("body")).to_have_class(__import__("re").compile("arbre-epingle"))
        # tout afficher : disposition complète, mémorisée après rechargement
        p.keyboard.press("Alt+d")
        expect(p.locator("body")).not_to_have_class(__import__("re").compile(r"\bdiscussion\b"))
        p.reload()
        p.wait_for_selector(".composer textarea", timeout=90000)
        expect(p.locator("body")).not_to_have_class(__import__("re").compile(r"\bdiscussion\b"))
    finally:
        p.ctx.close()


def test_telephone_inchange(navigateur, srv):
    p = ouvrir(navigateur, srv, 390, 844)
    try:
        expect(p.locator("body")).not_to_have_class(__import__("re").compile(r"\bdiscussion\b"))
    finally:
        p.ctx.close()


def test_titre_de_tache_non_rogne_par_le_rail_ni_recouvert_par_le_bandeau(navigateur, srv):
    """Symptôme du pilote : « Audit global… » coupé à gauche par le rail ; la bulle de premier usage recouvrait titre et début du fil."""
    p = ouvrir(navigateur, srv, tache="long-titre")
    try:
        p.wait_for_selector("[data-id=titre-tache]", timeout=30000)
        p.wait_for_timeout(500)
        m = p.evaluate("""() => { const t = document.querySelector("[data-id=titre-tache]").getBoundingClientRect(), rail = document.querySelector('#volet-gauche').getBoundingClientRect();
            const b = document.querySelector('[data-id="bulle-discussion"]')?.getBoundingClientRect();
            return { titreGauche: t.left, railDroite: rail.right, titreHaut: t.top, bulleBas: b ? b.bottom : 0, bulle: !!b }; }""")
        assert m["titreGauche"] >= m["railDroite"], m
        assert m["titreHaut"] >= m["bulleBas"], f"bandeau sur le titre : {m}"
        assert p.evaluate("localStorage.getItem('gb.disposition-vu')") == "1" or m["bulle"] is False
    finally:
        p.ctx.close()


@pytest.mark.parametrize("bouton", ["decisions", "amoi", "reglages", "guide", "graphe", "manager", "travaux"])
def test_ecran_ouvert_en_mode_discussion_rien_recouvert_ni_cassé(navigateur, srv, bouton):
    """(d) Chaque écran, tâche ouverte et mode discussion : aucune erreur, pas de débordement horizontal, barre haute à une rangée, fil non recouvert."""
    p = ouvrir(navigateur, srv)
    erreurs = []
    p.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        if not p.locator(f"#btn-{bouton}").is_visible():
            p.click("#btn-menu")
        if not p.locator(f"#btn-{bouton}").is_visible():
            pytest.skip("bouton absent de cette disposition")
        p.click(f"#btn-{bouton}")
        p.wait_for_timeout(700)
        m = p.evaluate("""() => ({ debord: document.documentElement.scrollWidth - innerWidth, barre: document.querySelector('.b-haut').getBoundingClientRect().height,
            corps: document.querySelector('#corps').getBoundingClientRect().height, bandeau: !!document.querySelector('[data-id="bulle-discussion"]') })""")
        assert not erreurs, erreurs
        assert m["debord"] <= 0, m
        if p.evaluate("document.body.classList.contains('discussion')"):
            assert m["barre"] <= 56, m  # un écran qui quitte la tâche rend la disposition complète : sa barre est alors plus haute, voulu
        assert m["corps"] > 300, m
    finally:
        p.ctx.close()


def test_intercalaires_utilisables_au_clavier_et_au_toucher(navigateur, srv):
    ctx = navigateur.new_context(viewport={"width": 1024, "height": 768}, locale="fr-FR", has_touch=True)
    p = ctx.new_page()
    p.goto(srv.url + "/#t=causerie")
    p.wait_for_selector(".composer textarea", timeout=90000)
    try:
        p.focus("#rail-arbre")
        p.keyboard.press("Enter")
        expect(p.locator("body")).to_have_class(__import__("re").compile("arbre-epingle"))
        p.tap("#rail-arbre")  # tactile : le même intercalaire replie
        expect(p.locator("body")).not_to_have_class(__import__("re").compile("arbre-epingle"))
        p.focus("#btn-menu")
        p.keyboard.press("Enter")
        expect(p.locator("#b-menu")).to_have_class(__import__("re").compile("ouvert"))
        p.keyboard.press("Escape")
        expect(p.locator("#b-menu")).not_to_have_class(__import__("re").compile("ouvert"))
        assert p.evaluate("[...document.querySelectorAll('.intercalaire, #btn-menu')].every((b) => { const r = b.getBoundingClientRect(); return r.width >= 24 && r.height >= 24; })")
    finally:
        ctx.close()
