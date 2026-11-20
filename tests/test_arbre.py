"""Lot 4 — arbre libre : chemins `A > B`, conteneur sous conteneur, cycles, gestes, INV-ARBRE-1."""

import logging

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, arbre, fiches
from orchestrateur.config import ConfigVault
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, NonTrouve, Vault
from conftest import ecrire, tache_md

H = {"X-Orchestrateur": "1"}
CTX_ORION = ("﻿---\r\ntype: contexte\r\ncasquette: C1\r\nstatus: actif 🚀\r\n"
             "créé: 2026-01-01\r\nparent: Produits\r\n---\r\n\r\n# ORION 🚀\r\n")


def faire(tmp_path, fichiers: dict) -> Vault:
    r = tmp_path / "v"
    for rel, texte in fichiers.items():
        ecrire(r, rel, texte)
    return Vault(ConfigVault(racine=r, taches=["Projets/*/taches/*.md", "_meta/taches/*.md"]))


def ctx(cas="C1", parent=None, extra="") -> str:
    return f"---\ntype: contexte\ncasquette: {cas}\n" + (f"parent: {parent}\n" if parent else "") \
        + extra + "---\n"


def lire(v: Vault, conteneur: str) -> str:
    return (v.racine / f"Projets/{conteneur}/contexte.md").read_bytes().decode("utf-8")


def projeter(noeuds):
    return [[n["id"], n["type"], n["titre"], n["ouvertes"], projeter(n["enfants"])] for n in noeuds]


def trouver(noeuds, ident):
    for n in noeuds:
        if n["id"] == ident:
            return n
        if (x := trouver(n["enfants"], ident)) is not None:
            return x
    return None


def chemin_de(noeuds, ident, pile=()):
    for n in noeuds:
        if n["id"] == ident:
            return [*pile, ident]
        if x := chemin_de(n["enfants"], ident, (*pile, n["id"])):
            return x
    return None


@pytest.fixture
def v(tmp_path):
    """C1 : TG (sans parent) ; opération Produits > ORION (+ Sub sous ORION) ; Produits > Annexes
    > Docs ; Nu sans contexte. C2 : Patri."""
    return faire(tmp_path, {
        "Projets/TG/contexte.md": ctx(),
        "Projets/TG/taches/tg1.md": tache_md(titre="TG un"),
        "Projets/ORION/contexte.md": CTX_ORION,
        "Projets/ORION/taches/ti1.md": tache_md(titre="Ti un"),
        "Projets/ORION/taches/ti2.md": tache_md(extra="parent: ti1\n", titre="Ti deux"),
        "Projets/ORION/taches/ti3.md": tache_md(extra="parent: ti2\nupdated: 2020-01-01\n",
                                                titre="Ti trois"),
        "Projets/Sub/contexte.md": ctx(parent="Produits > ORION"),
        "Projets/Sub/taches/su1.md": tache_md(extra="casquette: C1-Pro\n", titre="Su un"),
        "Projets/Docs/contexte.md": ctx(parent="Produits > Annexes", extra="updated: 2020-01-01\n"),
        "Projets/Docs/taches/do1.md": tache_md(titre="Do un"),
        "Projets/Docs/taches/do2.md": tache_md(extra="parent: do1\n", titre="Do deux"),
        "Projets/Nu/taches/nu1.md": tache_md(extra="casquette: C1\n", titre="Nu un"),
        "Projets/Patri/contexte.md": ctx("C2"),
        "Projets/Patri/taches/pa1.md": tache_md(titre="Pa un"),
    })


def octets(v: Vault) -> dict:
    return {p: p.read_bytes() for p in v.racine.rglob("*.md")}


