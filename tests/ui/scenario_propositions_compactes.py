"""Propositions compactes (INV-PROP-2) : six propositions en attente venues de deux tâches tiennent, repliées, en deux lignes de groupe
(≤ 2 × 32 px) et, dépliées, une ligne de ≤ 32 px chacune, dans le panneau déroulant « Propositions » (l'accueil n'en a plus, INV-DEROULANT-1) et la page Décisions.
Accepter ou refuser se fait d'un clic d'icône, ou pour tout le groupe ; le motif se lit au dépli ou au survol.
Les hauteurs s'impriment ; `GB_PLANCHE=<dossier>` y dépose les captures, `GB_AVANT=1` mesure sans exiger le budget (état antérieur).
Vault temporaire, harnais factice.
"""
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer

H = {"X-Orchestrateur": "1"}
AVANT = os.environ.get("GB_AVANT") == "1"
SORTIE = Path(os.environ["GB_PLANCHE"]) if os.environ.get("GB_PLANCHE") else None
LIGNE, GROUPE = 32, 2 * 32 + 4  # px ; 4 px de filets


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("props"), '\n[interface]\nmode = "avance"\nlangue = "fr"\n'):
        univers.ecrire(s.vault, "Projets/C1-Alpha/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\n---\n")
        for n, titre in (("p-a", "Préparer la réponse au dossier de consultation"), ("p-b", "Revue de cohérence du projet Alpha"),
                         ("p-c", "Mettre à jour le site de l'atelier"), ("p-d", "Relancer le fournisseur de matériaux")):
            univers.ecrire(s.vault, f"Projets/C1-Alpha/taches/{n}.md", univers.tache(titre))
        props = [("p-a", "perimetre", "p-c", "Limiter la mise à jour aux pages d'accueil et de contact, le reste attendra la prochaine version"),
                 ("p-a", "projet", "p-d", "Approvisionnement de l'atelier"),
                 ("p-a", "operation", "p-c", "Atelier 2027"),
                 ("p-b", "perimetre", "p-d", "Ne relancer que pour les commandes en retard de plus de quinze jours"),
                 ("p-b", "fermer", "p-c", "abandonne"),
                 ("p-b", "operation", "p-d", "Fournisseurs et achats")]
        import httpx
        for de, typ, tache, val in props:
            r = httpx.post(s.url + "/api/propositions", headers=H, json={"type": typ, "tache": tache, "valeur": val, "de": de,
                                                                         "motif": f"Motif de {typ} : le détail se lit au dépli."})
            assert r.is_success and r.json()["etat"] == "en_attente", r.text
        yield s


def ctx(navigateur, w=1366, h=860):
    c = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    p = c.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    return c, p


def hauteur(p, sel):
    return p.evaluate(f"() => {{ const e = document.querySelector({sel!r}); return e ? e.getBoundingClientRect().height : -1 }}")


def lignes(p, sel):
    return p.evaluate(f"() => [...document.querySelectorAll({sel!r})].map((e) => e.getBoundingClientRect().height)")


def cliche(p, nom):
    if SORTIE:
        SORTIE.mkdir(parents=True, exist_ok=True)
        p.mouse.move(1, 1)
        p.wait_for_timeout(300)
        p.screenshot(path=str(SORTIE / f"propositions-{'avant' if AVANT else 'apres'}-{nom}.png"))


def verifier(nom, replie, deplie):
    print(f"\nPROPOSITIONS {nom} : repliées {replie:.0f} px ; dépliées {[round(x) for x in deplie]}")
    if AVANT:
        return
    assert 0 < replie <= GROUPE, f"{nom} : {replie:.0f} px repliées (budget {GROUPE})"
    assert len(deplie) >= 4 and max(deplie) <= LIGNE, f"{nom} : lignes dépliées {deplie}"


def test_panneau_des_propositions(navigateur, srv):
    c, p = ctx(navigateur)
    p.goto(srv.url + "/")
    expect(p.locator("#n-props")).to_have_text("6")
    p.click("#btn-props")
    expect(p.locator("#panneau-props")).to_be_visible()
    p.wait_for_timeout(300)
    replie = hauteur(p, "#panneau-props .props")
    cliche(p, "panneau-replie")
    p.evaluate("() => document.querySelectorAll('#panneau-props details.prop-groupe').forEach((d) => { d.open = true })")
    p.wait_for_timeout(200)
    cliche(p, "panneau-deplie")
    verifier("panneau", replie, lignes(p, "#panneau-props .prop"))
    if not AVANT:
        g = p.locator("#panneau-props details.prop-groupe").first
        expect(g).to_contain_text("Propositions de")
        g.locator(".prop").first.locator("[data-refuser]").click()
        expect(p.locator("#n-props")).to_have_text("5")
    assert not p.erreurs, p.erreurs
    c.close()


def test_accueil_et_decisions(navigateur, srv):
    c, p = ctx(navigateur)
    p.goto(srv.url + "/")
    expect(p.locator("#n-props")).not_to_have_text("0")  # le test du panneau en a refusé une
    if not AVANT:  # INV-DEROULANT-1 : plus de zone permanente des propositions sur l'accueil, la pastille seule
        expect(p.locator(".casc-props")).to_have_count(0)
    p.goto(srv.url + "/#decisions")
    expect(p.locator(".dc-proposition").first).to_be_visible(timeout=20000)
    p.wait_for_timeout(300)
    replie = p.evaluate("() => [...document.querySelectorAll('.dc-proposition')].reduce((s, e) => s + e.getBoundingClientRect().height, 0)")
    cliche(p, "decisions-replie")
    p.evaluate("() => document.querySelectorAll('.dc-proposition details.prop-groupe').forEach((d) => { d.open = true })")
    p.wait_for_timeout(200)
    cliche(p, "decisions-deplie")
    verifier("decisions", replie, lignes(p, ".dc-proposition li.dc-prop"))
    if not AVANT:
        lot = p.locator(".dc-proposition").first
        expect(lot.locator("li.dc-prop").first).to_have_attribute("title", re.compile(r"^Motif de \w+ : le détail se lit au dépli\.$"))
        lot.get_by_role("button", name="Tout refuser").click()
        expect(p.locator(".dc-proposition")).to_have_count(1, timeout=5000)
    assert not p.erreurs, p.erreurs
    c.close()
