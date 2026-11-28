"""Page « Email » (INV-MAIL-2, INV-MAIL-3, INV-MAIL-6, INV-MAIL-8) : Menu → Email, lecture d'un mail HTML dans son cadre isolé,
« Créer une tâche » avec « Payer » : la tâche naît du dialogue « Nouvelle tâche », le mail est rangé dans le projet
et la fiche porte l'entrée. Onglet « Mails » du volet : liste, masquer / annuler, créer et associer depuis la ligne. Faux serveurs IMAP/SMTP de la boucle locale, vault temporaire, harnais factice.
"""

import re

import pytest
from playwright.sync_api import expect

from conftest import demarrer
from faux_mail import ADRESSE, MDP, FauxMail, message


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    faux = FauxMail()
    faux.ajouter("INBOX", message("Rendez-vous chantier", texte="Mardi 9 h."))
    faux.ajouter("INBOX", message("Facture électricité", html="<p>Montant <b>120 EUR</b></p><script>parent.x=1</script>",
                                  piece=("facture.pdf", b"%PDF-1"), jours=1))
    dossier = tmp_path_factory.mktemp("mail")
    (dossier / "etat").mkdir()
    (dossier / "etat" / "messagerie.mdp").write_text(MDP, encoding="utf-8")
    reglage = f'\n[messagerie]\nadresse = "{ADRESSE}"\nimap = "{faux.imap}"\nsmtp = "{faux.smtp}"\ntls = false\ndelai_s = 10\n'
    try:
        for s in demarrer(dossier, reglage):
            s.faux = faux
            yield s
    finally:
        faux.arreter()


