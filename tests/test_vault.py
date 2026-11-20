"""Index, arbre, création, déplacement, promotion, verrou paperclip (INV-VAULT-2/3/4)."""

import os

import pytest

from orchestrateur import fiches
from orchestrateur.transformations import creer_projet
from orchestrateur.vault import Conflit, Invalide, NonTrouve
from conftest import ecrire, tache_md

SOUS_PROJETS = "Projets/*/*/taches/*.md"  # lot 7 : le projet promu naît dans son conteneur


def ids_par_type(noeuds, type_):
    out = []
    for n in noeuds:
        if n["type"] == type_:
            out.append(n["id"])
        out += ids_par_type(n["enfants"], type_)
    return out


def test_index_homonymes_et_exclusion(vault):
    taches, conts = vault.index()
    doublons = sorted(k for k in taches if k.startswith("doublon"))
    assert doublons[0] == "doublon" and doublons[1].startswith("doublon~")
    assert len(doublons[1]) == len("doublon~") + 4
    assert "modele" not in taches
    assert taches["doublon"].conteneur == "Projets/C2-Beta"  # ordre trié : Projets < _meta
    assert {"Projets/C1-Alpha", "Projets/Vide", "_meta"} <= set(conts)


def test_conteneurs_casquette_operation(vault):
    conts = vault.index()[1]
    assert conts["Projets/C1-Alpha"].casquette == "C1"
    assert conts["Projets/C1-Alpha"].operation == "Operation-X"
    assert conts["Projets/C1-Alpha"].titre == "Alpha"
    assert conts["Projets/C2-Beta"].casquette == "C2"
    assert conts["Projets/Sans"].casquette == "META"  # repli sur la clé des tâches
    assert conts["_meta"].casquette == "?"


def test_arbre_casquette_operation_conteneur_enfants(vault):
    noeuds = vault.arbre(toutes=False)
    c1 = next(n for n in noeuds if n["id"] == "casquette:C1")
    op = c1["enfants"][0]
    assert op["type"] == "operation" and op["titre"] == "Operation-X"
    alpha = op["enfants"][0]
    assert alpha["type"] == "conteneur" and alpha["id"] == "Projets/C1-Alpha"
    mere = alpha["enfants"][0]
    assert mere["id"] == "mere" and mere["ouvertes"] == 3
    assert mere["enfants"][0]["id"] == "enfant"
    assert mere["enfants"][0]["enfants"][0]["id"] == "petit"
    assert mere["etat_execution"] == "inactif"
    assert "fermee" not in ids_par_type(noeuds, "tache")
    assert "fermee" in ids_par_type(vault.arbre(toutes=True), "tache")
    beta = next(n for n in noeuds if n["id"] == "casquette:C2")
    assert beta["enfants"][0]["type"] == "conteneur"  # pas d'opération sans `parent`


def test_detail_et_fil_ariane(vault):
    d = vault.detail("petit")
    assert d["fil_ariane"] == ["C1", "Operation-X", "Alpha", "Mère", "Enfant"]
    assert d["parent"] == "enfant" and d["enfants"] == []
    assert d["corps"].startswith("# Petit")
    assert vault.detail("mere")["enfants"] == ["enfant"]
    with pytest.raises(NonTrouve):
        vault.detail("inconnue")


def test_creation_dans_arrivee_et_sous_parent(vault, racine):
    ident = vault.creer("Nouvelle tâche : été !", description="Détails")
    t = vault.tache(ident)
    assert t.conteneur == "_meta" and ident.endswith("-nouvelle-tache-ete")
    assert t.fm["statut"] == "a-faire" and t.fm["palier"] == "P1" and t.fm["projet"] == "_meta"
    assert "Détails" in fiches.lire(t.chemin)
    fille = vault.creer("Fille", parent="mere")
    tf = vault.tache(fille)
    assert tf.conteneur == "Projets/C1-Alpha" and tf.parent_brut == "mere"
    assert tf.fm["casquette"] == "C1"
    assert vault.creer("Fille", parent="mere") != fille
    with pytest.raises(NonTrouve):
        vault.creer("x", conteneur="../dehors")  # INV-VAULT-3
    with pytest.raises(Invalide):
        vault.creer("  ")


def test_deplacement_avec_descendance(vault, racine):
    vault.deplacer_conteneur("enfant", "Projets/C2-Beta")
    taches = vault.index()[0]
    assert taches["enfant"].conteneur == "Projets/C2-Beta"
    assert taches["petit"].conteneur == "Projets/C2-Beta"
    assert "parent" not in taches["enfant"].fm
    assert taches["petit"].parent_brut == "enfant"
    assert taches["enfant"].fm["projet"] == "C2-Beta" and taches["enfant"].fm["casquette"] == "C2"
    assert not (racine / "Projets/C1-Alpha/taches/enfant.md").exists()


def test_deplacement_refuse_si_destination_existe(vault, racine):
    ecrire(racine, "Projets/C2-Beta/taches/petit.md", tache_md(titre="Occupant"))
    avant = (racine / "Projets/C1-Alpha/taches/enfant.md").read_bytes()
    with pytest.raises(Conflit):
        vault.deplacer_conteneur("enfant", "Projets/C2-Beta")
    assert (racine / "Projets/C1-Alpha/taches/enfant.md").read_bytes() == avant
    assert "Occupant" in (racine / "Projets/C2-Beta/taches/petit.md").read_text("utf-8")


def test_deplacement_sous_parent_change_de_conteneur(vault):
    vault.deplacer_parent("x", "mere")
    t = vault.tache("x")
    assert t.conteneur == "Projets/C1-Alpha" and t.parent_brut == "mere"
    with pytest.raises(Conflit):
        vault.deplacer_parent("mere", "petit")  # cycle


