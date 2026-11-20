"""Lot 5 — moteur de réécriture des références (`references.py`) : règles 1 à 4 et cas pièges."""

from pathlib import Path

import pytest

from orchestrateur.references import (Existants, compter, nouveau_chemin, planifier,
                                      reecrire)

R = "C:/Users/utilisateur/Documents/Vault"
DEP = [("Projets/C1-ORION", "Casquettes/C1-F/TG/C1-ORION")]
EX = Existants(["Projets", "Projets/C1-ORION", "Projets/C1-ORION/a.md", "Projets/C1-ORION/sub",
                "Projets/C1-ORION/sub/b.md", "Projets/C1-ORION-V2", "Projets/C1-ORION-V2/a.md",
                "Projets/X", "Projets/X/n.md", "memory.md", "Casquettes", "Casquettes/C1-F"])


@pytest.fixture(autouse=True)
def maison_fictive(monkeypatch):
    """La forme `~/…` dépend du dossier personnel : on le fixe (indépendance du poste, INV-PUB-1)."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: cls("C:/Users/utilisateur")))


def r(texte, source="Projets/X/n.md", deps=DEP, ex=EX):
    avert: list[str] = []
    nouveau, occ = reecrire(texte, source, deps, R, existants=ex, avertissements=avert)
    return nouveau, occ, avert


# --- règle 1 : chemins relatifs à la racine ---------------------------------------------
def test_chemin_racine_prefixe_et_entier():
    assert r("voir Projets/C1-ORION/a.md et Projets/C1-ORION.")[0] == \
        "voir Casquettes/C1-F/TG/C1-ORION/a.md et Casquettes/C1-F/TG/C1-ORION."


def test_prefixe_partage_orion_et_orion_v2_dans_les_deux_sens():
    texte = "Projets/C1-ORION-V2/a.md | Projets/C1-ORION/a.md | Projets/C1-ORIONIS"
    assert r(texte)[0] == "Projets/C1-ORION-V2/a.md | Casquettes/C1-F/TG/C1-ORION/a.md | " \
                          "Projets/C1-ORIONIS"
    inverse = [("Projets/C1-ORION-V2", "Casquettes/C1-F/C1-ORION-V2")]
    assert r(texte, deps=inverse)[0] == ("Casquettes/C1-F/C1-ORION-V2/a.md | Projets/C1-ORION/a.md"
                                         " | Projets/C1-ORIONIS")


def test_separateurs_antislash_conserves():
    texte = 'Projets\\C1-ORION\\a.md et "Projets\\\\C1-ORION\\\\a.md"'
    assert r(texte)[0] == ('Casquettes\\C1-F\\TG\\C1-ORION\\a.md et '
                           '"Casquettes\\\\C1-F\\\\TG\\\\C1-ORION\\\\a.md"')


def test_sous_dossier_homonyme_ou_url_non_reecrit():
    texte = "Archives/Projets/C1-ORION/a.md https://x.org/Projets/C1-ORION ../Projets/C1-ORION"
    assert r(texte)[0] == texte


def test_nom_voisin_plus_long_avec_espace_signale_non_reecrit():
    deps = [("Projets/Mon Projet", "Casquettes/C1-F/Mon Projet")]
    ex = Existants(["Projets/Mon Projet", "Projets/Mon Projet 2"])
    nouveau, _, avert = r("Projets/Mon Projet 2/x et Projets/Mon Projet/y", deps=deps, ex=ex)
    assert nouveau == "Projets/Mon Projet 2/x et Casquettes/C1-F/Mon Projet/y"
    assert len(avert) == 1 and "autre dossier" in avert[0]


def test_casse_differente_signalee_non_reecrite():
    nouveau, _, avert = r("projets/c1-orion/a.md")
    assert nouveau == "projets/c1-orion/a.md" and "casse" in avert[0]


# --- règle 2 : chemins absolus -----------------------------------------------------------
def test_chemins_absolus_toutes_formes():
    texte = ('"C:\\\\Users\\\\utilisateur\\\\Documents\\\\Vault\\\\Projets\\\\C1-ORION\\\\a.md" '
             "c:/users/utilisateur/documents/vault/Projets/C1-ORION ~/Documents/Vault/Projets/C1-ORION "
             "/c/Users/utilisateur/Documents/Vault/Projets/C1-ORION D:/Autre/Projets/C1-ORION")
    assert r(texte)[0] == (
        '"C:\\\\Users\\\\utilisateur\\\\Documents\\\\Vault\\\\Casquettes\\\\C1-F\\\\TG\\\\C1-ORION'
        '\\\\a.md" c:/users/utilisateur/documents/vault/Casquettes/C1-F/TG/C1-ORION '
        "~/Documents/Vault/Casquettes/C1-F/TG/C1-ORION "
        "/c/Users/utilisateur/Documents/Vault/Casquettes/C1-F/TG/C1-ORION D:/Autre/Projets/C1-ORION")


# --- liens -------------------------------------------------------------------------------
def test_wikilink_racine_ancre_alias_et_alias_echappe():
    texte = "[[Projets/C1-ORION/a#Titre|alias]] | [[Projets/C1-ORION/a\\|t]] ![[Projets/C1-ORION/a]]"
    assert r(texte)[0] == ("[[Casquettes/C1-F/TG/C1-ORION/a#Titre|alias]] | "
                           "[[Casquettes/C1-F/TG/C1-ORION/a\\|t]] ![[Casquettes/C1-F/TG/C1-ORION/a]]")


def test_wikilink_par_nom_jamais_touche():
    texte = "[[C1-ORION]] [[a]] [[a|C1-ORION]] C1-ORION"
    assert r(texte)[0] == texte


def test_lien_markdown_espace_encode():
    deps = [("Projets/C1-ORION", "Casquettes/C1-F/Projet Alpha/C1-ORION")]
    assert r("[x](Projets/C1-ORION/a.md#t \"titre\") et Projets/C1-ORION", deps=deps)[0] == \
        "[x](Casquettes/C1-F/Projet%20Alpha/C1-ORION/a.md#t \"titre\") et " \
        "Casquettes/C1-F/Projet Alpha/C1-ORION"


def test_lien_relatif_entrant_recalcule_ancre_alias_conserves():
    texte = "[[../C1-ORION/a#h|al]] [y](../C1-ORION/a.md#s) [[./n]]"
    assert r(texte)[0] == ("[[../../Casquettes/C1-F/TG/C1-ORION/a#h|al]] "
                           "[y](../../Casquettes/C1-F/TG/C1-ORION/a.md#s) [[./n]]")


def test_lien_relatif_sortant_gagne_des_remontees():
    texte = "[[../../../memory]] [z](../../X/n.md)"
    assert r(texte, source="Projets/C1-ORION/sub/b.md")[0] == \
        "[[../../../../../memory]] [z](../../../../../Projets/X/n.md)"


def test_lien_relatif_sortant_perd_des_remontees():
    deps = [("Projets/Op/Lot/C1-Deep", "Projets/C1-Deep")]
    ex = Existants(["Projets/Op/Lot/C1-Deep/n.md", "memory.md"])
    assert r("[[../../../../memory]]", source="Projets/Op/Lot/C1-Deep/n.md", deps=deps,
             ex=ex)[0] == "[[../../memory]]"


def test_lien_interne_au_dossier_deplace_inchange():
    texte = "[[../a]] [[./b]] [x](../a.md)"
    nouveau, occ, _ = r(texte, source="Projets/C1-ORION/sub/b.md")
    assert nouveau == texte and occ == []


def test_lien_relatif_casse_laisse_tel_quel():
    texte = "[[../C1-ORION/inexistant]] [x](../C1-ORION/zz.md) [[../../../hors]]"
    assert r(texte)[0] == texte


def test_deplacement_de_fichier_note_avec_et_sans_md():
    deps = [("Projets/X/n.md", "Projets/C1-ORION/n2.md")]
    texte = "[[Projets/X/n]] [[Projets/X/n.md|a]] [x](../X/n.md)"
    assert r(texte, source="Projets/C1-ORION/a.md", deps=deps)[0] == \
        "[[Projets/C1-ORION/n2]] [[Projets/C1-ORION/n2.md|a]] [x](./n2.md)"
    assert nouveau_chemin("Projets/X/n.md", deps) == "Projets/C1-ORION/n2.md"


def test_occurrences_retournees_et_compter_hors_vault():
    _, occ, _ = r("Projets/C1-ORION/a.md")
    assert occ == [("Projets/C1-ORION", "Casquettes/C1-F/TG/C1-ORION")]
    assert compter("Projets/C1-ORION et ~/Documents/Vault/Projets/C1-ORION/x", DEP, R) == 2


# --- balayage ---------------------------------------------------------------------------
def test_planifier_bom_crlf_binaire_exclusions(tmp_path: Path):
    v = tmp_path / "v"
    for rel, octets in {
        "Projets/C1-ORION/a.md": b"# A\n",
        "Projets/X/bom.md": "\ufeffvoir [[Projets/C1-ORION/a]]\r\nfin\r\n".encode(),
        "Projets/X/bin.md": b"\xff\xfe Projets/C1-ORION \x00",
        "Projets/X/ignore.png": b"Projets/C1-ORION",
        ".obsidian/w.json": b'"Projets/C1-ORION"',
        "Archives/v.md": b"Projets/C1-ORION",
        "_meta/templates/t.md": b"Projets/C1-ORION",
        "_meta/annuaire.md": b"- [[Projets/C1-ORION/a]]\n",
    }.items():
        (v / rel).parent.mkdir(parents=True, exist_ok=True)
        (v / rel).write_bytes(octets)
    avant = {p: p.read_bytes() for p in v.rglob("*") if p.is_file()}
    avert: list[str] = []
    plan = planifier(v, DEP, ["_meta/templates/*"], avert)
    assert {p.read_bytes() for p in avant} and all(p.read_bytes() == o for p, o in avant.items())
    assert sorted(x.fichier for x in plan) == ["Projets/X/bom.md", "_meta/annuaire.md"]
    bom = next(x for x in plan if x.fichier == "Projets/X/bom.md")
    assert bom.lignes == 1
    texte = (v / "Projets/X/bom.md").read_bytes().decode("utf-8")
    nouveau = reecrire(texte, "Projets/X/bom.md", DEP, v)[0]
    assert nouveau.encode() == "\ufeffvoir [[Casquettes/C1-F/TG/C1-ORION/a]]\r\nfin\r\n".encode()
    assert any("bin.md" in a and "UTF-8" in a for a in avert)


def test_chemin_hors_racine_refuse():
    with pytest.raises(ValueError):
        reecrire("x", "Projets/x.md", [("../dehors", "Projets/y")], R)