# --- lecture -----------------------------------------------------------------------------
def test_parents_a_un_segment_donnent_l_arbre_d_avant(tmp_path):
    # Référence produite par le code d'avant le lot 4 sur ce même vault.
    vt = faire(tmp_path, {
        "Projets/C1-Alpha/contexte.md": "---\ntype: contexte\ncasquette: C1-Pro\n"
                                        "parent: \"[[Operation-X]]\"\nnom: Alpha\n---\n",
        "Projets/C1-Alpha/taches/mere.md": tache_md(titre="Mère"),
        "Projets/C1-Alpha/taches/enfant.md": tache_md(extra='parent: "[[mere]]"\n', titre="Enfant"),
        "Projets/C1-Gamma/contexte.md": ctx(parent="Operation-X"),
        "Projets/C1-Gamma/taches/g.md": tache_md(titre="G"),
        "Projets/C1-Delta/contexte.md": ctx(parent="Autre op"),
        "Projets/C1-Delta/taches/d.md": tache_md(titre="D"),
        "Projets/C1-Zeta/contexte.md": ctx(),
        "Projets/C1-Zeta/taches/z.md": tache_md(titre="Z"),
        "Projets/C1-Zeta/taches/zf.md": tache_md(statut="fait", titre="ZF"),
        "Projets/C2-Beta/contexte.md": ctx("C2-Patrimoine"),
        "Projets/C2-Beta/taches/b.md": tache_md(titre="B"),
        "Projets/Sans/taches/x.md": tache_md(extra="casquette: META\n", titre="X"),
        "_meta/taches/m.md": tache_md(statut="fait", titre="M"),
    })
    c1 = ["casquette:C1", "casquette", "C1", 5, [
        ["Projets/C1-Zeta", "conteneur", "C1-Zeta", 1, [["z", "tache", "Z", 1, []]]],
        ["operation:C1/Autre op", "operation", "Autre op", 1,
         [["Projets/C1-Delta", "conteneur", "C1-Delta", 1, [["d", "tache", "D", 1, []]]]]],
        ["operation:C1/Operation-X", "operation", "Operation-X", 3, [
            ["Projets/C1-Alpha", "conteneur", "Alpha", 2,
             [["mere", "tache", "Mère", 2, [["enfant", "tache", "Enfant", 1, []]]]]],
            ["Projets/C1-Gamma", "conteneur", "C1-Gamma", 1, [["g", "tache", "G", 1, []]]]]]]]
    c2 = ["casquette:C2", "casquette", "C2", 1,
          [["Projets/C2-Beta", "conteneur", "C2-Beta", 1, [["b", "tache", "B", 1, []]]]]]
    meta = ["casquette:META", "casquette", "META", 1,
            [["Projets/Sans", "conteneur", "Sans", 1, [["x", "tache", "X", 1, []]]]]]
    assert projeter(vt.arbre(False)) == [c1, c2, meta]
    toutes = projeter(vt.arbre(True))
    assert toutes[0] == ["casquette:?", "casquette", "?", 0, [
        ["_meta", "conteneur", "_meta", 0, [["m", "tache", "M", 0, []]]]]]
    assert toutes[1][4][0][4] == [["z", "tache", "Z", 1, []], ["zf", "tache", "ZF", 0, []]]
    assert vt.conteneur("Projets/C1-Alpha").operation == "Operation-X"


def test_operation_imbriquee_deux_et_trois_niveaux(tmp_path):
    vt = faire(tmp_path, {
        "Projets/A/contexte.md": ctx(parent="Atelier > ORION"),
        "Projets/A/taches/a.md": tache_md(titre="A"),
        "Projets/B/contexte.md": ctx(parent="[[atelier]]  >  orion > Lot 2"),
        "Projets/B/taches/b.md": tache_md(titre="B"),
    })
    noeuds = vt.arbre(False)
    assert chemin_de(noeuds, "a") == ["casquette:C1", "operation:C1/Atelier",
                                      "operation:C1/Atelier > ORION", "Projets/A", "a"]
    assert chemin_de(noeuds, "b") == ["casquette:C1", "operation:C1/Atelier",
                                      "operation:C1/Atelier > ORION",
                                      "operation:C1/Atelier > ORION > Lot 2", "Projets/B", "b"]
    assert vt.conteneur("Projets/B").chemin == ["atelier", "orion", "Lot 2"]


def test_conteneur_sous_conteneur_porte_ses_taches_et_ses_sous_elements(tmp_path):
    vt = faire(tmp_path, {
        "Projets/Atelier/contexte.md": ctx(),
        "Projets/Atelier/taches/tg.md": tache_md(titre="TG"),
        "Projets/ORION/contexte.md": ctx(parent="atelier"),
        "Projets/ORION/taches/ti.md": tache_md(titre="Ti"),
        "Projets/Sub/contexte.md": ctx(parent="Atelier > ORION"),
        "Projets/Sub/taches/su.md": tache_md(titre="Su"),
        "Projets/W/contexte.md": ctx(parent="Ailleurs > Atelier > Chantier"),
        "Projets/W/taches/w.md": tache_md(titre="W"),
        "Projets/Vide/contexte.md": ctx(parent="Atelier"),
    })
    tg = trouver(vt.arbre(False), "Projets/Atelier")
    assert [e["id"] for e in tg["enfants"]] == [
        "tg", "Projets/ORION", "operation:C1/Atelier > Chantier"]
    assert tg["ouvertes"] == 4
    orion = tg["enfants"][1]
    assert [e["id"] for e in orion["enfants"]] == ["ti", "Projets/Sub"]
    assert trouver(tg["enfants"], "w") is not None


