"""Un projet créé depuis les notes (sa fiche `contexte.md`) accepte des tâches tout de suite."""

from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


def test_projet_cree_par_sa_fiche_de_contexte_est_connu_aussitot(config, vault, faux):
    config.vault.index_ttl_s = 60  # l'index en mémoire ne doit pas masquer le projet neuf
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        assert c.get("/api/arbre").status_code == 200  # index chargé et gardé en mémoire
        r = c.post("/api/vault/note", headers=H, json={
            "dossier": "Projets/C1-Neuf", "nom": "contexte", "creer_dossier": True,
            "contenu": "---\ntype: contexte\ncasquette: C1\nnom: Neuf\n---\n# Neuf\n"})
        assert r.status_code == 201
        t = c.post("/api/taches", headers=H, json={"titre": "Première", "conteneur": "Projets/C1-Neuf"})
        assert t.status_code == 201 and t.json()["conteneur"] == "Projets/C1-Neuf"
