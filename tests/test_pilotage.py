"""Chat de projet : conversation d'un conteneur (INV-PILOTAGE-1, INV-PILOTAGE-2, INV-PILOTAGE-3)."""

import json
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, fiches
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
PROJET = "Projets/C1-Alpha"


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def attendre_inactif(client, ident):
    for _ in range(300):
        if client.get(f"/api/taches/{ident}").json()["etat_execution"] == "inactif":
            return
        time.sleep(0.01)
    raise AssertionError("tour non terminé")


def ecrire_au_conteneur(client, noeud=PROJET, texte="où en est-on ?"):
    r = client.post("/api/pilotage", headers=H, json={"noeud": noeud, "texte": texte})
    assert r.status_code == 202, r.text
    ident = r.json()["tache"]
    attendre_inactif(client, ident)
    return ident


def ids_arbre(noeuds):
    for n in noeuds:
        yield n["id"]
        yield from ids_arbre(n.get("enfants", []))


def test_conversation_creee_au_premier_message_et_unique(client, racine):
    q = urllib.parse.quote(PROJET)
    assert client.get(f"/api/pilotage?noeud={q}").json()["tache"] is None  # lire ne crée rien
    assert not list((racine / PROJET / "taches").glob("*pilotage*"))
    ident = ecrire_au_conteneur(client)
    fichier = racine / PROJET / "taches" / f"{ident}.md"
    fm = fiches.frontmatter(fiches.lire(fichier))
    assert fm["nature"] == "pilotage" and fm["pilote"] == PROJET
    assert ecrire_au_conteneur(client, texte="et maintenant ?") == ident
    assert client.get(f"/api/pilotage?noeud={q}").json()["tache"] == ident
    assert len(list((racine / PROJET / "taches").glob("*pilotage*"))) == 1
    # tâche permanente : jamais « fait », ni « à valider »
    assert client.get(f"/api/taches/{ident}").json()["statut"] != "fait"


def test_masquee_des_listes_et_des_compteurs(client):
    avant = client.get("/api/etat").json()["compte"]
    ident = ecrire_au_conteneur(client)
    for toutes in (0, 1):
        assert ident not in set(ids_arbre(client.get(f"/api/arbre?toutes={toutes}").json()["noeuds"]))
    assert client.get("/api/recherche?q=Pilotage").json() == []
    assert client.get("/api/etat").json()["compte"] == avant
    assert client.get(f"/api/taches/{ident}").status_code == 200  # le panneau de tâche l'ouvre


def test_casquette_et_noeud_inconnu(client, racine):
    ident = ecrire_au_conteneur(client, "casquette:C1")
    assert (racine / "_meta" / "taches" / f"{ident}.md").is_file()  # arrivée : pas de dossier propre
    assert client.get("/api/pilotage?noeud=casquette:C1").json()["tache"] == ident
    assert client.get("/api/pilotage?noeud=casquette:C2").json()["tache"] is None
    r = client.post("/api/pilotage", headers=H, json={"noeud": "Projets/Inconnu", "texte": "x"})
    assert r.status_code == 400


def test_amorcage_avec_la_descendance_et_la_fiche_de_contexte(client, faux, racine):
    p = racine / PROJET / "taches" / "enfant.md"
    p.write_text(fiches.ecrire_fiche(fiches.lire(p), {**fiches.fiche_vide(), "fait": "maquette livrée",
                                                      "situation": "en recette"}), "utf-8")
    ident = ecrire_au_conteneur(client, texte="où en est-on ?")
    msg = faux.lances[-1]["message"]
    assert "Alpha" in msg and "nom: Alpha" in msg  # fiche de contexte recopiée au premier tour
    assert msg.index("Mère") < msg.index("Enfant") < msg.index("Petit")
    assert "  - Enfant (id enfant) [a-faire · inactif] — fait : maquette livrée" in msg
    assert "creer" in msg and msg.endswith("\n\n---\n\noù en est-on ?")
    conv = client.get(f"/api/taches/{ident}/conversation").json()
    assert all("Descendance" not in m["texte"] for m in conv)  # l'amorçage n'est pas montré
    ecrire_au_conteneur(client, texte="suite")
    assert "Fiche de contexte :" in faux.lances[-1]["message"]  # session connue : le chemin seul