def test_cycle_coupe_a_la_lecture_et_journalise(tmp_path, caplog):
    vt = faire(tmp_path, {
        "Projets/A/contexte.md": ctx(parent="B"), "Projets/A/taches/a.md": tache_md(titre="A"),
        "Projets/B/contexte.md": ctx(parent="A"), "Projets/B/taches/b.md": tache_md(titre="B"),
        "Projets/S/contexte.md": ctx(parent="Op > S"), "Projets/S/taches/s.md": tache_md(titre="S"),
    })
    with caplog.at_level(logging.WARNING):
        noeuds = vt.arbre(False)
    assert chemin_de(noeuds, "b") == ["casquette:C1", "Projets/A", "Projets/B", "b"]
    assert chemin_de(noeuds, "s") == ["casquette:C1", "Projets/S", "s"]
    assert "Projets/A" in caplog.text and "Projets/S" in caplog.text


def test_fil_d_ariane_suit_le_chemin_complet(v):
    d = v.detail("do2")
    assert d["fil_ariane"] == ["C1", "Produits", "Annexes", "Docs", "Do un"]
    assert d["fil"] == [
        {"id": "casquette:C1", "type": "casquette", "titre": "C1"},
        {"id": "operation:C1/Produits", "type": "operation", "titre": "Produits"},
        {"id": "operation:C1/Produits > Annexes", "type": "operation", "titre": "Annexes"},
        {"id": "Projets/Docs", "type": "conteneur", "titre": "Docs"},
        {"id": "do1", "type": "tache", "titre": "Do un"}]
    noeuds = v.arbre(True)
    assert all(trouver(noeuds, x["id"]) for x in d["fil"])  # mêmes identifiants que l'arbre
    assert v.fil_ariane("su1") == ["C1", "Produits", "ORION", "Sub"]


def test_deplacable_et_montable(v):
    n = v.arbre(True)
    vu = {k: (trouver(n, k)["deplacable"], trouver(n, k)["montable"]) for k in (
        "casquette:C1", "Projets/TG", "Projets/ORION", "Projets/Nu", "operation:C1/Produits",
        "operation:C1/Produits > Annexes", "ti1", "ti2")}
    assert vu == {"casquette:C1": (False, False), "Projets/TG": (True, False),
                  "Projets/ORION": (True, True), "Projets/Nu": (False, False),
                  "operation:C1/Produits": (True, False),
                  "operation:C1/Produits > Annexes": (True, True),
                  "ti1": (True, False), "ti2": (True, True)}


# --- gestes ------------------------------------------------------------------------------
def test_tache_sur_tache_et_sur_conteneur_reutilisent_l_existant(v):
    arbre.deplacer(v, "tg1", "ti3")
    assert v.tache("tg1").parent_brut == "ti3" and v.tache("tg1").conteneur == "Projets/ORION"
    arbre.deplacer(v, "ti2", "Projets/Patri")
    assert v.tache("ti3").conteneur == "Projets/Patri" and v.tache("ti2").parent_brut is None
    assert v.tache("ti2").fm["casquette"] == "C2"


@pytest.mark.parametrize("sous", ["operation:C1/Produits", "casquette:C2"])
def test_tache_sur_operation_ou_casquette_409(v, sous):
    with pytest.raises(Conflit, match="vit dans un projet"):
        arbre.deplacer(v, "tg1", sous)


def test_conteneur_sous_operation_puis_sous_conteneur(v):
    arbre.deplacer(v, "Projets/TG", "operation:C1/Produits > Annexes")
    assert "parent: Produits > Annexes\n" in (v.racine / "Projets/TG/contexte.md").read_text("utf-8")
    arbre.deplacer(v, "Projets/Patri", "Projets/Docs")
    texte = (v.racine / "Projets/Patri/contexte.md").read_text("utf-8")
    assert "parent: Produits > Annexes > Docs\n" in texte and "casquette: C1\n" in texte
    assert v.tache("pa1").fm["casquette"] == "C1"
    assert chemin_de(v.arbre(False), "pa1")[-3:] == ["Projets/Docs", "Projets/Patri", "pa1"]


