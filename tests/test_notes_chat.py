"""INV-NOTECHAT-1 : barre de chat IA de la vue Notes — proposition seulement (tâche ou retouche), projet déduit
de la place de la note, note liée dans la description, refus d'un agent ; l'application passe par PUT /vault/note."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.config import ConfigRole
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
NOTE = "Projets/C1-Alpha/idees.md"
CORPS = "---\ntype: note\n---\n# Idées\nappeler le plombié jeudi\n"


@pytest.fixture
def client(config, vault, faux, racine):
    config.moteurs_par_role["notes"] = ConfigRole(harnais="claude", modele="petit")
    (racine / NOTE).write_text(CORPS, encoding="utf-8")
    with TestClient(api.creer_app(config, Moteur(config, vault, {"claude": faux})), base_url=BASE) as c:
        yield c


def ia(client, action, consigne="", entetes=H, chemin=NOTE):
    return client.post("/api/vault/note/ia", headers=entetes, json={"chemin": chemin, "action": action, "consigne": consigne})


def test_tache_proposee_avec_note_liee_et_projet_deduit(client, faux, racine):
    faux.scenario = [Evenement("fin", texte="<titre>Appeler le plombier</titre><description>Obtenir un devis.</description>")]
    avant = (racine / NOTE).read_text(encoding="utf-8")
    j = ia(client, "tache", "pour jeudi").json()
    assert j["titre"] == "Appeler le plombier" and j["conteneur"] == "Projets/C1-Alpha"
    assert j["description"].startswith("Obtenir un devis.") and f"[[{NOTE[:-3]}]]" in j["description"]
    msg = faux.lances[-1]["message"]
    assert "plombié" in msg and "type: note" not in msg and "pour jeudi" in msg  # corps seul, précision transmise
    assert (racine / NOTE).read_text(encoding="utf-8") == avant  # rien n'est écrit
    assert client.get("/api/arbre").status_code == 200  # aucune tâche créée par la proposition


def test_retouche_proposee_puis_appliquee_et_annulee_par_les_routes_des_notes(client, faux):
    faux.scenario = [Evenement("fin", texte="<proposition>appeler le plombier jeudi</proposition>")]
    j = ia(client, "reformuler").json()
    assert j["proposition"] == "appeler le plombier jeudi" and j["original"].endswith("appeler le plombié jeudi")
    n = client.get(f"/api/vault/note?chemin={NOTE}").json()
    assert "plombié" in n["contenu"]  # proposée seulement
    r = client.put("/api/vault/note", headers=H, json={"chemin": NOTE, "mtime_ns": n["mtime_ns"],
                                                        "contenu": "---\ntype: note\n---\n" + j["proposition"] + "\n"})
    assert r.status_code == 200
    r = client.put("/api/vault/note", headers=H, json={"chemin": NOTE, "mtime_ns": r.json()["mtime_ns"], "contenu": n["contenu"]})
    assert client.get(f"/api/vault/note?chemin={NOTE}").json()["contenu"] == CORPS


def test_consigne_libre_exigee_actions_et_refus(client, faux):
    faux.scenario = [Evenement("fin", texte="<proposition>X</proposition>")]
    assert ia(client, "libre").status_code == 400
    assert ia(client, "libre", "mets en liste").status_code == 200
    assert "mets en liste" in faux.lances[-1]["message"]
    assert ia(client, "traduire").status_code == 400
    assert ia(client, "resumer", entetes={**H, "X-Orch-Tache": "enfant"}).status_code == 409
    assert ia(client, "resumer", chemin="Projets/C1-Alpha/absente.md").status_code == 404


def test_erreur_lisible_et_reponse_sans_titre(client, faux):
    faux.scenario = [Evenement("erreur", texte="quota épuisé")]
    assert ia(client, "tache").json()["erreur"]
    faux.scenario = [Evenement("fin", texte="rien de balisé")]
    j = ia(client, "tache").json()
    assert j["erreur"] and "titre" not in j