def test_promotion_en_projet(vault, racine):
    vault.cfg.taches.append(SOUS_PROJETS)
    rel = creer_projet(vault, "enfant", "Nouveau Projet")
    assert rel == "Projets/C1-Alpha/Nouveau-Projet"
    ctx = fiches.frontmatter(fiches.lire(racine / rel / "contexte.md"))
    assert ctx["type"] == "contexte" and ctx["casquette"] == "C1" and ctx["nom"] == "Nouveau Projet"
    assert "parent" not in ctx and ctx["projet"] == "Nouveau-Projet"
    assert "Issu de la tâche [[enfant]]" in fiches.lire(racine / rel / "contexte.md")
    taches = vault.index()[0]
    assert taches["enfant"].conteneur == rel and taches["petit"].conteneur == rel
    assert "parent" not in taches["enfant"].fm and "parent" not in taches["petit"].fm
    with pytest.raises(Conflit):
        creer_projet(vault, "mere", "Nouveau Projet")


def test_statut_et_tags(vault, racine):
    ecrire(racine, "_meta/taches/tg.md", "---\nstatut: a-faire\ntags: [C1, a-faire]\n---\n")
    vault.poser_statut("tg", "en-cours")
    assert vault.tache("tg").fm["tags"] == ["C1", "en-cours"]
    with pytest.raises(Invalide):
        vault.poser_statut("tg", "nimporte")


def test_verrou_paperclip(vault, racine):
    texte = "---\nstatut: a-faire\npaperclip: PC-12\ntags: [a-faire]\n---\n# P\n"
    p = ecrire(racine, "_meta/taches/pc.md", texte)
    vault.poser_statut("pc", "en-cours")  # moteur : ignoré en silence
    with pytest.raises(Conflit):
        vault.poser_statut("pc", "fait", humain=True)
    vault.modifier("pc", {"statut": "bloque", "tags": ["x"], "session": "s1"})
    fm = fiches.frontmatter(p.read_text("utf-8"))
    assert fm["statut"] == "a-faire" and fm["tags"] == ["a-faire"] and fm["session"] == "s1"
    assert vault.detail("pc")["statut_verrouille"] is True


# --- durcissement (revue adversariale) ---------------------------------------------------

def photo(racine):
    return {p.relative_to(racine).as_posix(): p.read_bytes()
            for p in racine.rglob("*") if p.is_file()}


def rename_qui_echoue_au_deuxieme(monkeypatch):
    vrai, appels = os.rename, []

    def faux(a, b):
        appels.append(a)
        if len(appels) == 2:
            raise OSError("fichier verrouillé")
        vrai(a, b)

    monkeypatch.setattr(os, "rename", faux)


def test_deplacement_interrompu_restitue_l_etat_initial_octet_pour_octet(vault, racine,
                                                                         monkeypatch):
    avant = photo(racine)
    rename_qui_echoue_au_deuxieme(monkeypatch)
    with pytest.raises(Conflit):
        vault.deplacer_conteneur("mere", "Projets/C2-Beta")
    assert photo(racine) == avant


def test_modification_echouee_pendant_deplacement_restitue_tout(vault, racine, monkeypatch):
    avant = photo(racine)
    vrai, n = fiches.ecrire_atomique, []

    def ecrire_atomique(chemin, texte):
        n.append(chemin)
        if len(n) == 2:
            raise OSError("disque plein")
        vrai(chemin, texte)

    monkeypatch.setattr(fiches, "ecrire_atomique", ecrire_atomique)
    with pytest.raises(Conflit):
        vault.deplacer_conteneur("mere", "Projets/C2-Beta")
    assert photo(racine) == avant


def test_promotion_echouee_ne_laisse_pas_de_dossier(vault, racine, monkeypatch):
    avant = photo(racine)
    vault.cfg.taches.append(SOUS_PROJETS)
    rename_qui_echoue_au_deuxieme(monkeypatch)
    with pytest.raises(Conflit):
        creer_projet(vault, "mere", "Neuf")
    assert not (racine / "Projets/C1-Alpha/Neuf").exists() and photo(racine) == avant


def test_promotion_collision_verifiee_avant_de_creer_le_dossier(vault, racine):
    vault.cfg.taches.append(SOUS_PROJETS)
    ecrire(racine, "_meta/taches/petit.md", tache_md(extra="parent: mere\n", titre="Homonyme"))
    with pytest.raises(Conflit):
        creer_projet(vault, "mere", "Neuf")
    assert not (racine / "Projets/C1-Alpha/Neuf").exists()


def test_lien_hors_du_vault_ignore_sans_faire_tomber_l_index(vault, racine, tmp_path):
    dehors = tmp_path / "dehors"
    ecrire(dehors, "taches/fuite.md", tache_md(titre="Fuite"))
    lien = racine / "Projets" / "Lien"
    try:
        os.symlink(dehors, lien, target_is_directory=True)
    except OSError:
        try:
            import _winapi
            _winapi.CreateJunction(str(dehors), str(lien))
        except (ImportError, OSError):
            pytest.skip("ni lien symbolique ni jonction possible ici")
    taches, conteneurs = vault.index()
    assert "fuite" not in taches and "Projets/Lien" not in conteneurs and "mere" in taches


def test_index_garde_en_memoire_puis_perime_par_une_ecriture(vault, racine):
    vault.cfg.index_ttl_s = 60
    avant = vault.index()
    ecrire(racine, "Projets/C1-Alpha/taches/venue-d-ailleurs.md", tache_md())
    assert vault.index() is avant  # écriture externe : visible à l'expiration seulement
    nouvelle = vault.creer("Tâche neuve")
    taches, _ = vault.index()  # écriture de l'orchestrateur : index périmé aussitôt
    assert nouvelle in taches and "venue-d-ailleurs" in taches
