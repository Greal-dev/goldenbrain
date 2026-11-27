"""Page « Email » (INV-MAIL-2, INV-MAIL-3, INV-MAIL-6) : Menu → Email, lecture d'un mail HTML dans son cadre isolé,
« Créer une tâche » avec « Payer » : la tâche naît du dialogue « Nouvelle tâche », le mail est rangé dans le projet
et la fiche porte l'entrée. Faux serveurs IMAP/SMTP de la boucle locale, vault temporaire, harnais factice.
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
    dlg = page.locator("dialog[open]")
    expect(dlg.locator('select[name="instruction"]')).to_have_value("payer")
    dlg.locator(".primaire").click()
    dlg = page.locator("dialog[open]")
    expect(dlg.locator('input[name="titre"]')).to_have_value("Facture électricité")
    dlg.locator('select[name="conteneur"]').select_option("Projets/C1-Alpha")
    dlg.locator(".primaire").click()
    expect(page).to_have_url(re.compile(r"#t=\d{4}-\d{2}-\d{2}-facture-electricite$"), timeout=10000)

    [fiche] = (srv.vault / "Projets" / "C1-Alpha" / "taches").glob("*-facture-electricite.md")
    mails = srv.vault / "Projets" / "C1-Alpha" / "mails"
    expect(page.locator("#volet-droit")).to_contain_text("Entrée : Projets/C1-Alpha/mails/", timeout=10000)  # l'entrée se lit dans la tâche
    expect(page.locator("#volet-droit")).to_contain_text("Instruction : Payer")
    expect(page.get_by_role("button", name="Livrables")).to_contain_text("1")  # la note est déclarée en livrable
    notes = list(mails.glob("*.md"))
    assert len(notes) == 1 and "type: mail" in notes[0].read_text(encoding="utf-8")
    assert (notes[0].with_suffix("") / "facture.pdf").read_bytes() == b"%PDF-1"
    assert f"Entrée : [[Projets/C1-Alpha/mails/{notes[0].stem}]] — Instruction : Payer" in fiche.read_text(encoding="utf-8")
    assert not erreurs, erreurs
    ctx.close()
