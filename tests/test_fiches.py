"""INV-VAULT-1 / INV-VAULT-2 : édition ligne à ligne, restitution octet pour octet, bloc fiche."""

import datetime as dt

import pytest

from orchestrateur import fiches

ORIGINAL = (
    "---\r\n"
    "type: tache   # commentaire conservé\r\n"
    "inconnue: {a: 1, b: [x, y]}\r\n"
    "statut: a-faire\r\n"
    "tags:\r\n"
    "  - C1\r\n"
    "  - a-faire\r\n"
    "zeta: 'garde'   \r\n"
    "---\r\n"
    "\r\n"
    "# Titre\r\n"
    "Texte avec\ttabulation et accents éèà.\r\n"
)


def test_restitution_octet_pour_octet_crlf_hors_cles_gerees():
    nouveau = fiches.modifier_cles(ORIGINAL, {"statut": "en-cours"})
    assert nouveau == ORIGINAL.replace("statut: a-faire\r\n", "statut: en-cours\r\n")


def test_liste_en_bloc_remplacee_sans_toucher_les_voisines():
    nouveau = fiches.modifier_cles(ORIGINAL, {"tags": ["C1", "en-cours"]})
    attendu = ORIGINAL.replace("tags:\r\n  - C1\r\n  - a-faire\r\n", "tags: [C1, en-cours]\r\n")
    assert nouveau == attendu


def test_cle_absente_ajoutee_avant_fermeture_et_cle_none_retiree():
    nouveau = fiches.modifier_cles(ORIGINAL, {"session": "abc-123", "statut": None})
    assert "statut:" not in nouveau
    assert nouveau.endswith("zeta: 'garde'   \r\nsession: abc-123\r\n---\r\n\r\n# Titre\r\n"
                            "Texte avec\ttabulation et accents éèà.\r\n")


def test_cle_non_geree_refusee():
    with pytest.raises(ValueError):
        fiches.modifier_cles(ORIGINAL, {"type": "autre"})


def test_valeurs_ambigues_citees():
    nouveau = fiches.modifier_cles("---\na: 1\n---\n", {"session": "true", "parent": "[[m]]",
                                                       "updated": dt.date(2026, 11, 12)})
    assert 'session: "true"' in nouveau
    assert 'parent: "[[m]]"' in nouveau
    assert "updated: 2026-11-12\n" in nouveau
    assert fiches.frontmatter(nouveau)["session"] == "true"


def test_fichier_sans_frontmatter_lu_et_complete():
    texte = "# Juste un titre\nrien d'autre"
    assert fiches.frontmatter(texte) == {}
    assert fiches.decouper(texte)[0] is None
    nouveau = fiches.modifier_cles(texte, {"statut": "en-cours"})
    assert nouveau == "---\nstatut: en-cours\n---\n" + texte


def test_frontmatter_illisible_garde_paperclip_et_session():
    texte = ("---\na: [b\npaperclip: X-12\nsession: \"abc-1\"\nstatut: 'en-cours'\r\n"
             "parent: [[mere]]\ncasquette: C1\nprojet: Alpha\nharnais: claude\n  - liste\n"
             "---\ncorps")
    fm = fiches.frontmatter(texte)
    assert fm["paperclip"] == "X-12" and fm["session"] == "abc-1" and fm["statut"] == "en-cours"
    assert fm["parent"] == "[[mere]]" and fm["casquette"] == "C1" and fm["projet"] == "Alpha"
    assert fm["harnais"] == "claude" and fm["a"] == "[b"


def test_marqueur_cite_dans_la_prose_n_est_pas_une_borne():
    fiche = {"fait": "x <!-- orchestrateur:fin --> y", "situation": "-->", "reste": "",
             "prochain_pas": "", "sous_taches": []}
    prose = f"---\nstatut: a\n---\n# T\n\nCiter `{fiches.DEBUT}` puis {fiches.FIN} en ligne.\n"
    une = fiches.ecrire_fiche(prose, fiche)
    assert une.startswith(prose) and "<!-- orchestrateur:fin --> y" not in une
    assert fiches.ecrire_fiche(une, fiche) == une
    assert fiches.lire_fiche(une)["fait"] == "x <! -- orchestrateur:fin -- > y"
    assert fiches.lire_fiche(une)["situation"] == "-- >"
    assert une.count(fiches.FIN) == 2  # celui de la prose + celui du bloc


