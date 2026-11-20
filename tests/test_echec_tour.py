"""Échec d'un tour visible (INV-EXEC-8) : message du système, repère de la tâche, quota reconnu."""

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrateur import api, echecs, fiches
from orchestrateur.harnais import Evenement, agy, codex, opencode
from orchestrateur.moteur import Moteur
from conftest import scenario_ok

BASE = "http://127.0.0.1:8399"
DONNEES = Path(__file__).parent / "donnees"
QUOTA = "You’ve hit your usage limit. Upgrade to Pro, or try again at 3:14 PM."


def rejouer(analyser, fichier):
    etat: dict = {}
    lignes = (DONNEES / fichier).read_text("utf-8").splitlines()
    return [ev for ligne in lignes for ev in analyser(json.loads(ligne), etat)]


def test_echec_codex_turn_failed_donne_un_evenement_erreur_avec_le_motif():
    evs = rejouer(codex.analyser, "codex-quota.jsonl")
    assert [e.type for e in evs] == ["session", "erreur"] and evs[-1].texte == QUOTA


def test_agy_et_opencode_remontent_leur_motif():
    evs = agy.analyser({"event": "result", "result": {"status": "ERROR", "error": QUOTA}}, {})
    assert evs[-1].type == "erreur" and evs[-1].texte == QUOTA
    evs = rejouer(opencode.analyser, "opencode-erreur.jsonl")
    assert evs[-1].type == "erreur" and "not supported" in evs[-1].texte


def test_quota_reconnu_avec_heure_de_reprise():
    assert echecs.est_quota(QUOTA) and not echecs.est_quota("boum")
    m = echecs.message(QUOTA)
    assert m.startswith("Quota épuisé") and "Reprise possible : 3:14 PM." in m and QUOTA in m
    assert echecs.message("boum") == "La séance de travail a échoué. Motif de l'assistant IA : boum"
    assert "Reprise" not in echecs.message("rate limit exceeded")


def test_echec_de_tour_visible_conversation_arbre_puis_efface_au_succes(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-1"), Evenement("erreur", texte=QUOTA)]

    async def tour(m):
        m.soumettre("mere", "go")
        while any(not b.done() for b in m.boucles.values()):
            await asyncio.gather(*m.boucles.values(), return_exceptions=True)

    m = Moteur(config, vault, {"faux": faux})
    asyncio.run(tour(m))
    assert "Quota épuisé" in vault.tache("mere").fm["echec_tour"]
    with TestClient(api.creer_app(config, m), base_url=BASE) as c:
        conv = c.get("/api/taches/mere/conversation").json()
        systeme = [x for x in conv if x["role"] == "systeme"]
        assert len(systeme) == 1 and "3:14 PM" in systeme[0]["texte"]
        noeud = next(n for n in _taches(c.get("/api/arbre?toutes=1").json()["noeuds"])
                     if n["id"] == "mere")
        assert "Quota épuisé" in noeud["echec"]
    # Tour réussi suivant : le repère disparaît, l'historique garde le message.
    faux.scenario = scenario_ok()
    asyncio.run(tour(m))
    assert not vault.tache("mere").fm.get("echec_tour")
    assert fiches.lire_fiche(fiches.lire(vault.tache("mere").chemin))["fait"] == "lu le dossier"
    with TestClient(api.creer_app(config, m), base_url=BASE) as c:
        assert any(x["role"] == "systeme" for x in c.get("/api/taches/mere/conversation").json())


def _taches(noeuds):
    for n in noeuds:
        if n.get("type") == "tache":
            yield n
        yield from _taches(n.get("enfants") or [])
