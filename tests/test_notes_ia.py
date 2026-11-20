"""INV-EXECUTANT-3 : bouton « IA » du panneau Notes — seule la portée choisie part au modèle, la
réponse est une proposition (rien n'est écrit), le coût est rendu, l'appel vaut aussi en mode « Moi »,
un agent ne peut l'appeler ; l'application et l'annulation passent par les routes des notes."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, roles
from orchestrateur.config import ConfigRole
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
AGENT = {**H, "X-Orch-Tache": "enfant"}
FIN = {"type": "result", "usage": {"input_tokens": 120, "output_tokens": 30}, "total_cost_usd": 0.0021}


@pytest.fixture
def client(config, vault, faux):
    config.moteurs_par_role["notes"] = ConfigRole(harnais="claude", modele="petit")
    with TestClient(api.creer_app(config, Moteur(config, vault, {"claude": faux})), base_url=BASE) as c:
        yield c


def photo(racine):
    return {p.relative_to(racine).as_posix(): p.read_bytes() for p in sorted(racine.rglob("*")) if p.is_file()}


def ia(client, action, texte, entetes=H):
    return client.post("/api/taches/mere/notes/ia", headers=entetes, json={"action": action, "texte": texte})


def test_selection_seule_envoyee_et_rien_ecrit(client, faux, racine):
    client.post("/api/taches/mere/notes", headers=H, json={"texte": "Note privée sans rapport"})
    client.post("/api/taches/mere/notes", headers=H, json={"texte": "Appel : rappeler le notaire jeudi"})
    faux.scenario = [Evenement("fin", texte="Voilà.\n<proposition>\n- Action : notaire jeudi\n</proposition>", brut=FIN)]
    avant = photo(racine)
    r = ia(client, "synthetiser", "Appel : rappeler le notaire jeudi")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["proposition"] == "- Action : notaire jeudi" and j["erreur"] == ""
    assert j["original"] == "Appel : rappeler le notaire jeudi"
    assert (j["harnais"], j["modele"], j["cout"], j["jetons"]) == ("claude", "petit", 0.0021, 150)
    lance = faux.lances[-1]
    assert "rappeler le notaire" in lance["message"] and "Note privée" not in lance["message"]
    assert lance["session"] is None and lance["modele"] == "petit"
    assert "Actions à mener" in lance["message"] and "<proposition>" in lance["consigne"]
    assert photo(racine) == avant  # vault intact
    assert [n["texte"] for n in client.get("/api/taches/mere").json()["notes"]] == [
        "Note privée sans rapport", "Appel : rappeler le notaire jeudi"]  # aucune écriture avant le geste


def test_portee_tout_et_mode_moi(client, faux):
    client.post("/api/taches/mere/executant", headers=H, json={"executant": "humain"})
    faux.scenario = [Evenement("fin", texte="Texte corigé sans balise")]
    j = ia(client, "corriger", "### 2026-11-18 10:00\nPremière note\n\n### 2026-11-18 11:00\nSeconde").json()
    assert j["proposition"] == "Texte corigé sans balise" and j["cout"] is None
    assert "Première note" in faux.lances[-1]["message"] and "Seconde" in faux.lances[-1]["message"]
    assert client.get("/api/taches/mere").json()["executant"] == "humain"  # l'appel ne change pas le mode


def test_appliquer_puis_annuler_restaure_l_original(client, faux):
    client.post("/api/taches/mere/notes", headers=H, json={"texte": "il faut apeller le plombié"})
    faux.scenario = [Evenement("fin", texte="<proposition>il faut appeler le plombier</proposition>")]
    j = ia(client, "corriger", "il faut apeller le plombié").json()
    client.put("/api/taches/mere/notes/0", headers=H, json={"texte": j["proposition"]})
    assert client.get("/api/taches/mere").json()["notes"][0]["texte"] == "il faut appeler le plombier"
    client.put("/api/taches/mere/notes/0", headers=H, json={"texte": j["original"]})
    assert client.get("/api/taches/mere").json()["notes"][0]["texte"] == "il faut apeller le plombié"


def test_refus_agent_action_inconnue_portee_vide_et_erreur_lisible(client, faux):
    assert ia(client, "resumer", "x", AGENT).status_code == 409  # INV-EXECUTANT-2
    assert ia(client, "traduire", "x").status_code == 400
    assert ia(client, "resumer", "   ").status_code == 400
    assert client.post("/api/taches/inconnue/notes/ia", headers=H, json={"action": "resumer", "texte": "x"}).status_code == 404
    faux.scenario = [Evenement("erreur", texte="quota épuisé")]
    j = ia(client, "resumer", "un texte").json()
    assert j["proposition"] == "" and j["erreur"]  # repli tenté puis échec, sans 500


def test_role_notes_economique_par_defaut(config):
    config.credits = {"rapide": ["claude"], "sonnet": ["claude"], "opus": ["claude"]}
    config.harnais["claude"] = {"familles": {"rapide": "haiku", "sonnet": "sonnet", "opus": "opus"}}
    config.moteurs_par_role.pop("notes", None)
    assert roles.Roles(config, {}).choisir("notes") == roles.Choix("claude", "haiku")
