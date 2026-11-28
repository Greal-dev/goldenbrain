"""API via TestClient : garde INV-API-1, formes JSON, 400/404/409, flux d'un tour."""

import asyncio
import json
import socket
import threading
import time
import urllib.request

import pytest
import uvicorn
from fastapi.testclient import TestClient

from orchestrateur import api, natif
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def attendre_inactif(client, ident):
    for _ in range(200):
        if client.get(f"/api/taches/{ident}").json()["etat_execution"] == "inactif":
            return
        time.sleep(0.01)
    raise AssertionError("tour non terminé")


def test_garde_host_et_entete(client, config):
    assert client.get("/api/arbre", headers={"Host": "evil.com:8399"}).status_code == 403
    assert client.get("/api/arbre", headers={"Host": "localhost:8399"}).status_code == 200
    r = client.post("/api/taches", json={"titre": "x"})
    assert r.status_code == 403 and "X-Orchestrateur" in r.json()["detail"]
    assert client.post("/api/taches", json={"titre": "x"}, headers=H).status_code == 201


def test_arbre_conteneurs_etat(client):
    noeuds = client.get("/api/arbre").json()["noeuds"]
    assert {n["type"] for n in noeuds} == {"casquette"}
    assert all({"id", "type", "titre", "ouvertes", "enfants"} <= set(n) for n in noeuds)
    toutes = client.get("/api/arbre?toutes=1").json()["noeuds"]
    assert sum(n["ouvertes"] for n in toutes) == sum(n["ouvertes"] for n in noeuds)
    conts = client.get("/api/conteneurs").json()
    assert {"id": "Projets/C1-Alpha", "titre": "Alpha", "casquette": "C1",
            "operation": "Operation-X"} in conts
    etat = client.get("/api/etat").json()
    assert etat.pop("version")["a_jour"] is True
    assert etat == {"pauses": {}, "tours": [], "en_file": 0, "file": [], "a_moi": 0, "moi_valider": 0, "moi_questions": 0, "moi_faire": 0, "en_retard": 0, "propositions": 0,
                    "decisions": 0, "recent": 0, "a_valider": 0, "mandats_sans_tour": [], "occupees": {}, "poste": None, "alertes_vigie": [],
                    "fiches_absentes": {"absentes": 0, "relancees": 0, "bloquees": 0},
                    "reseau": {"actif": True, "perdu_depuis": None, "hors": {}, "en_attente": 0, "taches": []},
                    "compte": {"a-faire": 6},
                    "roles": {"tours": [], "replis": [], "roles": {},
                              "credits": {f: ["agy", "claude"] for f in ("rapide", "sonnet", "opus")}}}


def test_tache_forme_et_404(client):
    t = client.get("/api/taches/enfant").json()
    assert set(t) == {"id", "chemin", "titre", "conteneur", "fil_ariane", "fil", "frontmatter",
                      "statut", "genre", "genre_pose",
                      "statut_verrouille", "harnais", "session", "etat_execution", "reprise_auto", "attente_poste", "rang_poste", "pause_ram", "pause",
                      "controle", "attente_prerequis", "rang_file", "execution", "executant", "notes", "signe", "raison_attente", "incident", "fiche",
                      "corps", "main", "enfants", "parent", "liens", "revues", "renvois", "echeance", "priorite",
                      "retard", "dossier_travail", "dossier_travail_origine",
                      "etiquettes", "consignes_etiquettes", "liees_etiquette"}
    assert t["parent"] == "mere" and t["enfants"] == ["petit"]
    r = client.get("/api/taches/inconnue")
    assert r.status_code == 404 and r.json()["detail"]


def test_creer_lancer_et_conversation(client, faux):
    r = client.post("/api/taches", headers=H, json={"titre": "Lancée", "description": "fais",
                                                     "conteneur": "Projets/C1-Alpha",
                                                     "lancer": True})
    assert r.status_code == 201
    ident = r.json()["id"]
    attendre_inactif(client, ident)
    t = client.get(f"/api/taches/{ident}").json()
    assert t["statut"] == "retour-humain" and t["session"] == "s-1"
    assert faux.lances[0]["message"] == "fais"
    conv = client.get(f"/api/taches/{ident}/conversation").json()
    assert conv == [{"role": "assistant", "texte": "bonjour s-1", "outils": ["Read"],
                     "horodatage": "2026-11-12T10:00:00", "secondaire": False, "dernier": True}]  # INV-RETOUR-1 : « Répondre à partir d’ici »
    assert client.get("/api/taches/mere/conversation").json() == []


def test_entrees_invalides_400(client):
    assert client.post("/api/taches", headers=H, json={}).status_code == 400
    assert client.post("/api/taches/mere/statut", headers=H,
                       json={"statut": "nimporte"}).status_code == 400
    assert client.post("/api/taches/mere/deplacer", headers=H, json={}).status_code == 400
    assert client.post("/api/taches/mere/session", headers=H,
                       json={"session": "../../etc"}).status_code == 400
    assert client.post("/api/taches", headers=H, json={"titre": "x", "conteneur": "../x"}
                       ).status_code == 404  # INV-VAULT-3


