"""Gestes de routine appliqués d'office, tracés et annulables ; reste à faire en ligne (INV-PROP-1, INV-LIGNES-1)."""

import pytest

from orchestrateur import decisions, fiches, liens
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit

MOTIF = "Une description de quatre mots."


def _m(config, vault, faux):
    return Moteur(config, vault, {"faux": faux})


def test_proposition_de_routine_ne_surcharge_plus_decisions_appliquee_d_office_et_tracee(config, vault, faux):
    # Symptôme (24/11) : chaque lien ou déplacement proposé attendait un clic dans Décisions.
    m = _m(config, vault, faux)
    p = m.proposer("lier", "mere", "alimente:x", de="mere", motif="x dépend de mere")
    assert p["etat"] == "acceptee" and p["auto"] is True
    assert [r["id"] for r in liens.refs(vault.index()[0], "x")["alimente_par"]] == ["mere"]
    assert not [d for d in decisions.rassembler(m)["decisions"] if d["genre"] == "proposition"]
    assert [o["n"] for o in decisions.rassembler(m)["office"]] == [p["n"]]
    assert "lier alimente:x" in fiches.lire(vault.tache("mere").chemin)


@pytest.mark.parametrize("type_,tache,valeur", [
    ("lier", "mere", "alimente:x"),
    ("renommer", "x", "Titre tout neuf"),
    ("echeance", "mere", "2030-01-01"),
    ("deplacer", "x", "Projets/C2-Beta"),
    ("ticket", "mere", "Sous-ticket neuf"),
])
def test_geste_d_office_annulable_depuis_le_journal(config, vault, faux, type_, tache, valeur):
    m = _m(config, vault, faux)
    avant = vault.tache(tache)
    titre, conteneur, echeance = avant.titre, avant.conteneur, avant.fm.get("echeance")
    p = m.proposer(type_, tache, valeur, motif=MOTIF)
    assert p["etat"] == "acceptee" and p["auto"] is True
    assert m.annuler(p["n"])["etat"] == "annulee"
    apres = vault.tache(tache)
    assert (apres.titre, apres.conteneur, apres.fm.get("echeance")) == (titre, conteneur, echeance)
    assert not liens.refs(vault.index()[0], "x")["alimente_par"]
    assert not [t for t in vault.index()[0].values() if t.titre == "Sous-ticket neuf" and t.statut != "abandonne"]
    assert "annulé" in fiches.lire(vault.tache(tache).chemin)
    with pytest.raises(Conflit):
        m.annuler(p["n"])  # une seule fois
    assert not decisions.rassembler(m)["office"]


def test_reste_a_faire_d_un_agent_devient_une_ligne_pas_une_tache_a_trancher(config, vault, faux):
    m = _m(config, vault, faux)
    nb = len(vault.index()[0])
    r = m.proposer("tache", "mere", "Vérifier la suite d'audit", de="enfant", motif=MOTIF)
    assert r["etat"] == "ligne" and r["tache"] == "enfant"
    assert "Vérifier la suite d'audit" in fiches.lire(vault.tache("enfant").chemin)
    assert len(vault.index()[0]) == nb and not m.propositions.liste


def test_fermer_reste_a_trancher(config, vault, faux):
    m = _m(config, vault, faux)
    p = m.proposer("fermer", "x", "abandonne", de="mere", motif=MOTIF)
    assert p["etat"] == "en_attente" and "auto" not in p
    assert vault.tache("x").statut == "a-faire"


def test_famille_retiree_des_gestes_d_office_repasse_a_trancher(config, vault, faux):
    config.interface.office = ["lier"]
    m = _m(config, vault, faux)
    assert m.proposer("lier", "mere", "alimente:x")["etat"] == "acceptee"
    assert m.proposer("renommer", "x", "Autre titre", motif=MOTIF)["etat"] == "en_attente"


def test_echec_d_office_laisse_la_proposition_en_attente(config, vault, faux, monkeypatch):
    m = _m(config, vault, faux)

    def refuse(*a, **k):
        raise Conflit("cible verrouillée")
    monkeypatch.setattr(m.vault, "renommer", refuse)
    p = m.proposer("renommer", "x", "Titre refusé", motif=MOTIF)
    assert p["etat"] == "en_attente" and p["echec"] == "cible verrouillée" and "auto" not in p
    assert [d for d in decisions.rassembler(m)["decisions"] if d["genre"] == "proposition"]
