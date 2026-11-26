"""« À moi » en trois pastilles (INV-MAIN-4, INV-MAIN-6, INV-MAIN-7) : À valider, Questions, À faire par vous ;
validation en lot (cases, « Valider la sélection », annulation), survol = résultat ; les « jamais lancées » de l'IA
et les permanentes ne comptent pas. Vault temporaire, harnais factice.
"""
import pytest

import univers
from conftest import demarrer


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("a_moi"), '\n[interface]\nmode = "avance"\n'):
        for i, nom in enumerate(("Alpha", "Beta")):
            univers.ecrire(s.vault, f"Projets/C1-Alpha/taches/livre-{i}.md",
                           univers.tache(f"Livrée {nom}", "fait", f"session: s{i}\n"))
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/avocat.md", univers.tache("Appeler l'avocat pour le bail", "a-faire"))
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/veille.md", univers.tache("Intégrer les branches", "a-faire", "nature: permanente\n"))
        yield s


def ouvrir(navigateur, srv):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition-vu','1')}catch(e){}")
    p = ctx.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.goto(srv.url + "/")
    p.wait_for_selector("#bandeau .b-haut", state="visible", timeout=90000)
    p.wait_for_selector("#volet-gauche .ligne", timeout=90000)
    p.wait_for_timeout(500)
    return p


def test_trois_pastilles_comptent_sans_les_permanentes_ni_les_jamais_lancees(navigateur, srv):
    p = ouvrir(navigateur, srv)
    assert p.inner_text("#n-avalider").strip() == "2"
    assert p.inner_text("#n-afaire").strip() == "1"  # l'avocat ; la permanente est en veille
    assert p.inner_text("#n-questions").strip() == "0"
    assert not p.erreurs, p.erreurs


def test_validation_en_lot_puis_annulation(navigateur, srv):
    p = ouvrir(navigateur, srv)
    p.click("#btn-avalider")
    p.wait_for_selector("#panneau-avalider .ap-case", timeout=10000)
    assert p.is_disabled("#panneau-avalider [data-id=valider-selection]")
    p.check("#panneau-avalider .ap-case >> nth=0")
    p.check("#panneau-avalider .ap-case >> nth=1")
    p.click("#panneau-avalider [data-id=valider-selection]")
    p.wait_for_function("() => document.querySelector('#n-avalider').textContent.trim() === '0'", timeout=10000)
    p.wait_for_selector("#panneau-avalider [data-id=valider-annuler]", state="visible", timeout=10000)  # le panneau reste ouvert, il dit le lot
    p.click("#panneau-avalider [data-id=valider-annuler]")
    p.wait_for_function("() => document.querySelector('#n-avalider').textContent.trim() === '2'", timeout=10000)
    assert not p.erreurs, p.erreurs
