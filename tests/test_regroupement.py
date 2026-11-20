"""Exécution par tâche ou regroupée sous la mère (INV-REGROUPE-1, INV-REGROUPE-2, INV-REGROUPE-3)."""

import time

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, cli, fiches, regroupement
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
P = "Projets/C1-Gamma"


def famille(racine, *, prerequis=True, extra=None, ctx=""):
    """Mère M et trois sous-tâches A → B → C (prérequis enchaînés si demandé)."""
    ecrire(racine, f"{P}/contexte.md", f"---\ntype: contexte\ncasquette: C1-Pro\nnom: Gamma\n{ctx}---\n")
    ecrire(racine, f"{P}/taches/m.md", tache_md(statut="en-cours", titre="Mère M", extra=(extra or {}).get("m", "")))
    for k, req in (("a", ""), ("b", "a"), ("c", "b")):
        lien = f"prerequis: [{req}]\n" if prerequis and req else ""
        ecrire(racine, f"{P}/taches/{k}.md",
               tache_md(titre=f"Sous {k.upper()}", extra=f"parent: m\n{lien}{(extra or {}).get(k, '')}"))


@pytest.fixture
def moteur(config, vault, faux):
    return Moteur(config, vault, {"faux": faux, "autre": faux})


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def attendre(client, ident, etat="inactif"):
    for _ in range(300):
        if client.get(f"/api/taches/{ident}").json()["etat_execution"] == etat:
            return
        time.sleep(0.01)
    raise AssertionError(f"{ident} jamais {etat}")


# --- règle automatique -------------------------------------------------------------------
def test_petites_et_enchainees_regroupees(racine, moteur):
    famille(racine)
    d = regroupement.decider(moteur, "b")
    assert (d.mode, d.parent) == ("regroupee", "m")
    assert d.motif == "Regroupée sous « Mère M » : 3 sous-tâches petites et enchaînées"
    assert regroupement.decider(moteur, "m") is None  # sans mère : rien à décider


def test_independantes_une_conversation_par_tache(racine, moteur):
    famille(racine, prerequis=False)
    d = regroupement.decider(moteur, "a")
    assert d.mode == "par_tache" and "indépendantes" in d.motif


@pytest.mark.parametrize("extra, attendu", [
    ({"b": "epreuves: lourdes\n"}, "dont 1 lourde"),
    ({"c": "taille: L\n"}, "dont 1 lourde"),
    ({"b": "harnais: autre\n"}, "« Sous B » exige un autre assistant IA ou modèle"),
    ({"a": "branche: gb/a\n"}, "« Sous A » a sa propre version du code"),
])
def test_lourde_ou_isolee_une_conversation_par_tache(racine, moteur, extra, attendu):
    famille(racine, extra=extra)
    d = regroupement.decider(moteur, "a")
    assert d.mode == "par_tache" and attendu in d.motif, d.motif


def test_ram_insuffisante_regroupe_meme_independantes(racine, moteur, monkeypatch):
    famille(racine, prerequis=False)
    monkeypatch.setattr(moteur._sem, "regule", lambda: True)
    monkeypatch.setattr(moteur._sem, "mesure", object())
    monkeypatch.setattr(moteur._sem, "depasse", lambda m, en_plus=0: True)
    d = regroupement.decider(moteur, "a")
    assert d.mode == "regroupee" and "mémoire vive" in d.motif
    famille(racine, prerequis=False, extra={"a": "harnais: autre\n"})
    assert regroupement.decider(moteur, "a").mode == "par_tache"  # l'isolation prime


def test_reglage_herite_du_conteneur_et_surcharge_par_la_mere(racine, moteur):
    famille(racine, prerequis=False, ctx="execution: regroupee\n")
    d = regroupement.decider(moteur, "a")
    assert (d.mode, d.reglage, d.origine) == ("regroupee", "regroupee", "Gamma")
    assert "réglage « regroupée sous la mère » posé sur Gamma" in d.motif
    regroupement.regler(moteur, "m", "par_tache")
    assert regroupement.decider(moteur, "a").mode == "par_tache"
    assert fiches.frontmatter(fiches.lire(racine / P / "taches/m.md"))["execution"] == "par_tache"
    regroupement.regler(moteur, "m", "")  # hériter à nouveau
    assert regroupement.decider(moteur, "a").mode == "regroupee"


def test_reglage_d_un_conteneur_par_l_api(client, racine):
    famille(racine)
    r = client.put("/api/execution", headers=H, json={"noeud": P, "reglage": "par_tache"})
    assert r.status_code == 200 and r.json()["reglage"] == "par_tache"
    texte = fiches.lire(racine / P / "contexte.md")
    assert "execution: par_tache" in texte and "nom: Gamma" in texte  # INV-VAULT-1 : reste intact
    assert client.get(f"/api/taches/b").json()["execution"]["decision"]["mode"] == "par_tache"
    assert client.put("/api/execution", headers=H, json={"noeud": P, "reglage": "x"}).status_code == 400
    assert client.put("/api/execution", headers=H,
                      json={"noeud": "Projets/Sans", "reglage": "par_tache"}).status_code == 409


