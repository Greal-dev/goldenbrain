"""Proposition « rattacher » : lot sous un parent, détachement, garde-fous (INV-RATTACHER-1)."""

import pytest
from conftest import ecrire, tache_md

from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Invalide

ALPHA = "Projets/C1-Alpha/taches/"


def _m(config, vault, faux, racine, **taches):
    for nom, (titre, extra) in taches.items():
        ecrire(racine, f"{ALPHA}{nom}.md", tache_md(titre=titre, extra=extra))
    vault._index = None
    return Moteur(config, vault, {"faux": faux})


def _parent(vault, ident):
    return vault.tache(ident).parent_brut


def test_lot_en_une_proposition_puis_detachement(config, vault, faux, racine):
    m = _m(config, vault, faux, racine, groupe=("Développement", ""), a=("Corriger le code", ""), b=("Ajouter la branche", ""))
    p = m.proposer("rattacher", "a", "groupe", motif="ranger", annexe={"taches": ["b"]})
    assert p["taches"] == ["a", "b"] and len(m.propositions.liste) == 1
    assert _parent(vault, "a") is None  # rien n'est écrit avant le geste humain (INV-EXEC-5)
    m.trancher(p["n"], True)
    assert _parent(vault, "a") == "groupe" and _parent(vault, "b") == "groupe"
    m.trancher(m.proposer("rattacher", "a", "racine", annexe={"taches": ["b"]})["n"], True)
    assert _parent(vault, "a") is None and _parent(vault, "b") is None


def test_cycle_refuse_a_la_proposition_et_a_l_acceptation(config, vault, faux, racine):
    m = _m(config, vault, faux, racine)
    with pytest.raises(Conflit, match="cycle"):
        m.proposer("rattacher", "mere", "petit")  # petit descend de mère
    with pytest.raises(Conflit, match="cycle"):
        m.proposer("rattacher", "mere", "mere")
    # l'arbre bouge entre la proposition et l'acceptation : refus, rien d'écrit, proposition en attente
    ecrire(racine, ALPHA + "x.md", tache_md(titre="X"))
    ecrire(racine, ALPHA + "y.md", tache_md(titre="Y"))
    vault._index = None
    p = m.proposer("rattacher", "x", "y")
    vault.modifier("y", {"parent": "x"})
    with pytest.raises(Conflit, match="cycle"):
        m.trancher(p["n"], True)
    assert m.propositions.get(p["n"])["etat"] == "en_attente" and _parent(vault, "x") is None


def test_tache_en_cours_d_execution_refusee(config, vault, faux, racine):
    m = _m(config, vault, faux, racine, g=("Groupe", ""), a=("Travail", ""))
    m.occupation = lambda i: {"tache": i} if i == "a" else None
    with pytest.raises(Conflit, match="exécution"):
        m.proposer("rattacher", "a", "g")


def test_parent_d_un_autre_projet_refuse(config, vault, faux, racine):
    m = _m(config, vault, faux, racine, a=("Travail", ""))
    with pytest.raises(Conflit, match="autre projet"):
        m.proposer("rattacher", "a", "doublon")


def test_plafond_de_dix_par_parent(config, vault, faux, racine):
    noms = {f"t{i}": (f"Tâche {i}", "") for i in range(11)}
    m = _m(config, vault, faux, racine, g=("Groupe", ""), **noms)
    with pytest.raises(Conflit, match="10"):
        m.proposer("rattacher", "t0", "g", annexe={"taches": [f"t{i}" for i in range(1, 11)]})
    m.trancher(m.proposer("rattacher", "t0", "g", annexe={"taches": [f"t{i}" for i in range(1, 10)]})["n"], True)
    with pytest.raises(Conflit, match="10"):
        m.proposer("rattacher", "t10", "g")


def test_natures_non_melangees(config, vault, faux, racine):
    m = _m(config, vault, faux, racine, g=("Groupe", ""), a=("Corriger le code", "genre: developpement\n"),
           b=("Relancer le mail", "genre: operation\n"))
    with pytest.raises(Conflit, match="natures"):
        m.proposer("rattacher", "a", "g", annexe={"taches": ["b"]})
    m.trancher(m.proposer("rattacher", "a", "g")["n"], True)


def test_valeur_et_tache_inconnues(config, vault, faux, racine):
    m = _m(config, vault, faux, racine)
    with pytest.raises(Exception):
        m.proposer("rattacher", "mere", "inexistante")
    with pytest.raises(Invalide):
        m.proposer("rattacher", "mere", "  ")

