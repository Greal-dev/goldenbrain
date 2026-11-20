"""Recherche : sans casse ni accents, tous les mots, titre / fiche / fil d'Ariane, ouvertes d'abord."""

from orchestrateur import fiches, recherche
from conftest import ecrire, tache_md


def ids(vault, q, limite=20):
    return [r["id"] for r in recherche.chercher(vault, q, limite)]


def test_accents_et_casse(vault):
    # Le titre « Mère » figure aussi au fil d'Ariane de ses descendantes ; titre d'abord.
    assert ids(vault, "MERE") == ["mere", "enfant", "petit"]
    assert ids(vault, "fermée") == ids(vault, "FERMEE") == ["fermee"]


def test_plusieurs_mots_titre_et_fil_ariane(vault):
    # « alpha » vient du fil d'Ariane (conteneur), « petit » du titre.
    assert ids(vault, "alpha petit") == ["petit"]
    assert set(ids(vault, "operation-x")) == {"mere", "enfant", "petit"}
    assert ids(vault, "alpha introuvable") == [] and ids(vault, "   ") == []


def test_fiche_cherchee_et_extrait(vault):
    fiche = {**fiches.fiche_vide(), "situation": "Attente du devis de l'électricien"}
    vault.modifier("x", {}, fiche)
    r = recherche.chercher(vault, "electricien")
    assert [x["id"] for x in r] == ["x"]
    assert r[0]["extrait"] == "Attente du devis de l'électricien"
    assert set(r[0]) == {"id", "titre", "statut", "fil_ariane", "extrait", "echeance", "priorite",
                         "retard"}


def test_ouvertes_d_abord_et_limite(vault, racine):
    ecrire(racine, "_meta/taches/zzz.md", tache_md(statut="cloture", titre="Doublon ancien"))
    assert ids(vault, "doublon")[-1] == "zzz"
    assert len(ids(vault, "doublon", limite=1)) == 1


def test_sans_relecture_des_fichiers(vault, monkeypatch):
    # Index relu (ttl 0) mais fichiers inchangés : le cache par date de modification suffit.
    vault.index()
    monkeypatch.setattr(fiches, "lire", lambda p: (_ for _ in ()).throw(AssertionError(p)))
    assert ids(vault, "mere")[0] == "mere"
