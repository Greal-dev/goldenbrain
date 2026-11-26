"""Lecteur de fichiers (INV-LECTEUR-1) : un .md se lit rendu, un .html reste isolé (son script ne s'exécute pas), un .docx part à
l'application du poste (appel simulé : un test ne lance jamais une vraie application) ; Échap ferme, l'adresse #f= se partage."""
from urllib.parse import quote

import univers

HTML = "<html><body><p id=p>vu</p><script>document.getElementById('p').textContent='EXECUTE'; fetch('/api/taches')</script></body></html>"


def _preparer(serveur):
    univers.ecrire(serveur.vault, "Ressources/lecteur-ui/lisez.md", "---\ntitre: x\n---\n# Bonjour lecteur\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    univers.ecrire(serveur.vault, "Ressources/lecteur-ui/page.html", HTML)
    univers.ecrire(serveur.vault, "Ressources/lecteur-ui/doc.docx", "binaire")


def test_md_rendu_puis_echap(page, serveur):
    _preparer(serveur)
    page.goto(page.url_serveur + "/#f=" + quote("Ressources/lecteur-ui/lisez.md", safe=""))
    page.wait_for_selector("dialog.lecteur[open] h3:has-text('Bonjour lecteur')")
    assert page.locator("dialog.lecteur table").count() == 1
    assert page.locator("dialog.lecteur details.lec-front").count() == 1  # frontmatter replié
    page.click("[data-id=lecteur-source]")
    page.wait_for_selector("dialog.lecteur pre.lec-pre:has-text('# Bonjour lecteur')")
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.lecteur", state="detached")
    assert not page.erreurs, page.erreurs


def test_html_isole(page, serveur):
    _preparer(serveur)
    page.goto(page.url_serveur + "/#f=" + quote("Ressources/lecteur-ui/page.html", safe=""))
    cadre = page.wait_for_selector("iframe.lec-cadre")
    assert cadre.get_attribute("sandbox") == ""  # ni script, ni origine
    page.frame_locator("iframe.lec-cadre").locator("#p").wait_for()
    assert page.frame_locator("iframe.lec-cadre").locator("#p").inner_text() == "vu"  # le script du fichier ne s'est pas exécuté


def test_docx_ouvert_dans_l_application(page, serveur):
    _preparer(serveur)
    appels = []
    page.route("**/api/lecteur/ouvrir", lambda r: (appels.append(r.request.post_data), r.fulfill(json={"message": "ouvert dans Word"}))[1])
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.evaluate("import('/lecteur.js').then((m) => m.ouvrirFichier('Ressources/lecteur-ui/doc.docx'))")
    page.wait_for_selector("text=ouvert dans Word")
    assert len(appels) == 1 and "doc.docx" in appels[0]
    assert page.locator("dialog.lecteur").count() == 0  # pas de volet : l'application s'en charge
