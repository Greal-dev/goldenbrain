"""Chaînes de phases : modèles (lecture, priorité du vault, traduction), lancement, enchaînement, validation,
échec et reprise, ajustements de l'IA, surveillance d'un dossier, API et commande (INV-CHAINE-*)."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from conftest import RENDU, ecrire, scenario_ok
from orchestrateur import api, chaines, cli_chaines, langues
from orchestrateur.cli_erreurs import ErreurCli
from orchestrateur.chaines_execution import Chaines
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Invalide, NonTrouve
from test_api import BASE, H

MODELE = """---
titre: Essai
resume: trois phases
phases:
  - titre: Analyse
    consigne: Analyse le dossier.
    livrable: analyse.md
    validation: true
  - titre: Rédaction
    consigne: Rédige.
  - titre: Relecture
    consigne: Relis.
---

# Essai

Contexte commun de l'essai.
"""
FINI = RENDU.replace("<fiche>\n", "<fiche>\nstatut: terminee\n")


def executer(coro):
    return asyncio.run(coro)


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def monde(config, vault, faux, modele=MODELE):
    ecrire(vault.racine, "_meta/chaines/essai.md", modele)
    m = Moteur(config, vault, {"faux": faux})
    m.chaines = Chaines(m)
    return m, m.chaines


# --- modèles ---------------------------------------------------------------------------------
def test_modeles_integres_listes_et_vault_prioritaire(racine):
    ids = [m["id"] for m in chaines.lister(racine)]
    assert {"appel-d-offres", "article"} <= set(ids)
    ao = chaines.modele(racine, "appel-d-offres")
    assert ao["origine"] == "integre" and len(ao["phases"]) == 5 and ao["phases"][1]["validation"]
    ecrire(racine, "_meta/chaines/appel-d-offres.md", MODELE)
    assert chaines.modele(racine, "appel-d-offres")["origine"] == "vault"
    with pytest.raises(NonTrouve):
        chaines.modele(racine, "absente")


@pytest.mark.parametrize("langue", ["en", "de", "es"])
def test_modeles_integres_traduits(racine, langue):
    fr = {m["id"]: m for m in chaines.lister(racine, "fr")}
    tr = {m["id"]: m for m in chaines.lister(racine, langue)}
    for ident in ("appel-d-offres", "article"):
        assert len(tr[ident]["phases"]) == len(fr[ident]["phases"])
        assert tr[ident]["titre"] != fr[ident]["titre"]


@pytest.mark.parametrize("donnees, motif", [
    ({"titre": "", "phases": [{"titre": "a", "consigne": "b"}]}, "titre"),
    ({"titre": "x", "phases": []}, "phase"),
    ({"titre": "x", "phases": [{"titre": "a"}]}, "consigne"),
    ({"titre": "x", "phases": ["texte"]}, "objet"),
    ({"titre": "x", "phases": [{"titre": "a", "consigne": "b"}] * 21}, "20"),
    ({"titre": "x", "phases": [{"titre": "a", "consigne": "b"}], "surveiller": "../dehors"}, "relatif"),
    ({"titre": "x", "phases": [{"titre": "a", "consigne": "b"}], "surveiller": "/tmp"}, "relatif"),
])
def test_modele_invalide_refuse(racine, donnees, motif):
    with pytest.raises(Invalide, match=motif):
        chaines.normaliser(donnees)


def test_modele_illisible_ecarte_sans_casser_la_liste(racine):
    ecrire(racine, "_meta/chaines/casse.md", "---\ntitre: [\n---\n")
    ecrire(racine, "_meta/chaines/sans-phase.md", "---\ntitre: Vide\n---\n")
    ids = [m["id"] for m in chaines.lister(racine)]
    assert "casse" not in ids and "sans-phase" not in ids and "article" in ids


def test_enregistrer_relire_et_retirer(racine):
    m = chaines.enregistrer(racine, {"titre": "Ma chaîne", "contexte": "Commun.",
                                     "phases": [{"titre": "Un", "consigne": "Fais un.", "validation": True}]})
    assert m["id"] == "ma-chaine"
    relu = chaines.modele(racine, "ma-chaine")
    assert relu["contexte"] == "Commun." and relu["phases"][0]["validation"] is True
    chaines.retirer(racine, "ma-chaine")
    with pytest.raises(NonTrouve):
        chaines.retirer(racine, "ma-chaine")


def test_tirets_dans_une_consigne_ne_coupent_pas_l_entete(racine):
    phases = [{"titre": "Un", "consigne": "a --- b\n---\nc"}, {"titre": "Deux", "consigne": "Fais deux."}]
    chaines.enregistrer(racine, {"titre": "Tirets", "contexte": "Commun.\n\n\nSuite.", "phases": phases})
    relu = chaines.modele(racine, "tirets")
    assert [p["consigne"] for p in relu["phases"]] == ["a --- b\n---\nc", "Fais deux."]
    assert relu["contexte"] == "Commun.\n\n\nSuite."


# --- exécution -------------------------------------------------------------------------------
def test_lancer_cree_parente_et_phases_et_soumet_la_premiere(config, vault, faux):
    async def scenario():
        m, c = monde(config, vault, faux)
        ecrire(vault.racine, "Projets/C1-Alpha/ao/dossier-1/rc.md", "règlement")
        parent = c.lancer("essai", "Projets/C1-Alpha", "Projets/C1-Alpha/ao/dossier-1")
        await finir(m)
        p = vault.tache(parent)
        assert p.titre == "Essai — dossier-1" and p.fm["chaine"] == "essai" and p.fm["execution"] == "par_tache"
        e = c.public(parent)
        assert [ph["titre"] for ph in e["phases"]] == ["Analyse", "Rédaction", "Relecture"]
        assert [ph["etat"] for ph in e["phases"]] == ["en_cours", "a_venir", "a_venir"]
        assert vault.tache(e["phases"][0]["tache"]).fm["chaine_phase"] == "1"
        assert len(faux.lances) == 1
        msg = faux.lances[0]["message"]
        assert "Analyse le dossier." in msg and "Contexte commun de l'essai." in msg
        assert str(vault.racine / "Projets/C1-Alpha/ao/dossier-1") in msg and "orch chaine" in msg
    executer(scenario())


def test_enchainement_validation_puis_fin(config, vault, faux):
    async def scenario():
        m, c = monde(config, vault, faux)
        parent = c.lancer("essai", "Projets/C1-Alpha", titre="D1")
        await finir(m)
        ph = [p["tache"] for p in c.public(parent)["phases"]]
        c.apres_tour(ph[1], "fait")  # le tour d'une autre phase ne fait rien avancer
        assert c.public(parent)["courante"] == 0
        c.apres_tour(ph[0], "fait")
        e = c.public(parent)
        assert e["etat"] == "attente_validation" and vault.tache(parent).statut == vault.retour
        with pytest.raises(Conflit):
            c.reprendre(parent)
        c.poursuivre(parent)
        await finir(m)
        assert c.public(parent)["phases"][1]["etat"] == "en_cours" and len(faux.lances) == 2
        assert "Analyse (" in faux.lances[1]["message"]  # résultats des phases précédentes
        c.apres_tour(ph[1], "fait")
        await finir(m)
        c.apres_tour(ph[2], "fait")
        assert c.public(parent)["etat"] == "terminee" and vault.tache(parent).statut == "fait"
        with pytest.raises(Conflit):
            c.poursuivre(parent)
    executer(scenario())


def test_echec_puis_reprise(config, vault, faux):
    async def scenario():
        m, c = monde(config, vault, faux)
        parent = c.lancer("essai", "Projets/C1-Alpha", titre="D2")
        await finir(m)
        premiere = c.public(parent)["phases"][0]["tache"]
        c.apres_tour(premiere, "bloque")
        assert c.public(parent)["etat"] == "echec"
        c.reprendre(parent)
        await finir(m)
        assert c.public(parent)["etat"] == "en_cours" and len(faux.lances) == 2
        assert faux.lances[1]["message"].startswith("[Reprise")
    executer(scenario())


def test_phase_conclue_sans_fin_de_tour_vue_reconciliee(config, vault, faux):
    async def scenario():
        m, c = monde(config, vault, faux)
        parent = c.lancer("essai", "Projets/C1-Alpha", titre="D3")
        await finir(m)
        premiere = c.public(parent)["phases"][0]["tache"]
        vault.poser_statut(premiere, "fait")  # posé à la main, ou fin perdue au redémarrage
        c.reconcilier()
        await finir(m)
        e = c.public(parent)  # « Analyse » demande la validation humaine
        assert e["phases"][0]["etat"] == "faite" and e["etat"] == "attente_validation"
    executer(scenario())


def test_boucle_enchaine_seule_sur_fin_de_tour(config, vault, faux):
    faux.scenario = scenario_ok(rendu=FINI)
    sans_validation = MODELE.replace("    validation: true\n", "")

    async def scenario():
        m, c = monde(config, vault, faux, sans_validation)
        boucle = asyncio.create_task(c.boucle())
        await asyncio.sleep(0)
        parent = c.lancer("essai", "Projets/C1-Alpha", titre="D3")
        for _ in range(200):
            await asyncio.sleep(0.01)
            if c.public(parent)["etat"] == "terminee":
                break
        boucle.cancel()
        await finir(m)
        assert c.public(parent)["etat"] == "terminee" and len(faux.lances) == 3
        assert json.loads((config.donnees / "etat" / "chaines.json").read_text("utf-8"))["executions"][parent]
    executer(scenario())


def test_ajustements_journalises_et_bornes(config, vault, faux):
    async def scenario():
        m, c = monde(config, vault, faux)
        parent = c.lancer("essai", "Projets/C1-Alpha", titre="D4")
        await finir(m)
        source = c.public(parent)["phases"][0]["tache"]
        with pytest.raises(Invalide):
            c.ajuster(source, "sauter", "3")  # motif requis
        with pytest.raises(Conflit):
            c.ajuster(source, "sauter", "1", motif="m")  # phase en cours
        with pytest.raises(Invalide):
            c.ajuster(source, "renommer", "2", motif="m")
        with pytest.raises(NonTrouve):
            c.ajuster("mere", "sauter", "2", motif="m")
        c.ajuster(source, "sauter", "3", motif="pas de relecture pour ce dossier")
        c.ajuster(source, "ajouter", "1", "Chiffrage", "Chiffre l'offre.", "le dossier a un BPU")
        c.ajuster(source, "dedoubler", "2", motif="deux lots")
        c.ajuster(source, "consigne", "2", consigne="Rédige le lot 1.", motif="lots séparés")
        e = c.public(parent)
        assert [p["num"] for p in e["phases"]] == ["1", "1.1", "2", "2.1", "3"]
        assert [p["etat"] for p in e["phases"]][-1] == "sautee"
        assert vault.tache(e["phases"][-1]["tache"]).statut == "abandonne"
        assert vault.tache(e["phases"][1]["tache"]).titre == "1.1. Chiffrage"
        assert c.etat["executions"][parent]["phases"][2]["consigne"] == "Rédige le lot 1."
        assert [a["action"] for a in e["ajustements"]] == ["sauter", "ajouter", "dedoubler", "consigne"]
        assert all(a["motif"] and a["de"] == source for a in e["ajustements"])
        c.apres_tour(source, "fait")
        await finir(m)
        c.poursuivre(parent)
        await finir(m)
        assert c.public(parent)["phases"][1]["etat"] == "en_cours"  # la phase ajoutée part ensuite
    executer(scenario())


def test_surveillance_sans_rattrapage_une_seule_fois(config, vault, faux):
    modele = MODELE.replace("titre: Essai\n", "titre: Essai\nsurveiller: Entrees\nconteneur: Projets/C1-Alpha\n")

    async def scenario():
        m, c = monde(config, vault, faux, modele)
        ecrire(vault.racine, "Entrees/ancien/a.md", "x")
        assert c.surveiller() == []  # présent au départ : jamais rattrapé
        ecrire(vault.racine, "Entrees/nouveau/b.md", "x")
        lancees = c.surveiller()
        assert len(lancees) == 1 and vault.tache(lancees[0]).titre == "Essai — nouveau"
        assert c.public(lancees[0])["origine"] == "surveillance"
        assert c.surveiller() == []
        chaines.enregistrer(vault.racine, {**chaines.modele(vault.racine, "essai"), "surveiller": "Autres"}, "essai")
        ecrire(vault.racine, "Autres/existant/c.md", "x")
        assert c.surveiller() == []  # dossier surveillé changé : l'existant n'est pas rattrapé
        await finir(m)
    executer(scenario())


# --- API et commande -------------------------------------------------------------------------
def test_api_modeles_lancer_et_ajuster(config, vault, faux):
    ecrire(vault.racine, "_meta/chaines/essai.md", MODELE)
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        assert "essai" in [m["id"] for m in c.get("/api/chaines").json()]
        corps = {"titre": "Neuve", "phases": [{"titre": "Un", "consigne": "Fais."}]}
        assert c.post("/api/chaines", json=corps, headers=H).json()["id"] == "neuve"
        assert c.post("/api/chaines", json={**corps, "phases": []}, headers=H).status_code == 400
        assert c.post("/api/chaines/neuve/retirer", headers=H).json() == {"ok": True}
        r = c.post("/api/chaines/lancer", json={"modele": "essai", "conteneur": "Projets/C1-Alpha",
                                                  "titre": "API"}, headers=H)
        assert r.status_code == 200, r.text
        e = r.json()
        assert c.get(f"/api/chaines/executions/{e['phases'][0]['tache']}").json()["id"] == e["id"]
        assert [x["id"] for x in c.get("/api/chaines/executions").json()] == [e["id"]]
        assert c.post(f"/api/chaines/executions/{e['id']}/poursuivre", headers=H).status_code == 409
        aj = {"de": e["phases"][0]["tache"], "action": "sauter", "n": "2", "motif": "inutile"}
        assert c.post("/api/chaines/ajuster", json=aj, headers=H).json()["phases"][1]["etat"] == "sautee"
        assert c.post("/api/chaines/lancer", json={"modele": "absente"}, headers=H).status_code == 404


def test_commande_chaine_plan_et_ajouter():
    appels = []

    def appeler(methode, chemin, corps=None):
        appels.append((methode, chemin, corps))
        return {"id": "p", "titre": "Essai", "etat": "en_cours",
                "phases": [{"num": "1", "titre": "Analyse", "tache": "t1", "etat": "en_cours", "validation": True}]}

    a = SimpleNamespace(action="plan", valeurs=[], apres="", motif="", tache="")
    sortie = cli_chaines.executer(a, appeler, lambda s: s, "t1")
    assert appels[-1][:2] == ("GET", "/chaines/executions/t1") and sortie[1].startswith("[>] 1. Analyse")
    a = SimpleNamespace(action="ajouter", valeurs=["Chiffrage", "Chiffre."], apres="1", motif="BPU", tache="")
    cli_chaines.executer(a, appeler, lambda s: s, "t1")
    assert appels[-1][2] == {"de": "t1", "action": "ajouter", "motif": "BPU", "n": "1", "titre": "Chiffrage",
                             "consigne": "Chiffre."}
    with pytest.raises(ErreurCli, match="ORCH_TACHE"):  # B11 : code de sortie non nul
        cli_chaines.executer(a, appeler, lambda s: s, "")


def test_cles_serveur_existent_en_quatre_langues():
    for code in ("fr", "en", "de", "es"):
        assert langues.t("serveur.chaines.motif_requis", code) != "serveur.chaines.motif_requis"