def test_debut_orphelin_ajoute_un_bloc_neuf_sans_rien_effacer():
    fiche = fiches.fiche_vide() | {"fait": "un"}
    orphelin = f"# T\n\n{fiches.DEBUT}\nnotes de l'utilisateur\n"
    une = fiches.ecrire_fiche(orphelin, fiche)
    assert une.startswith(orphelin) and une.count(fiches.DEBUT) == 2
    deux = fiches.ecrire_fiche(une, fiche | {"fait": "deux"})
    assert deux.startswith(orphelin) and deux.count(fiches.DEBUT) == 2
    assert fiches.lire_fiche(deux)["fait"] == "deux"


def test_sans_rendu_lineaire_sur_espaces_massifs():
    import time
    texte = " " * 200_000 + "x"
    t0 = time.perf_counter()
    assert fiches.sans_rendu(texte) == "x"
    assert fiches.sans_rendu("a <fiche>z</fiche> ") == "a"
    assert time.perf_counter() - t0 < 1


def test_bloc_fiche_ajoute_puis_remplace_en_place():
    fiche = {"fait": "a", "resultat": "r", "essai": "e", "situation": "b", "reste": "c",
             "prochain_pas": "d", "sous_taches": [{"fait": True, "texte": "x"}, {"fait": False, "texte": "y"}]}
    une = fiches.ecrire_fiche(ORIGINAL, fiche)
    assert une.startswith(ORIGINAL)
    assert "\r\n### Sous-tâches\r\n- [x] x\r\n- [ ] y\r\n" in une
    assert fiches.lire_fiche(une) == {**fiche, "lignes": []}  # les lignes (INV-LIGNES-1) ont leur bloc
    une += "Après le bloc.\r\n"
    deux = fiches.ecrire_fiche(une, {**fiche, "situation": "nouvelle", "sous_taches": []})
    assert deux.endswith(fiches.FIN + "\r\nAprès le bloc.\r\n")
    assert deux.startswith(ORIGINAL)
    assert fiches.lire_fiche(deux)["situation"] == "nouvelle"
    assert fiches.corps_sans_fiche(deux) == "# Titre\r\nTexte avec\ttabulation et accents éèà." \
        "\r\n\r\n\r\nAprès le bloc."


def test_analyse_tolerante_du_rendu():
    rendu = "blabla\n<fiche>\nfait: x\nsous_taches:\n- [X] a\n-  [ ] faux\n- [ ] b\n</fiche>"
    f = fiches.analyser_rendu(rendu)
    assert f["fait"] == "x" and f["situation"] == "" and f["reste"] == ""
    assert f["sous_taches"] == [{"fait": True, "texte": "a"}, {"fait": False, "texte": "b"}]
    assert fiches.analyser_rendu("pas de bloc") is None


def test_resultat_et_essai_aller_retour_et_absence_visible_comme_telle():
    rendu = ("<fiche>\nstatut: terminee\nfait: x\nresultat: branche gb/a, commit abc\n"
             "essai: `python orch.py arbre` doit lister les tâches\n</fiche>")
    f = fiches.analyser_rendu(rendu)
    assert f["resultat"] == "branche gb/a, commit abc" and f["essai"].startswith("`python")
    assert fiches.lire_fiche(fiches.ecrire_fiche(ORIGINAL, f)) == f
    # Un rendu sans ces lignes les laisse vides : l'interface les affiche « non indiqué ».
    vide = fiches.analyser_rendu("<fiche>\nfait: x\n</fiche>")
    assert vide["resultat"] == "" and vide["essai"] == ""
    # Une fiche d'avant R1 (sans ces lignes) se relit sans erreur.
    ancien = ORIGINAL + fiches.DEBUT + "\n## Fiche\n- **Fait** : a\n" + fiches.FIN + "\n"
    assert fiches.lire_fiche(ancien)["resultat"] == ""


def test_ecriture_atomique_sans_residu(tmp_path):
    p = tmp_path / "t.md"
    p.write_bytes(b"ancien")
    fiches.ecrire_atomique(p, "nouveau\r\n")
    assert p.read_bytes() == b"nouveau\r\n"
    assert [x.name for x in tmp_path.iterdir()] == ["t.md"]


def test_octets_non_utf8_restitues(tmp_path):
    p = tmp_path / "t.md"
    p.write_bytes(b"---\nstatut: a\n---\n\xff\xfe latin\n")
    fiches.ecrire_atomique(p, fiches.modifier_cles(fiches.lire(p), {"statut": "b"}))
    assert p.read_bytes() == b"---\nstatut: b\n---\n\xff\xfe latin\n"
