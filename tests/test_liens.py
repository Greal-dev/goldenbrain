"""Liens fonctionnels (alimente, voir_aussi), INV-VAULT-1 sur ces clés, propagation INV-LIEN-1."""

import pytest

from orchestrateur import fiches, liens
from orchestrateur.vault import Conflit, Invalide, NonTrouve
from conftest import ecrire, tache_md
from test_moteur import executer, finir, moteur


def ref_ids(vault, ident):
    r = liens.refs(vault.index()[0], ident)
    return {k: [x["id"] for x in v] for k, v in r.items()}


def test_lien_cree_retire_et_alimente_par_calcule(vault):
    liens.lier(vault, "mere", "alimente", "x")
    assert "alimente: [x]\n" in fiches.lire(vault.tache("mere").chemin)
    assert ref_ids(vault, "mere")["alimente"] == ["x"]
    assert ref_ids(vault, "x") == {"alimente": [], "alimente_par": ["mere"], "prerequis": [],
                                 "requis_par": [], "voir_aussi": []}
    assert "alimente" not in vault.tache("x").fm  # « alimenté par » n'est jamais écrit
    liens.delier(vault, "mere", "alimente", "x")
    assert "alimente" not in fiches.lire(vault.tache("mere").chemin)  # clé retirée si vide
    with pytest.raises(NonTrouve):
        liens.delier(vault, "mere", "alimente", "x")


def test_refus_doublon_soi_meme_cycle_et_type_inconnu(vault):
    liens.lier(vault, "mere", "alimente", "enfant")
    liens.lier(vault, "enfant", "alimente", "petit")
    with pytest.raises(Conflit):
        liens.lier(vault, "mere", "alimente", "enfant")  # doublon
    with pytest.raises(Conflit):
        liens.lier(vault, "mere", "voir_aussi", "mere")  # soi-même
    with pytest.raises(Conflit, match="cycle"):
        liens.lier(vault, "petit", "alimente", "mere")
    with pytest.raises(Invalide):
        liens.lier(vault, "mere", "depend", "x")
    with pytest.raises(NonTrouve):
        liens.lier(vault, "mere", "alimente", "inconnue")


def test_voir_aussi_vu_et_retirable_des_deux_cotes(vault):
    liens.lier(vault, "mere", "voir_aussi", "x")
    assert ref_ids(vault, "x")["voir_aussi"] == ["mere"]
    with pytest.raises(Conflit):
        liens.lier(vault, "x", "voir_aussi", "mere")  # doublon vu depuis l'autre côté
    liens.delier(vault, "x", "voir_aussi", "mere")  # retiré du côté qui ne le stocke pas
    assert "voir_aussi" not in vault.tache("mere").fm
    assert ref_ids(vault, "mere")["voir_aussi"] == []


def test_fichier_restitue_octet_pour_octet_crlf(vault, racine):
    texte = ("---\r\ntype: tache\r\n# commentaire\r\ninconnue:   valeur  \r\nstatut: a-faire\r\n"
             "updated: 2020-01-01\r\n---\r\n\r\n# Brut\r\n\r\nCorps  \r\n")
    p = ecrire(racine, "Projets/C1-Alpha/taches/brut.md", texte)
    liens.lier(vault, "brut", "voir_aussi", "mere")
    apres = p.read_bytes().decode()
    assert "voir_aussi: [mere]\r\n---\r\n" in apres
    liens.delier(vault, "brut", "voir_aussi", "mere")
    jour = vault.tache("brut").fm["updated"]
    assert p.read_bytes().decode() == texte.replace("2020-01-01", jour)


def test_lecture_tolerante_et_reecriture_sur_une_ligne(vault, racine):
    p = ecrire(racine, "Projets/C1-Alpha/taches/multi.md",
               "---\ntype: tache\nstatut: a-faire\nalimente:\n  - \"[[enfant]]\"\n  - x\n"
               "voir_aussi: \"[[petit]]\"\nfin: oui\n---\n\n# Multi\n")
    assert ref_ids(vault, "multi")["alimente"] == ["enfant", "x"]
    assert ref_ids(vault, "multi")["voir_aussi"] == ["petit"]
    liens.lier(vault, "multi", "alimente", "mere")
    texte = p.read_text("utf-8")
    assert "alimente: [enfant, x, mere]\nvoir_aussi: \"[[petit]]\"\nfin: oui\n" in texte


