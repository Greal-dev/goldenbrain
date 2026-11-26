"""Accueil sur une rangée (demande du 26/11) : sans tâche ouverte, la barre haute tient en UNE rangée (les gestes secondaires dans
« Menu », « En cours » en pastille), aucune rangée « En direct » en doublon, le filtre de statut partage la ligne du titre, et la
première ligne du tableau commence dans le premier quart de la fenêtre. Vault temporaire chargé (260 tâches), harnais factice.
"""
import os

import pytest

import charge
from conftest import demarrer

MESURE = """() => {
  const h = (s) => { const e = document.querySelector(s); return e && e.offsetParent !== null ? e.getBoundingClientRect() : null; };
  const barre = h('#bandeau'), l1 = h('.casc-l1'), statut = h('#btn-statuts'), titre = h('.casc-titre'), ligne = h('.casc-corps .cl');
  return { barre: Math.round(barre.height), fine: document.body.classList.contains('barre-fine'),
           direct: !!h('.casc-live'), bas: !!h('.b-bas'), travaux: !!h('.b-haut #btn-travaux'),
           memeLigne: !!statut && !!titre && Math.abs((statut.top + statut.height / 2) - (titre.top + titre.height / 2)) < 14,
           premiere: ligne ? Math.round(ligne.top) : -1, fenetre: innerHeight,
           deborde: document.documentElement.scrollWidth - innerWidth };
}"""


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("accueil"), '\n[interface]\nmode = "avance"\n', avant=charge.peupler):
        yield s


@pytest.mark.parametrize("largeur", [1366, 1280, 1024])
def test_accueil_sans_tache_la_barre_tient_en_une_rangee_et_le_tableau_commence_haut(navigateur, srv, largeur):
    ctx = navigateur.new_context(viewport={"width": largeur, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition-vu','1')}catch(e){}")
    p = ctx.new_page()
    p.goto(srv.url + "/")
    p.wait_for_selector(".casc-corps .cl", timeout=90000)
    p.wait_for_timeout(600)
    m = p.evaluate(MESURE)
    if os.environ.get("GB_CAPTURES"):
        p.screenshot(path=os.path.join(os.environ["GB_CAPTURES"], f"accueil-{largeur}.png"))
    ctx.close()
    assert m["fine"] and not m["bas"] and m["travaux"], m
    assert m["barre"] <= 48, f"barre haute de {m['barre']} px : plus d'une rangée ({m})"
    assert not m["direct"], f"rangée « En direct » en doublon de la pastille « En cours » ({m})"
    assert m["memeLigne"], f"le filtre de statut n'est pas sur la ligne du titre ({m})"
    assert 0 < m["premiere"] <= 0.25 * m["fenetre"], f"première ligne à {m['premiere']} px, au-delà du quart de la fenêtre ({m})"
    assert m["deborde"] <= 0, m


TITRE_LONG = "Audit global de l'application : ambition, bugs, fonctionnalités imparfaites, ergonomie"  # 86 caractères


def test_fiche_ouverte_le_titre_long_reste_lisible_dans_l_en_tete(navigateur, srv):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition-vu','1')}catch(e){}")
    p = ctx.new_page()
    p.goto(srv.url + "/")
    p.wait_for_selector(".casc-corps .cl", timeout=90000)
    p.get_by_text("Tâche de charge 0", exact=True).first.click()
    p.wait_for_selector(".d-une .d-titre", timeout=30000)
    p.wait_for_timeout(500)
    m = p.evaluate("""(titre) => { const e = document.querySelector('.d-une .d-titre'); e.textContent = titre;
        const l = document.querySelector('.d-une').getBoundingClientRect();
        const dedans = [...document.querySelectorAll('.d-une > *')].every((x) => x.offsetParent === null || x.getBoundingClientRect().right <= l.right + 0.5);
        return { visible: e.clientWidth, entier: e.scrollWidth, ligne: Math.round(l.width), haut: Math.round(l.height), dedans }; }""", TITRE_LONG)
    if os.environ.get("GB_CAPTURES"):
        p.screenshot(path=os.path.join(os.environ["GB_CAPTURES"], "fiche-titre-long.png"))
    ctx.close()
    assert m["visible"] >= 0.45 * m["ligne"], f"le titre n'a que {m['visible']} px sur une ligne de {m['ligne']} ({m})"
    assert m["visible"] >= 0.9 * m["entier"], f"titre de 86 caractères rogné : {m['visible']} px visibles sur {m['entier']} ({m})"
    assert m["haut"] <= 44 and m["dedans"], f"l'en-tête ne tient plus sur une ligne dans la fenêtre ({m})"
