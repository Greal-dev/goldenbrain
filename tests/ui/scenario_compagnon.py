"""Scénario « Accueil » du compagnon mobile (INV-COMPAGNON-1, INV-PWA-2), profil Pixel 7 : à décider, en cours, arbre
allégé ; stockage local absent par défaut, garde seulement une fois la case cochée (titres sans corps de fiche), perte du
poste montrée avec la date des données, puis effacement. Serveur dédié : `[distant] hors_ligne = true`."""

import re

import pytest
import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from conftest import demarrer
from playwright.sync_api import expect

SECRET = "CORPS-SECRET-COMPAGNON"
IDB = ("indexedDB.databases().then(ds => ds.some(d => d.name === 'gb-compagnon') ? new Promise(ok => {"
       " const q = indexedDB.open('gb-compagnon'); q.onsuccess = () => { const g = q.result.transaction('i').objectStore('i').get('dernier');"
       " g.onsuccess = () => { q.result.close(); ok(g.result ? JSON.stringify(g.result) : null); }; }; }) : null)")


@pytest.fixture(scope="module")
def poste(tmp_path_factory):
    yield from demarrer(tmp_path_factory.mktemp("ui-compagnon"), "\n[distant]\nhors_ligne = true\n")


def _monde(poste):
    univers.ecrire(poste.vault, "Projets/C1-Co/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: Co\n---\n")
    univers.ecrire(poste.vault, "Projets/C1-Co/taches/co-q.md",
                   univers.tache("Question Compagnon", statut="retour-humain", extra="commentaire: Faut-il publier ?\n").replace("Corps", SECRET))
    univers.ecrire(poste.vault, "Projets/C1-Co/taches/co-a.md", univers.tache("Tâche Compagnon"))
    univers.ecrire(poste.vault, "Projets/C1-Co/taches/co-v.md", univers.tache("Tâche à valider Compagnon", statut="fait", extra="session: s-co-v\n"))


def test_accueil_compagnon_et_stockage_optionnel(navigateur, poste):
    _monde(poste)
    ctx = navigateur.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        page.goto(poste.url + "/#compagnon")
        barre = page.locator("#barre-basse")
        expect(barre.locator("[data-tel=accueil]")).to_have_attribute("aria-current", "page")
        carte = page.locator(".co-carte", has_text="Question Compagnon")
        expect(carte).to_contain_text("Faut-il publier ?")
        expect(page.locator(".co-etat")).to_contain_text("Connecté")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for b in page.locator(".compagnon button:visible").all():
            assert b.bounding_box()["height"] >= 40

        # Par défaut, rien n'est garde sur l'appareil (INV-PWA-2).
        assert page.evaluate(IDB) is None

        # Case cochée : l'instantané léger est garde, sans corps de fiche.
        page.locator(".co-reglage input[type=checkbox]").check()
        garde = None
        for _ in range(50):
            garde = page.evaluate(IDB)
            if garde:
                break
            page.wait_for_timeout(100)
        assert garde and "Question Compagnon" in garde and SECRET not in garde

        # Poste injoignable : l'aperçu reste, daté ; les gestes sont désactivés.
        ctx.set_offline(True)
        page.locator(".co-etat .btn-discret").tap()
        expect(page.locator(".co-etat")).to_contain_text("Hors connexion")
        expect(page.locator(".co-carte", has_text="Question Compagnon")).to_be_disabled()
        ctx.set_offline(False)

        # Effacement à la demande.
        page.locator(".co-reglage .btn").tap()
        for _ in range(50):
            if page.evaluate(IDB) is None:
                break
            page.wait_for_timeout(100)
        assert page.evaluate(IDB) is None
        assert not erreurs, erreurs
    finally:
        ctx.close()


def test_valider_depuis_l_accueil(navigateur, poste):
    """Jalon 2 : une tâche à valider se valide depuis l'accueil, après confirmation ; seulement en ligne."""
    _monde(poste)
    ctx = navigateur.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    try:
        page.goto(poste.url + "/#compagnon")
        carte = page.locator(".compagnon li", has_text="Tâche à valider Compagnon")
        expect(carte.locator(".co-actions .btn")).to_have_count(2)
        expect(page.locator(".compagnon li", has_text="Question Compagnon").locator(".co-actions")).to_have_count(0)
        carte.locator(".co-actions .primaire").tap()
        page.locator("dialog .dlg-actions .primaire").tap()
        expect(page.locator(".co-retour-geste.ok")).to_contain_text("Validée : Tâche à valider Compagnon")
        expect(page.locator(".compagnon li", has_text="Tâche à valider Compagnon")).to_have_count(0, timeout=8000)

        # Échec visible : le serveur refuse, la décision reste et un bandeau d'erreur le dit.
        _monde(poste)
        univers.ecrire(poste.vault, "Projets/C1-Co/taches/co-w.md", univers.tache("Autre à valider", statut="fait", extra="session: s-co-w\n"))
        page.reload()
        page.route("**/api/taches/*/valider", lambda r: r.fulfill(status=500, content_type="application/json", body='{"detail":"panne"}'))
        carte = page.locator(".compagnon li", has_text="Autre à valider")
        carte.locator(".co-actions .primaire").tap()
        page.locator("dialog .dlg-actions .primaire").tap()
        expect(page.locator(".co-retour-geste.ko")).to_contain_text("panne")
        expect(page.locator(".compagnon li", has_text="Autre à valider")).to_have_count(1)
    finally:
        ctx.close()


def test_travail_epingle_et_chat(navigateur, poste):
    """Jalon 3 : seules les tâches épinglées sur l'appareil paraissent dans « Travail en cours » ; chacune ouvre son chat."""
    _monde(poste)
    ctx = navigateur.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    try:
        page.goto(poste.url + "/#travail")
        expect(page.locator(".compagnon.travail .vide")).to_contain_text("Aucune tâche épinglée")
        expect(page.locator("#barre-basse [data-tel=accueil]")).to_have_attribute("aria-current", "page")

        page.goto(poste.url + "/#compagnon")
        page.locator(".compagnon .co-ligne:has(.co-dossier)", has_text="C1").tap()   # casquette, puis projet
        page.locator(".compagnon .co-ligne:has(.co-dossier) .co-titre", has_text=re.compile(r"^Co$")).tap()
        page.locator(".compagnon .tr-ligne", has_text="Tâche Compagnon").locator(".tr-pin").tap()
        page.locator(".co-travail").tap()
        expect(page.locator(".compagnon.travail .co-liste li")).to_have_count(1)
        expect(page.locator(".compagnon.travail .co-liste")).to_contain_text("Tâche Compagnon")
        expect(page.locator(".compagnon.travail .co-liste")).not_to_contain_text("Question Compagnon")

        page.locator(".compagnon.travail .co-ligne").tap()
        expect(page.locator(".tr-tete .co-titre")).to_have_text("Tâche Compagnon")
        page.locator(".tr-saisie textarea").fill("Bonjour depuis le téléphone")
        page.locator(".tr-saisie button[type=submit]").tap()
        expect(page.locator(".tr-conv")).to_contain_text("Bonjour depuis le téléphone", timeout=8000)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Retrait : l'étoile du chat retire la tâche de la liste.
        page.locator(".tr-tete .tr-pin").tap()
        page.locator(".tr-tete .co-retour").tap()
        expect(page.locator(".compagnon.travail .vide")).to_be_visible()
    finally:
        ctx.close()