# --- mode regroupé -------------------------------------------------------------------------
def test_message_a_une_sous_tache_achemine_vers_la_mere(client, racine, faux):
    famille(racine)
    r = client.post("/api/taches/b/messages", headers=H, json={"texte": "avance B"})
    assert r.status_code == 202
    attendre(client, "m")
    assert len(faux.lances) == 1 and faux.lances[0]["env"]["ORCH_TACHE"] == "m"
    msg = faux.lances[0]["message"]
    assert "Pour la sous-tâche « Sous B » (id b" in msg and "avance B" in msg
    assert msg.index("1. Sous A") < msg.index("2. Sous B") < msg.index("3. Sous C")  # ordonnancement
    conv = client.get("/api/taches/b/conversation").json()
    assert any(m["role"] == "systeme" and "acheminé vers la conversation de « Mère M »" in m["texte"]
               for m in conv)
    assert not fiches.frontmatter(fiches.lire(racine / P / "taches/b.md")).get("session")


def test_message_de_la_mere_elle_meme_non_reachemine(client, racine, faux):
    famille(racine)
    client.post("/api/taches/a/messages", headers=H, json={"texte": "à toi", "de": "m"})
    attendre(client, "a")  # (b attendrait son prérequis a : INV-ORDO-1)
    assert faux.lances[0]["env"]["ORCH_TACHE"] == "a"


def test_fiche_d_une_sous_tache_ecrite_par_la_mere_seule(client, racine):
    famille(racine)
    corps = {"de": "m", "statut": "terminee", "fait": "B écrite", "situation": "prête"}
    r = client.post("/api/taches/b/fiche-regroupee", headers=H, json=corps)
    assert r.status_code == 200 and r.json()["statut"] == "fait"
    t = client.get("/api/taches/b").json()
    assert t["statut"] == "fait" and t["fiche"]["fait"] == "B écrite"
    conv = client.get("/api/taches/b/conversation").json()
    assert any("Fiche mise à jour par la conversation de « Mère M »" in m["texte"] for m in conv)
    autre = client.post("/api/taches/c/fiche-regroupee", headers=H, json={**corps, "de": "a"})
    assert autre.status_code == 409 and fiches.frontmatter(fiches.lire(racine / P / "taches/c.md"))["statut"] == "a-faire"


def test_repere_ia_au_travail_sur_la_sous_tache_portee(client, racine, faux):
    import asyncio
    famille(racine)
    faux.scenario = ["attendre"] + faux.scenario
    faux.liberer = asyncio.Event()
    client.post("/api/taches/c/messages", headers=H, json={"texte": "avance C"})
    attendre(client, "c", "en_cours")
    assert "c" in client.get("/api/etat").json()["occupees"]
    assert client.get("/api/taches/a").json()["etat_execution"] == "inactif"
    client.post("/api/taches/m/arret", headers=H)
    attendre(client, "c", "inactif")


def test_bascule_reprend_la_conversation_propre_de_la_sous_tache(client, racine, faux):
    famille(racine, extra={"a": "session: s-propre-a\n"})
    client.post("/api/taches/a/messages", headers=H, json={"texte": "un"})
    attendre(client, "m")
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == "m"
    client.put("/api/execution", headers=H, json={"noeud": "m", "reglage": "par_tache"})
    client.post("/api/taches/a/messages", headers=H, json={"texte": "deux"})
    attendre(client, "a")
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == "a" and faux.lances[-1]["session"] == "s-propre-a"
    propre = fiches.frontmatter(fiches.lire(racine / P / "taches/a.md"))["session"]
    client.put("/api/execution", headers=H, json={"noeud": "m", "reglage": "regroupee"})
    client.post("/api/taches/a/messages", headers=H, json={"texte": "trois"})
    attendre(client, "m")
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == "m"
    assert fiches.frontmatter(fiches.lire(racine / P / "taches/a.md"))["session"] == propre  # intacte


def test_orch_fiche_depuis_la_conversation_de_la_mere(monkeypatch, capsys):
    appels = []
    monkeypatch.setenv("ORCH_TACHE", "m")
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: appels.append((m, c, corps)) or {"statut": "en-cours"})
    assert cli.main(["fiche", "b", "--statut", "en_cours", "--fait", "x", "--prochain-pas", "y"]) == 0
    m, chemin, corps = appels[0]
    assert (m, chemin, corps["de"], corps["fait"], corps["prochain_pas"]) == ("POST", "/taches/b/fiche-regroupee", "m", "x", "y")
    monkeypatch.delenv("ORCH_TACHE")
    assert cli.main(["fiche", "b"]) == 1