def test_wikilinks_en_liste_en_ligne(vault, racine):
    ecrire(racine, "Projets/C1-Alpha/taches/wiki.md",
           tache_md(extra="alimente: [[[enfant]], [[x]]]\n", titre="Wiki"))
    assert ref_ids(vault, "wiki")["alimente"] == ["enfant", "x"]


def test_identifiant_orphelin_ignore_a_l_affichage_et_conserve(vault, racine):
    p = ecrire(racine, "Projets/C1-Alpha/taches/orph.md",
               tache_md(extra="voir_aussi: [disparue, enfant]\n", titre="Orph"))
    assert ref_ids(vault, "orph")["voir_aussi"] == ["enfant"]
    liens.delier(vault, "orph", "voir_aussi", "enfant")
    assert "voir_aussi: [disparue]\n" in p.read_text("utf-8")


def test_annoter_compte_les_liens_des_noeuds(vault):
    liens.lier(vault, "mere", "alimente", "x")
    liens.lier(vault, "mere", "voir_aussi", "doublon")
    noeuds = liens.annoter(vault.arbre(False), vault.index()[0])

    def trouver(ns, ident):
        for n in ns:
            if n["id"] == ident:
                return n
            if (r := trouver(n["enfants"], ident)) is not None:
                return r

    assert trouver(noeuds, "mere")["liens"] == 2 and trouver(noeuds, "x")["liens"] == 1
    assert trouver(noeuds, "petit")["liens"] == 0


def test_deplacement_ne_touche_pas_aux_liens(vault):
    liens.lier(vault, "x", "alimente", "mere")
    vault.deplacer_conteneur("x", "Projets/C2-Beta")
    assert ref_ids(vault, "mere")["alimente_par"] == ["x"]


# --- INV-LIEN-1 ----------------------------------------------------------------------------
def propager(config, vault, faux, depart="mere"):
    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre(depart, "avance")
        await finir(m)

    executer(scenario())
    return [(x["env"]["ORCH_TACHE"], x["message"]) for x in faux.lances]


def test_propagation_apres_tour_reussi_vers_taches_ouvertes(config, vault, faux):
    vault.modifier("mere", {"alimente": ["x", "fermee"]})
    lances = propager(config, vault, faux)
    assert [t for t, _ in lances] == ["mere", "x"]  # jamais vers une tâche fermée
    msg = lances[1][1]
    assert msg.startswith("[La tâche « Mère » (mere), qui t'alimente, vient d'avancer. "
                          "Fait : lu le dossier Situation : en bonne voie")
    assert faux.lances[1]["env"]["ORCH_SAUTS"] == "1"


def test_pas_de_propagation_apres_echec(config, vault, faux):
    from orchestrateur.harnais import Evenement
    faux.scenario = [Evenement("erreur", texte="boum")]
    vault.modifier("mere", {"alimente": ["x"]})
    assert [t for t, _ in propager(config, vault, faux)] == ["mere"]


def test_propagation_desactivable(config, vault, faux):
    config.liens.propagation = False
    vault.modifier("mere", {"alimente": ["x"]})
    assert [t for t, _ in propager(config, vault, faux)] == ["mere"]


def test_propagation_bornee_par_les_sauts(config, vault, faux):
    # Cycle à trois, écrit à la main (le contrôle de cycle ne vaut que pour l'orchestrateur).
    vault.modifier("mere", {"alimente": ["x"]})
    vault.modifier("x", {"alimente": ["enfant"]})
    vault.modifier("enfant", {"alimente": ["mere"]})
    lances = propager(config, vault, faux)
    assert len(lances) == config.moteur.sauts_max + 1  # INV-MSG-1 coupe la boucle


def test_pas_d_accuse_de_retour_vers_la_source(config, vault, faux):
    # Cycle à deux : x, déclenché par mere, ne repropage pas vers mere (INV-MSG-2).
    vault.modifier("mere", {"alimente": ["x"]})
    vault.modifier("x", {"alimente": ["mere"]})
    assert [t for t, _ in propager(config, vault, faux)] == ["mere", "x"]


def test_message_d_une_tache_ne_revient_pas_vers_elle(config, vault, faux):
    vault.modifier("x", {"alimente": ["mere"]})

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("x", "salut", de="mere")
        await finir(m)
    executer(scenario())
    assert [x["env"]["ORCH_TACHE"] for x in faux.lances] == ["x"]