def test_conteneur_sous_casquette_change_la_casquette_de_ses_taches(v):
    avant = octets(v)
    arbre.deplacer(v, "Projets/ORION", "casquette:C2")
    ctx_orion = v.racine / "Projets/ORION/contexte.md"
    # INV-VAULT-1 : ligne `parent` supprimée, `casquette` éditée, le reste intact (BOM, CRLF).
    assert ctx_orion.read_bytes() == CTX_ORION.replace("parent: Produits\r\n", "").replace(
        "casquette: C1", "casquette: C2").encode("utf-8")
    assert {v.tache(k).fm["casquette"] for k in ("ti1", "ti2", "ti3", "su1")} == {"C2"}
    sub = (v.racine / "Projets/Sub/contexte.md").read_text("utf-8")
    assert "parent: ORION\n" in sub and "casquette: C2\n" in sub
    ti3 = (v.racine / "Projets/ORION/taches/ti3.md").read_text("utf-8")
    assert "updated: 2020-01-01" not in ti3  # `updated` existante rafraîchie
    assert "updated:" not in (v.racine / "Projets/ORION/taches/ti1.md").read_text("utf-8")
    assert avant[v.racine / "Projets/Docs/contexte.md"] == \
        (v.racine / "Projets/Docs/contexte.md").read_bytes()
    assert chemin_de(v.arbre(False), "su1") == [
        "casquette:C2", "Projets/ORION", "Projets/Sub", "su1"]


def test_operation_deplacee_avec_tous_ses_conteneurs(v):
    arbre.deplacer(v, "operation:C1/Produits", "Projets/TG")
    assert "parent: TG > Produits\r\n" in lire(v, "ORION")
    assert "parent: TG > Produits > ORION\n" in lire(v, "Sub")
    assert "parent: TG > Produits > Annexes\n" in lire(v, "Docs")
    assert "updated: 2020-01-01" not in lire(v, "Docs")
    assert chemin_de(v.arbre(False), "do1") == [
        "casquette:C1", "Projets/TG", "operation:C1/TG > Produits",
        "operation:C1/TG > Produits > Annexes", "Projets/Docs", "do1"]
    arbre.deplacer(v, "operation:C1/TG > Produits", "casquette:C2")
    assert "parent: Produits\r\n" in lire(v, "ORION") and "casquette: C2\r\n" in lire(v, "ORION")
    assert "parent: Produits > Annexes\n" in lire(v, "Docs")
    assert v.tache("do2").fm["casquette"] == "C2"


def test_operation_sous_operation(v):
    arbre.deplacer(v, "operation:C1/Produits > Annexes", "casquette:C1")
    assert chemin_de(v.arbre(False), "do1")[:2] == ["casquette:C1", "operation:C1/Annexes"]
    arbre.deplacer(v, "operation:C1/Annexes", "operation:C1/Produits")
    assert "parent: Produits > Annexes\n" in \
        (v.racine / "Projets/Docs/contexte.md").read_text("utf-8")


@pytest.mark.parametrize("noeud, sous", [
    ("Projets/ORION", "Projets/ORION"), ("Projets/ORION", "Projets/Sub"),
    ("operation:C1/Produits", "Projets/ORION"),
    ("operation:C1/Produits", "operation:C1/Produits > Annexes")])
def test_depot_sur_soi_ou_sur_un_descendant_409(v, noeud, sous):
    avant = octets(v)
    with pytest.raises(Conflit, match="descendants"):
        arbre.deplacer(v, noeud, sous)
    assert octets(v) == avant


def test_conteneur_sans_contexte_409_et_refus_divers(v):
    with pytest.raises(Conflit, match="créez-la d'abord"):
        arbre.deplacer(v, "Projets/Nu", "operation:C1/Produits")
    with pytest.raises(Conflit, match="casquette ne se déplace"):
        arbre.deplacer(v, "casquette:C1", "casquette:C2")
    with pytest.raises(Conflit, match="sous une tâche"):
        arbre.deplacer(v, "Projets/TG", "tg1")
    with pytest.raises(NonTrouve):
        arbre.deplacer(v, "Projets/TG", "operation:C1/Inconnue")
    with pytest.raises(Conflit, match="descendance"):
        arbre.deplacer(v, "ti1", "ti3")


def test_monter_une_tache(v):
    arbre.monter(v, "ti3")
    assert v.tache("ti3").parent_brut == "ti1"
    arbre.monter(v, "ti2")
    assert v.tache("ti2").parent_brut is None and v.tache("ti2").conteneur == "Projets/ORION"
    with pytest.raises(Conflit, match="pas de mère"):
        arbre.monter(v, "ti1")