def test_amorcage_resume_au_dela_du_seuil(client, faux, racine, monkeypatch):
    from orchestrateur import pilotage
    monkeypatch.setattr(pilotage, "SEUIL", 2)
    ecrire_au_conteneur(client)
    msg = faux.lances[-1]["message"]
    assert "autres tâches ouvertes" in msg and "tâches closes non détaillées" in msg


def test_tache_mere_amorcee_feuille_intacte(client, faux):
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "pilote"})
    attendre_inactif(client, "mere")
    assert "Enfant (id enfant)" in faux.lances[-1]["message"]
    client.post("/api/taches/petit/messages", headers=H, json={"texte": "seul"})
    attendre_inactif(client, "petit")
    assert faux.lances[-1]["message"] == "seul"


def test_creer_et_lancer_une_tache_enfant_depuis_le_chat(client, faux, monkeypatch, capsys):
    ident = ecrire_au_conteneur(client)

    def appeler(methode, chemin, corps=None):  # `orch` branché sur le serveur de test
        r = client.request(methode, "/api" + chemin, headers=H, json=corps)
        if r.status_code >= 400:
            raise cli.ErreurCli(r.text)
        return r.json()
    monkeypatch.setattr(cli, "appeler", appeler)
    monkeypatch.setenv("ORCH_TACHE", ident)
    assert cli.main(["creer", "Rédiger la recette", "--parent", "mere", "--description", "Rédiger la recette de la fête."]) == 0
    sortie = capsys.readouterr().out
    enfant = sortie.split("tâche créée : ")[1].split(" ")[0]
    assert cli.main(["dire", enfant, "rédige-la"]) == 0
    attendre_inactif(client, enfant)
    assert faux.lances[-1]["message"].endswith("rédige-la")
    t = client.get(f"/api/taches/{enfant}").json()
    assert t["parent"] == "mere" and t["session"] == "s-1"
    assert enfant in set(ids_arbre(client.get("/api/arbre?toutes=1").json()["noeuds"]))
    assert cli.main(["arreter", enfant]) == 0 and "inactif" in capsys.readouterr().out


def test_remontee_sans_tour_puis_lue_au_tour_suivant(client, faux):
    ident = ecrire_au_conteneur(client)
    n = len(faux.lances)
    client.post("/api/taches/enfant/messages", headers=H, json={"texte": "avance"})
    attendre_inactif(client, "enfant")
    time.sleep(0.05)
    assert len(faux.lances) == n + 1  # le tour de l'enfant, aucun tour de pilotage
    assert client.get(f"/api/taches/{ident}").json()["etat_execution"] == "inactif"
    conv = client.get(f"/api/taches/{ident}/conversation").json()
    systeme = [m["texte"] for m in conv if m["role"] == "systeme"]
    assert any("« Enfant » (enfant) a fini un tour" in s and "lu le dossier" in s for s in systeme)
    ecrire_au_conteneur(client, texte="et alors ?")
    msg = faux.lances[-1]["message"]
    assert "Remontées depuis ton dernier tour" in msg and "« Enfant » (enfant)" in msg
    ecrire_au_conteneur(client, texte="encore ?")
    assert "Remontées" not in faux.lances[-1]["message"]  # consommées une fois


def test_remontee_vers_une_tache_mere_qui_a_une_conversation(client, faux, config):
    client.post("/api/taches/mere/messages", headers=H, json={"texte": "pilote"})
    attendre_inactif(client, "mere")
    client.post("/api/taches/petit/messages", headers=H, json={"texte": "avance"})
    attendre_inactif(client, "petit")
    journaux = [json.loads(x) for f in (config.donnees / "journal").rglob("mere-*.jsonl")
                for x in f.read_text("utf-8").splitlines()]
    assert any(j.get("type") == "orch_remontee" and "Petit" in j["texte"] for j in journaux)
