"""Propositions enrichies : motif, types lier / operation / tache / perimetre, échec d'acceptation."""

import json

import pytest

from orchestrateur import fiches, liens
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Invalide
from conftest import ecrire, tache_md
from test_moteur import executer, finir, moteur


def test_motif_enregistre_et_ancienne_proposition_lisible(config, vault, faux):
    etat = config.donnees / "etat"
    etat.mkdir(parents=True)
    (etat / "propositions.json").write_text(json.dumps([
        {"n": 1, "type": "deplacer", "tache": "x", "titre_tache": "X", "valeur": "Projets/C2-Beta",
         "de": "", "etat": "en_attente", "cree": "2026-11-01T10:00:00"}]), encoding="utf-8")
    m = Moteur(config, vault, {"faux": faux})
    assert m.propositions.liste[0]["motif"] == ""
    p = m.proposer("projet", "x", "Projet X", de="mere", motif="  trop gros\npour rester ")
    assert p["motif"] == "trop gros pour rester"
    assert m.trancher(1, True)["etat"] == "acceptee"


def test_lier_accepte(config, vault, faux):
    config.interface.office = []  # INV-PROP-1 : ce test éprouve le geste à trancher
    m = Moteur(config, vault, {"faux": faux})
    p = m.proposer("lier", "mere", "alimente:x", motif="x dépend de mere")
    m.trancher(p["n"], True)
    assert [r["id"] for r in liens.refs(vault.index()[0], "x")["alimente_par"]] == ["mere"]
    with pytest.raises(Invalide):
        m.proposer("lier", "mere", "parent:x")


def test_lier_en_echec_reste_en_attente(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    liens.lier(vault, "x", "alimente", "mere")
    p = m.proposer("lier", "mere", "alimente:x")
    with pytest.raises(Conflit):
        m.trancher(p["n"], True)  # fermerait un cycle
    assert m.propositions.get(p["n"])["etat"] == "en_attente"


def test_operation_ne_s_accepte_pas_hors_api(config, vault, faux):
    # INV-ARBRE-2 : elle déplace un dossier (plan, verrou, tout ou rien) : voir
    # test_verrou_deplacement.py ; `trancher` seul ne réécrit plus `parent:`.
    m = Moteur(config, vault, {"faux": faux})
    p = m.proposer("operation", "petit", "Opération Neuve")
    with pytest.raises(Conflit, match="déplace un dossier"):
        m.trancher(p["n"], True)
    assert m.propositions.get(p["n"])["etat"] == "en_attente"


def test_tache_acceptee_cree_une_tache_liee_non_lancee(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.trancher(m.proposer("tache", "mere", "Idée manquante",
                              motif="Couvre un besoin que la tâche mère oublie")["n"], True)
        await finir(m)

    executer(scenario())
    neuve = next(t for t in vault.index()[0].values() if t.titre == "Idée manquante")
    assert neuve.conteneur == "Projets/C1-Alpha" and neuve.statut == "a-faire"
    assert [r["id"] for r in liens.refs(vault.index()[0], "mere")["voir_aussi"]] == [neuve.id]
    assert faux.lances == []


def test_perimetre_accepte_soumet_le_message(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.trancher(m.proposer("perimetre", "x", "Se limiter au devis.", de="mere")["n"], True)
        await finir(m)

    executer(scenario())
    assert [(x["env"]["ORCH_TACHE"], x["message"]) for x in faux.lances] == [
        ("x", "[Périmètre révisé, validé par l'utilisateur] Se limiter au devis.")]
    assert fiches.lire_fiche(fiches.lire(vault.tache("x").chemin))["fait"] == "lu le dossier"


def test_proposition_deplacer_ramene_le_nom_du_dossier_a_l_identifiant(config, vault, faux):
    moteur = Moteur(config, vault, {"faux": faux})
    p = moteur.proposer("deplacer", "mere", "c1-alpha")
    assert p["valeur"] == "Projets/C1-Alpha"
    with pytest.raises(Invalide):
        moteur.proposer("deplacer", "mere", "Dossier-Inexistant")


def test_accepter_un_lien_deja_present_conclut_sans_erreur_et_ne_depose_rien(config, vault, faux):
    """Symptôme (23/11) : « lien déjà présent » à l'acceptation, proposition restée en attente."""
    config.interface.office = []  # INV-PROP-1 : ce test éprouve le geste à trancher
    m = Moteur(config, vault, {"faux": faux})
    p = m.proposer("lier", "mere", "alimente:x")
    liens.lier(vault, "mere", "alimente", "x")  # le lien est posé entre-temps
    r = m.trancher(p["n"], True)
    assert r["etat"] == "acceptee" and r["deja_fait"] is True
    # dépôt : un effet déjà en place n'est pas déposé
    assert m.proposer("lier", "mere", "alimente:x")["etat"] == "deja_fait"
    assert len(m.propositions.liste) == 1


def test_gestes_deja_realises_ne_sont_pas_deposes(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    assert m.proposer("rattacher", "petit", "enfant")["etat"] == "deja_fait"
    assert m.proposer("rattacher", "mere", "racine")["etat"] == "deja_fait"
    assert m.proposer("deplacer", "doublon", "Projets/C2-Beta")["etat"] == "deja_fait"
    assert m.propositions.liste == []


def _integration_permanente(racine):
    ecrire(racine, "Projets/C1-Alpha/taches/integ.md", tache_md(statut="en-cours", extra="nature: permanente\n", titre="Intégrer"))


def test_livraison_bloquee_une_nuit_par_un_lien_d_integration_en_attente(config, vault, faux, racine):
    # Symptôme : le lien « alimente » vers l'intégration attendait dans Décisions, la branche n'était pas fusionnée.
    _integration_permanente(racine)
    m = Moteur(config, vault, {"faux": faux})
    p = m.proposer("lier", "mere", "alimente:integ", de="mere", motif="livre la branche")
    assert p["etat"] == "acceptee" and p["auto"] is True
    assert [r["id"] for r in liens.refs(vault.index()[0], "mere")["alimente"]] == ["integ"]
    assert not [q for q in m.propositions.liste if q["etat"] == "en_attente"]
    assert "lier alimente:integ" in fiches.lire(vault.tache("mere").chemin)  # mention discrète dans « Traces »


def test_lien_vers_une_tache_permanente_est_pose_meme_si_les_propositions_sont_ignorees(config, vault, faux, racine):
    _integration_permanente(racine)
    config.interface.propositions = "ignorer"
    m = Moteur(config, vault, {"faux": faux})
    assert m.proposer("lier", "mere", "alimente:integ")["etat"] == "acceptee"
    assert [r["id"] for r in liens.refs(vault.index()[0], "mere")["alimente"]] == ["integ"]


def test_les_autres_liens_gardent_la_politique(config, vault, faux, racine):
    config.interface.office = []  # INV-PROP-1 : ce test éprouve le geste à trancher
    _integration_permanente(racine)
    m = Moteur(config, vault, {"faux": faux})
    assert m.proposer("lier", "mere", "alimente:x")["etat"] == "en_attente"  # cible ordinaire
    assert m.proposer("lier", "mere", "voir_aussi:integ")["etat"] == "en_attente"  # lien autre qu'alimente