def test_monter_conteneur_et_operation(v):
    arbre.monter(v, "Projets/Sub")
    assert "parent: Produits\n" in (v.racine / "Projets/Sub/contexte.md").read_text("utf-8")
    arbre.monter(v, "operation:C1/Produits > Annexes")
    assert "parent: Annexes\n" in (v.racine / "Projets/Docs/contexte.md").read_text("utf-8")
    arbre.monter(v, "Projets/ORION")
    assert v.conteneur("Projets/ORION").chemin == []
    for noeud in ("Projets/TG", "operation:C1/Annexes", "casquette:C1"):
        with pytest.raises(Conflit):
            arbre.monter(v, noeud)


def test_aller_retour_deplacer_puis_monter_rend_le_fichier_d_origine(v):
    ctx_orion = v.racine / "Projets/ORION/contexte.md"
    arbre.deplacer(v, "Projets/ORION", "operation:C1/Produits > Annexes")
    assert "parent: Produits > Annexes\r\n" in lire(v, "ORION")
    arbre.monter(v, "Projets/ORION")
    assert ctx_orion.read_bytes() == CTX_ORION.encode("utf-8")


def test_ecriture_en_echec_au_deuxieme_fichier_restaure_tout(v, monkeypatch):
    avant = octets(v)
    vrai, appels = fiches.ecrire_atomique, []

    def ecrire_puis_casser(p, texte):
        appels.append(p)
        if len(appels) == 2:
            raise OSError("disque plein")
        vrai(p, texte)

    monkeypatch.setattr(fiches, "ecrire_atomique", ecrire_puis_casser)
    with pytest.raises(Conflit, match="geste annulé"):
        arbre.deplacer(v, "operation:C1/Produits", "Projets/TG")
    assert len(appels) == 2 and octets(v) == avant


def test_operation_au_nom_inutilisable_comme_dossier_409_rien_touche(config, vault, faux, racine):
    # INV-ARBRE-2 : l'opération devient un dossier ; « : » est interdit dans un nom de dossier.
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    avant = (racine / "Projets/C1-Alpha/contexte.md").read_bytes()
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        h = {"X-Orchestrateur": "1"}
        n = c.post("/api/propositions", headers=h, json={"type": "operation", "tache": "petit",
                                                          "valeur": "Atelier > Lot: 2"}).json()["n"]
        r = c.post(f"/api/propositions/{n}/accepter", headers=h)
        assert r.status_code == 409 and "inutilisable" in r.json()["detail"]
    assert (racine / "Projets/C1-Alpha/contexte.md").read_bytes() == avant


# --- routes ------------------------------------------------------------------------------
@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        yield c


def test_routes_deplacer_et_monter(client):
    corps = {"noeud": "Projets/C1-Alpha", "sous": "casquette:C2"}
    # INV-ARBRE-2 : un projet ne se déplace plus par un geste logique, mais par plan + application.
    assert client.post("/api/arbre/deplacer", headers=H, json=corps).status_code == 409
    p = client.post("/api/arbre/plan", headers=H, json=corps)
    assert p.status_code == 200 and p.json()["deplacements"] == []  # déjà sous `Projets`
    r = client.post("/api/alignement/appliquer", headers=H,
                    json={"jeton": p.json()["jeton"], "point_git": False})
    assert r.status_code == 200
    noeuds = r.json()["arbre"]["noeuds"]
    assert chemin_de(noeuds, "mere")[:2] == ["casquette:C2", "Projets/C1-Alpha"]
    assert trouver(noeuds, "mere")["liens"] == 0
    r = client.post("/api/arbre/monter", headers=H, json={"noeud": "petit"})
    assert r.status_code == 200 and trouver(r.json()["noeuds"], "mere")["enfants"][1]["id"] == "petit"
    assert client.post("/api/arbre/deplacer", headers=H,
                       json={"noeud": "mere", "sous": "casquette:C2"}).status_code == 409
    assert client.post("/api/arbre/monter", headers=H, json={"noeud": "inconnu"}).status_code == 404
    assert client.post("/api/arbre/deplacer", headers=H, json={"noeud": "mere"}).status_code == 400
    assert client.post("/api/arbre/monter", json={"noeud": "petit"}).status_code == 403
    t = client.get("/api/taches/petit").json()
    assert t["fil"][0] == {"id": "casquette:C2", "type": "casquette", "titre": "C2"}
