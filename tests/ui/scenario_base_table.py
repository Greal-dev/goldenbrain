"""Page « Base » (INV-BASES-1) : un dossier du vault en tableau — geste « Voir en tableau » de l'arbre des notes,
tri par en-tête, filtre, regroupement avec sous-totaux, somme en pied, clic de ligne qui ouvre la note, palette."""

import re

import univers
from aides_arbre import _ECRITS, nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

DOSSIER = "BasesUI/Loyers"
LOYERS = {  # nom : (montant, date, locataire, payé)
    "janvier": (800, "2026-01-05", "Durand", "true"), "fevrier": (800, "2026-02-05", "Durand", "false"),
    "mars": (650, "2026-03-05", "Martin", "true"), "avril": (650, "2026-04-05", "Martin", "true"),
    "mai": (-100, "2026-05-05", "Martin", "true"), "juin": (900, "2026-06-05", "Petit", "false"),
}


def _monde(serveur):
    _ECRITS.append(serveur.vault / "BasesUI")
    for nom, (montant, date, locataire, paye) in LOYERS.items():
        univers.ecrire(serveur.vault, f"{DOSSIER}/{nom}.md",
                       f"---\nmontant: {montant}\ndate: {date}\nlocataire: {locataire}\npaye: {paye}\n---\n# Loyer {nom}\n")


def _nombre(texte):
    return re.compile(rf"^{texte.replace(' ', r'\s')}$")


def test_base_tri_filtre_groupe_somme_et_ouverture(page, serveur):
    _monde(serveur)
    page.goto(page.url_serveur + "/")
    page.wait_for_selector(".ligne")
    page.click("#onglet-notes")
    page.click(".ligne.t-dossier >> text=BasesUI")
    rangee = page.locator(".ligne.t-dossier", has=page.locator(".titre", has_text=re.compile("^Loyers$")))
    rangee.hover()
    rangee.locator("[data-id=voir-tableau]").click()

    table = page.locator(".base-table")
    lignes = table.locator("tr.base-ligne")
    expect(lignes).to_have_count(6)
    assert page.evaluate("decodeURIComponent(location.hash)") == f"#base={DOSSIER}"
    pied = table.locator("tfoot td[data-col=montant]")
    pied.locator("select").select_option("somme")
    expect(pied.locator(".base-valeur")).to_have_text(_nombre("3 700"))

    # Tri : croissant puis décroissant ; une valeur négative se trie comme un nombre.
    table.locator("button.base-tri[data-col=montant]").click()
    expect(lignes.first.locator("th")).to_have_text("mai")
    table.locator("button.base-tri[data-col=montant]").click()
    expect(lignes.first.locator("th")).to_have_text("juin")

    # Filtre texte puis case : le pied suit les lignes gardées.
    page.fill("input[data-f='locataire:contient']", "mart")
    expect(lignes).to_have_count(3)
    expect(pied.locator(".base-valeur")).to_have_text(_nombre("1 200"))
    page.click("text=Effacer les filtres")
    expect(lignes).to_have_count(6)
    page.select_option("select[data-f='paye:est']", "non")
    expect(lignes).to_have_count(2)
    page.click("text=Effacer les filtres")
    expect(lignes).to_have_count(6)

    # Regroupement par locataire : un groupe par valeur, sous-total par groupe.
    page.select_option("[data-id=base-groupe]", "locataire")
    groupes = table.locator("tbody.base-groupe")
    expect(groupes).to_have_count(3)
    durand = groupes.filter(has=page.locator(".base-groupe-titre", has_text="Durand"))
    expect(durand.locator("tr.base-sous-total td[data-col=montant]")).to_have_text(_nombre("1 600"))
    martin = groupes.filter(has=page.locator(".base-groupe-titre", has_text="Martin"))
    expect(martin.locator("tr.base-sous-total td[data-col=montant]")).to_have_text(_nombre("1 200"))

    # Clic sur une ligne : la note s'ouvre.
    martin.locator("tr.base-ligne", has=page.locator("th", has_text="mars")).click()
    expect(page.locator(".vue-note .d-titre")).to_have_text("Loyer mars")

    # Palette : la base récente se rouvre, ses réglages retenus (groupe).
    page.keyboard.press("Control+k")
    page.keyboard.type("base")
    page.locator("dialog#palette [data-id=palette-commande]", has_text=f"Base : {DOSSIER}").click()
    expect(table.locator("tbody.base-groupe")).to_have_count(3)
    expect(page.locator("[data-id=base-groupe]")).to_have_value("locataire")
    assert not page.erreurs, page.erreurs