def test_lire_un_mail_et_en_faire_une_tache_a_payer(navigateur, srv):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.detail-ouvert','1');localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")
    page = ctx.new_page()
    erreurs = []
    page.on("console", lambda m: erreurs.append(m.text) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(srv.url + "/")
    page.wait_for_selector("#arbre .ligne")
    if page.locator("#btn-menu").is_visible():  # barre fine : les écrans sont dans « Menu » (INV-DISCUSSION-1)
        page.click("#btn-menu")
    page.click("#btn-mail")
    expect(page).to_have_url(srv.url + "/#mail")
    lignes = page.locator('[data-id="mail-ligne"]')
    expect(lignes).to_have_count(2)
    expect(lignes.first).to_contain_text("Facture électricité")  # le plus récent d'abord
    lignes.first.click()
    expect(page.locator('[data-id="mail-objet"]')).to_have_text("Facture électricité")
    cadre = page.locator('[data-id="mail-cadre"]')
    expect(cadre).to_have_attribute("sandbox", "allow-popups allow-popups-to-escape-sandbox")  # INV-MAIL-3 : ni script ni origine
    expect(page.frame_locator('[data-id="mail-cadre"]').locator("b")).to_have_text("120 EUR")
    assert page.evaluate("window.x") is None  # le script du mail n'a rien touché
    expect(page.locator('[data-id="mail-pieces"]')).to_contain_text("facture.pdf")

    page.click('[data-id="mail-creer-tache"]')
    dlg = page.locator("dialog[open]")  # un seul dialogue : « Nouvelle tâche », prérempli, avec le rappel du mail joint
    expect(page.locator("dialog[open]")).to_have_count(1)
    expect(dlg.locator('input[name="titre"]')).to_have_value("Facture électricité")
    expect(dlg.locator('textarea[name="description"]')).to_have_value("Traiter le mail joint.")
    expect(dlg.locator('select[name="instruction"]')).to_have_count(0)
    expect(dlg.locator(".dlg-texte")).to_contain_text("Facture électricité")
    dlg.locator('textarea[name="description"]').fill("Payer la facture avant vendredi.")
    dlg.locator('select[name="conteneur"]').select_option("Projets/C1-Alpha")
    dlg.locator(".primaire").click()
    expect(page).to_have_url(re.compile(r"#t=\d{4}-\d{2}-\d{2}-facture-electricite$"), timeout=10000)

    [fiche] = (srv.vault / "Projets" / "C1-Alpha" / "taches").glob("*-facture-electricite.md")
    mails = srv.vault / "Projets" / "C1-Alpha" / "mails"
    expect(page.locator("#volet-droit")).to_contain_text("Entrée : Projets/C1-Alpha/mails/", timeout=10000)  # l'entrée se lit dans la tâche
    expect(page.locator("#volet-droit")).to_contain_text("Instruction : Payer la facture avant vendredi.")
    expect(page.get_by_role("button", name="Livrables")).to_contain_text("1")  # la note est déclarée en livrable
    notes = list(mails.glob("*.md"))
    assert len(notes) == 1 and "type: mail" in notes[0].read_text(encoding="utf-8")
    assert (notes[0].with_suffix("") / "facture.pdf").read_bytes() == b"%PDF-1"
    assert f"Entrée : [[Projets/C1-Alpha/mails/{notes[0].stem}]] — Instruction : Payer" in fiche.read_text(encoding="utf-8")
    assert not erreurs, erreurs
    ctx.close()


def _page(navigateur, srv):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.detail-ouvert','1');localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")
    page = ctx.new_page()
    erreurs = []
    page.on("console", lambda m: erreurs.append(m.text) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(srv.url + "/")
    page.wait_for_selector("#arbre .ligne")
    return ctx, page, erreurs


def test_onglet_mails_liste_masquer_annuler_et_ouvrir(navigateur, srv):
    ctx, page, erreurs = _page(navigateur, srv)
    expect(page.locator("#onglet-mails")).to_be_visible()
    page.click("#onglet-mails")
    lignes = page.locator('[data-id="volet-mail-ligne"]')
    expect(lignes).to_have_count(2)
    expect(lignes.first).to_contain_text("Facture électricité")
    assert page.evaluate("localStorage.getItem('orch.onglet')") == "mails"  # mémorisé comme Tâches et Notes
    assert page.evaluate("getComputedStyle(document.querySelector('.mail-ligne.non-lu .mail-objet')).fontWeight") in ("700", "bold")
    page.reload()  # l'onglet choisi revient au rechargement
    expect(page.locator('[data-id="volet-mail-ligne"]')).to_have_count(2)

    page.locator('[data-id="volet-mail-ligne"]', has_text="Rendez-vous chantier").hover()
    page.locator('.mail-item:has-text("Rendez-vous chantier") [data-id="mail-ligne-masquer"]').click()  # un clic, sans confirmation
    expect(page.locator('[data-id="volet-mail-ligne"]')).to_have_count(1)
    assert len(srv.faux.boites["INBOX"]) == 1 and len(srv.faux.boites["[Gmail]/Tous les messages"]) == 1  # masqué, pas supprimé
    expect(page.locator("#banniere")).to_contain_text("Mail masqué")
    page.click('[data-id="banniere-action"]')
    expect(page.locator('[data-id="volet-mail-ligne"]')).to_have_count(2)
    assert len(srv.faux.boites["INBOX"]) == 2

    page.locator('[data-id="volet-mail-ligne"]', has_text="Rendez-vous chantier").click()
    expect(page).to_have_url(srv.url + "/#mail")
    expect(page.locator('[data-id="mail-objet"]')).to_have_text("Rendez-vous chantier")
    page.click('[data-id="mail-archiver"]')  # même geste depuis l'en-tête du mail ouvert
    expect(page.locator('[data-id="mail-objet"]')).to_have_count(0)
    expect(page.locator('[data-id="mail-ligne"]')).to_have_count(1)
    page.click('[data-id="banniere-action"]')
    expect(page.locator('[data-id="mail-ligne"]')).to_have_count(2)
    assert not erreurs, erreurs
    ctx.close()


def test_creer_et_associer_une_tache_depuis_la_ligne(navigateur, srv):
    ctx, page, erreurs = _page(navigateur, srv)
    page.click("#onglet-mails")
    page.locator('[data-id="volet-mail-ligne"]', has_text="Rendez-vous chantier").hover()
    page.locator('.mail-item:has-text("Rendez-vous chantier") [data-id="mail-ligne-associer"]').click()
    dlg = page.locator("dialog[open]")
    expect(dlg.locator('input[name="lancer"]')).to_be_checked()  # lancer l'agent tout de suite : coché d'emblée
    dlg.locator('input[name="lancer"]').uncheck()
    dlg.locator('select[name="tache"]').select_option(label="Facture électricité")
    dlg.locator('textarea[name="consigne"]').fill("Investiguer le devis")
    dlg.locator(".primaire").click()
    [fiche] = (srv.vault / "Projets" / "C1-Alpha" / "taches").glob("*-facture-electricite.md")
    for _ in range(40):
        if "Instruction : Investiguer le devis" in fiche.read_text(encoding="utf-8"):
            break
        page.wait_for_timeout(250)
    assert "Instruction : Investiguer le devis" in fiche.read_text(encoding="utf-8")

    page.locator('[data-id="volet-mail-ligne"]', has_text="Rendez-vous chantier").hover()
    page.locator('.mail-item:has-text("Rendez-vous chantier") [data-id="mail-ligne-creer"]').click()
    expect(page.locator('dialog[open] input[name="titre"]')).to_have_value("Rendez-vous chantier")  # directement « Nouvelle tâche »
    assert not erreurs, erreurs
    ctx.close()