def test_conflits_409(client, racine):
    (racine / "_meta/taches/pc.md").write_text("---\nstatut: a-faire\npaperclip: 1\n---\n",
                                               encoding="utf-8")
    assert client.post("/api/taches/pc/statut", headers=H,
                       json={"statut": "fait"}).status_code == 409
    assert client.post("/api/taches/mere/deriver", headers=H, json={
        "titre": "f", "lien": "enfant", "avec_fil": True}).status_code == 409
    assert client.post("/api/taches/mere/natif", headers=H).status_code == 409
    assert client.post("/api/taches/mere/messages", headers=H,
                       json={"texte": "x", "sauts": 99}).status_code == 409


def test_statut_deplacer_deriver_promouvoir(client, config):
    config.vault.taches.append("Projets/*/*/taches/*.md")
    assert client.post("/api/taches/mere/statut", headers=H,
                       json={"statut": "fait"}).json()["statut"] == "fait"
    t = client.post("/api/taches/x/deplacer", headers=H, json={"parent": "mere"}).json()
    assert t["parent"] == "mere" and t["conteneur"] == "Projets/C1-Alpha"
    t = client.post("/api/taches/x/deplacer", headers=H,
                    json={"conteneur": "Projets/C2-Beta"}).json()
    assert t["conteneur"] == "Projets/C2-Beta" and t["parent"] is None
    r = client.post("/api/taches/enfant/deriver", headers=H,
                    json={"titre": "Sœur", "lien": "soeur", "avec_fil": False})
    assert r.status_code == 201 and r.json()["parent"] == "mere"
    r = client.post("/api/taches/enfant/promouvoir", headers=H,
                    json={"nom": "Gros", "decouper": False}).json()
    assert r["conteneur"] == "Projets/C1-Alpha/Gros"
    assert r["tache"]["conteneur"] == "Projets/C1-Alpha/Gros"


def test_session_et_interface_native(client, monkeypatch):
    ouverts = []

    async def jamais_ferme(fichier_pid, demarrage_s=0):
        await asyncio.Event().wait()

    monkeypatch.setattr(natif, "ouvrir_onglet", lambda t, d, a: ouverts.append(a))
    monkeypatch.setattr(natif, "attendre_fin", jamais_ferme)
    t = client.post("/api/taches/mere/session", headers=H, json={"session": "abc-1"}).json()
    assert t["session"] == "abc-1"
    r = client.post("/api/taches/mere/natif", headers=H)
    assert r.json() == {"tache": "mere", "harnais": "faux", "session": "abc-1"}
    assert len(ouverts) == 1 and ouverts[0][-2] == "natif"


def test_entetes_anti_clickjacking_sur_toutes_les_reponses(client):
    reponses = [client.get("/"), client.get("/api/arbre"),
                client.get("/api/arbre", headers={"Host": "evil.com:8399"}),
                client.post("/api/taches", json={"titre": "x"})]
    assert [r.status_code for r in reponses] == [200, 200, 403, 403]
    for r in reponses:
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_arret_du_serveur_tue_les_tours_et_garde_la_trace(config, vault, faux):
    from orchestrateur.harnais import Evenement
    faux.scenario = [Evenement("session", session="s"), "attendre"]
    m = Moteur(config, vault, {"faux": faux})
    with TestClient(api.creer_app(config, m), base_url=BASE) as c:
        c.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
        for _ in range(200):
            if m.tours:
                break
            time.sleep(0.01)
        assert m.tours
    assert len(faux.arrets) >= 1  # INV-EXEC-1 : aucun processus ne survit au serveur
    fichier = config.donnees / "etat" / "tours.json"
    assert [x["tache"] for x in json.loads(fichier.read_text("utf-8"))] == ["mere"]
    assert Moteur(config, vault, {"faux": faux}).etat_de("mere") == "interrompu"


def test_messages_et_arret(client):
    r = client.post("/api/taches/mere/messages", headers=H, json={"texte": "go"})
    assert r.status_code == 202 and r.json()["etat_execution"] in ("en_file", "en_cours")
    attendre_inactif(client, "mere")
    r = client.post("/api/taches/mere/arret", headers=H)
    assert r.json() == {"etat_execution": "inactif"}


def test_propositions_api(client):
    r = client.post("/api/propositions", headers=H,
                    json={"type": "deplacer", "tache": "x", "valeur": "Projets/C2-Beta",
                          "de": "mere"})
    assert r.status_code == 201
    p = r.json()  # INV-PROP-1 : déplacer est un geste de routine, appliqué d'office
    assert {"n", "type", "tache", "valeur", "de", "motif", "etat", "cree", "auto", "avant"} <= set(p)
    assert p["etat"] == "acceptee" and p["auto"] is True
    assert client.get("/api/taches/x").json()["conteneur"] == "Projets/C2-Beta"
    assert client.post(f"/api/propositions/{p['n']}/refuser", headers=H).status_code == 409
    assert client.post(f"/api/propositions/{p['n']}/annuler", headers=H).json()["etat"] == "annulee"
    assert client.get("/api/taches/x").json()["conteneur"] != "Projets/C2-Beta"
    assert client.post(f"/api/propositions/{p['n']}/annuler", headers=H).status_code == 409
    assert client.post("/api/propositions/42/refuser", headers=H).status_code == 404


