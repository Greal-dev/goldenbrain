"""Scénario téléphone (profil mobile Pixel 7) : une colonne, barre basse, cibles tactiles ≥ 44 px, tâche en plein écran
avec panneaux Conversation et Notes empilés, envoi d'un message, validation d'une décision, application installable (INV-PWA-1)."""

import re

import univers
from aides_arbre import nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

BLOC = ("\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : fait\n- **Résultat** : livrable-tel\n"
        "- **Essai** : lancer livrable-tel\n- **Situation** : \n- **Reste à faire** : \n- **Prochain pas** : \n"
        "<!-- orchestrateur:fin -->\n")


def _monde(serveur):
    univers.ecrire(serveur.vault, "Projets/C1-Tel/contexte.md", "---\ntype: contexte\ncasquette: C1-Pro\nnom: Tel\n---\n")
    univers.ecrire(serveur.vault, "Projets/C1-Tel/taches/tel-a.md", univers.tache("Tâche Téléphone"))
    univers.ecrire(serveur.vault, "Projets/C1-Tel/taches/tel-v.md",
                   univers.tache("Validation Téléphone", statut="fait", extra="session: s-tel\n") + BLOC)


def _telephone(navigateur):
    ctx = navigateur.new_context(viewport={"width": 412, "height": 839}, screen={"width": 412, "height": 915},
                                 device_scale_factor=2.625, is_mobile=True, has_touch=True)
    ctx.add_init_script("try{localStorage.setItem('gb.detail-ouvert','1')}catch(e){}")  # INV-DETAIL-1
    p = ctx.new_page()
    p.erreurs = []
    p.on("console", lambda m: p.erreurs.append(m.text) if m.type in ("error", "warning") else None)
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    return ctx, p


def test_telephone_liste_tache_message_et_decision(navigateur, serveur):
    _monde(serveur)
    ctx, page = _telephone(navigateur)
    try:
        page.goto(serveur.url + "/")
        barre = page.locator("#barre-basse")
        expect(barre).to_be_visible()
        expect(page.locator("#volet-droit")).to_be_hidden()  # une seule colonne : la liste
        expect(barre.locator("[data-tel=taches]")).to_have_attribute("aria-current", "page")

        # Cibles tactiles : boutons de la barre et lignes de l'arbre ≥ 44 px ; pas de défilement horizontal.
        for el in barre.locator("button").all() + page.locator("#arbre .ligne").all():
            assert el.bounding_box()["height"] >= 44
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Toucher le projet puis la tâche : plein écran, panneaux Conversation et Notes empilés, sans onglet.
        page.locator("#arbre .ligne", has_text="Tel").first.tap()
        expect(page.locator("#volet-gauche")).to_be_hidden()
        page.locator(".cl.t-tache", has_text="Tâche Téléphone").tap()
        expect(page.locator(".d-titre")).to_have_text("Tâche Téléphone")
        expect(page.locator(".d-onglet")).to_have_count(0)
        expect(page.locator(".volet-t-conv")).to_be_visible()
        expect(page.locator(".volet-t-notes")).to_be_attached()
        expect(page.locator(".d-rattache")).to_contain_text("Changer…")  # « Déplacer vers… » sans glisser-déposer
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Envoyer un message : le harnais factice répond.
        page.locator(".composer textarea").fill("bonjour")
        page.locator(".composer textarea").focus()
        expect(barre).to_be_hidden()  # clavier ouvert : la barre basse cède la place
        page.get_by_role("button", name="Envoyer").tap()
        expect(page.locator(".msg.agent.final")).to_contain_text("bonjour s-faux", timeout=15000)

        page.locator(".composer textarea").blur()  # clavier refermé : la barre basse revient
        expect(barre).to_be_visible()

        # Décisions par la barre basse : valider sur place.
        barre.locator("[data-tel=decisions]").tap()
        expect(barre.locator("[data-tel=decisions]")).to_have_attribute("aria-current", "page")
        carte = page.locator(".dc-validation", has=page.locator(".dc-titre", has_text=re.compile(r"^Validation Téléphone$")))
        carte.get_by_role("button", name="Valider").tap()
        expect(carte).to_have_count(0, timeout=5000)
        assert page.request.get(serveur.url + "/api/taches/tel-v").json()["statut"] != "fait"

        # Retour à la liste par la barre basse.
        barre.locator("[data-tel=taches]").tap()
        expect(page.locator("#volet-gauche")).to_be_visible()
        assert not page.erreurs, page.erreurs
    finally:
        ctx.close()


def test_application_installable_sans_cache_des_donnees(navigateur, serveur):
    ctx, page = _telephone(navigateur)
    try:
        man = page.request.get(serveur.url + "/manifest.json").json()
        assert man["display"] == "standalone" and man["start_url"] == "./#compagnon"
        for icone in man["icons"]:
            assert page.request.get(serveur.url + "/" + icone["src"]).ok
        page.goto(serveur.url + "/")
        expect(page.locator("#barre-basse")).to_be_visible()
        assert page.evaluate("navigator.serviceWorker.ready.then(r => r.active.scriptURL)").endswith("/sw.js")
        page.reload()
        expect(page.locator("#barre-basse")).to_be_visible()
        # INV-PWA-1 : seuls des fichiers statiques entrent dans le cache, jamais une réponse de l'API.
        cles = page.evaluate("caches.keys().then(ks => Promise.all(ks.map(k => caches.open(k).then(c => c.keys()))))"
                             ".then(ls => ls.flat().map(r => new URL(r.url).pathname))")
        assert cles and not [c for c in cles if c.startswith("/api/")], cles
        assert not page.erreurs, page.erreurs
    finally:
        ctx.close()