def test_flux_sse_sur_vrai_serveur(config, vault, faux):
    # TestClient met la réponse entière en tampon : un flux infini exige un vrai serveur.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        config.port = s.getsockname()[1]
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=config.port,
                                            log_level="warning"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    try:
        while not serveur.started:
            time.sleep(0.02)
        base = f"http://127.0.0.1:{config.port}/api"
        with urllib.request.urlopen(base + "/evenements", timeout=10) as flux:
            assert flux.readline() == b": ouvert\n"
            req = urllib.request.Request(base + "/propositions", method="POST", headers={
                "X-Orchestrateur": "1", "Content-Type": "application/json"},
                data=json.dumps({"type": "projet", "tache": "x", "valeur": "P"}).encode())
            urllib.request.urlopen(req, timeout=10).read()
            lignes = [flux.readline() for _ in range(2)]
        assert b'data: {"type": "proposition", "n": 1}\n' in lignes
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)


def test_liens_routes(client):
    r = client.post("/api/taches/mere/liens", headers=H, json={"type": "alimente", "cible": "x"})
    assert r.status_code == 200
    assert r.json()["liens"] == {"alimente": [{"id": "x", "titre": "X", "statut": "a-faire"}],
                                 "alimente_par": [], "prerequis": [], "requis_par": [],
                                 "voir_aussi": []}
    assert client.get("/api/taches/x").json()["liens"]["alimente_par"][0]["id"] == "mere"
    assert client.post("/api/taches/mere/liens", headers=H,
                       json={"type": "alimente", "cible": "x"}).status_code == 409
    assert client.post("/api/taches/x/liens", headers=H,
                       json={"type": "alimente", "cible": "mere"}).status_code == 409
    assert client.post("/api/taches/x/liens", headers=H,
                       json={"type": "autre", "cible": "mere"}).status_code == 400
    client.post("/api/taches/x/liens", headers=H, json={"type": "voir_aussi", "cible": "petit"})
    r = client.post("/api/taches/petit/liens/retirer", headers=H,
                    json={"type": "voir_aussi", "cible": "x"})
    assert r.status_code == 200 and r.json()["liens"]["voir_aussi"] == []
    assert client.post("/api/taches/petit/liens/retirer", headers=H,
                       json={"type": "voir_aussi", "cible": "x"}).status_code == 404
    def taches(ns):
        for n in ns:
            yield from ([n] if n["type"] == "tache" else []) + list(taches(n["enfants"]))

    nombre = {n["id"]: n["liens"] for n in taches(client.get("/api/arbre").json()["noeuds"])}
    assert nombre["mere"] == 1 and nombre["x"] == 1 and nombre["petit"] == 0


def test_recherche_route(client):
    r = client.get("/api/recherche", params={"q": "doublon méta"}).json()
    assert [x["titre"] for x in r] == ["Doublon Meta"]
    assert len(client.get("/api/recherche", params={"q": "doublon", "limite": 1}).json()) == 1


def test_jardinage_routes(client):
    assert client.get("/api/jardinage").json() == {"rythme": "a-la-demande", "prochaine": None,
                                                   "derniere": None, "tache": None}
    r = client.post("/api/jardinage", headers=H)
    assert r.status_code == 202
    ident = r.json()["tache"]
    attendre_inactif(client, ident)
    assert client.get("/api/jardinage").json()["tache"] == ident
    assert client.post("/api/jardinage", headers=H).json()["tache"] == ident
    attendre_inactif(client, ident)


def test_proposition_avec_motif_et_operation_409(client):
    p = client.post("/api/propositions", headers=H, json={
        "type": "operation", "tache": "x", "valeur": "Op", "motif": "regrouper"}).json()
    assert p["motif"] == "regrouper"
    r = client.post(f"/api/propositions/{p['n']}/accepter", headers=H)
    assert r.status_code == 409 and "promouv" in r.json()["detail"]
    assert client.get("/api/propositions").json()[0]["etat"] == "en_attente"


def test_proposition_rattacher_lot_et_cycle_api(client):
    r = client.post("/api/propositions", headers=H, json={"type": "rattacher", "tache": "petit", "valeur": "mere", "taches": ["enfant"]})
    assert r.status_code == 201 and r.json()["taches"] == ["petit", "enfant"]
    r = client.post("/api/propositions", headers=H, json={"type": "rattacher", "tache": "mere", "valeur": "petit"})
    assert r.status_code == 409  # cycle (INV-RATTACHER-1)
