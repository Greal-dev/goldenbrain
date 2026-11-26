"""Bases (étape a) : inférence des types, filtres, tri, groupes, agrégats, garde-fous de la route."""

import json
import os
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire
from orchestrateur import api, bases
from orchestrateur.config import ConfigNotes
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide

H = {"X-Orchestrateur": "1"}
LOYERS = {
    "janvier": "montant: 800\ndate: 2026-01-05\nlocataire: \"[[Durand]]\"\npaye: true\ntags: [loyer, a]\n",
    "fevrier": "montant: 800\ndate: 2026-02-05\nlocataire: \"[[Durand]]\"\npaye: false\ntags: [loyer]\n",
    "mars": "montant: -120.5\ndate: 2026-03-05\nlocataire: \"[[Martin]]\"\npaye: true\n",
    "avril": "date: 2026-04-05\nlocataire: \"[[Martin]]\"\npaye: true\ntitre: Avril régularisé\n",
    "mai": "montant: 650\nlocataire: libre\n",
}


def _base(racine):
    for nom, fm in LOYERS.items():
        ecrire(racine, f"Base/{nom}.md", f"---\n{fm}---\n# Corps {nom}\n")
    ecrire(racine, "Base/Sous/cachee.md", "---\nmontant: 1\n---\n")  # non récursif
    ecrire(racine, "Base/.brouillon.md", "---\nmontant: 1\n---\n")
    ecrire(racine, "Base/image.png", "png")


def _lignes(racine):
    return bases.lire(racine / "Base", "Base", [])[0]


def test_inference_des_types_par_colonne(racine):
    _base(racine)
    cols = {c["nom"]: c for c in bases.colonnes(_lignes(racine))}
    assert {n: c["type"] for n, c in cols.items()} == {
        "montant": "nombre", "date": "date", "locataire": "texte", "paye": "case", "tags": "liste",
        "titre": "texte"}
    assert cols["tags"]["valeurs"] == ["a", "loyer"]
    assert "somme" in cols["montant"]["agregats"] and "cochees" in cols["paye"]["agregats"]
    assert bases.inferer(["[[A]]", "[[B|b]]", None]) == "lien"
    assert bases.inferer([1, "deux"]) == "texte" and bases.inferer([True, 1]) == "texte"
    assert bases.inferer(["2026-01-01T10:00:00", "2026-02-01"]) == "date"


def test_lecture_non_recursive_titre_et_fichiers_ignores(racine):
    _base(racine)
    lignes, total = bases.lire(racine / "Base", "Base", [])
    assert total == 5 and [l["chemin"] for l in lignes][0] == "Base/avril.md"
    assert {l["titre"] for l in lignes} >= {"Avril régularisé", "mai"}


def test_somme_ignore_valeurs_manquantes_et_compte_les_negatifs(racine):
    _base(racine)
    t = bases.calculer(_lignes(racine))
    m = t["agregats"]["montant"]
    assert m["somme"] == 800 + 800 - 120.5 + 650 and m["compte"] == 4
    assert m["min"] == -120.5 and m["max"] == 800 and m["moyenne"] == pytest.approx(2129.5 / 4)
    assert t["agregats"]["paye"]["cochees"] == 3 and t["agregats"]["locataire"]["distincts"] == 3
    assert t["agregats"]["tags"]["distincts"] == 2
    assert t["agregats"]["date"]["min"] == "2026-01-05"


def test_tri_croissant_decroissant_absents_en_fin(racine):
    _base(racine)
    asc = bases.calculer(_lignes(racine), tri="montant")["lignes"]
    assert [l["valeurs"].get("montant") for l in asc] == [-120.5, 650, 800, 800, None]
    desc = bases.calculer(_lignes(racine), tri="-montant")["lignes"]
    assert [l["valeurs"].get("montant") for l in desc] == [800, 800, 650, -120.5, None]
    par_titre = bases.calculer(_lignes(racine), tri="-titre")["lignes"]
    assert par_titre[0]["titre"] == "mars"


def test_filtres_par_type(racine):
    _base(racine)
    lignes = _lignes(racine)

    def noms(filtres):
        return sorted(l["chemin"][5:-3] for l in bases.calculer(lignes, filtres)["lignes"])

    assert noms([{"colonne": "montant", "op": ">=", "valeur": "700"}]) == ["fevrier", "janvier"]
    assert noms([{"colonne": "montant", "op": "<=", "valeur": 0}]) == ["mars"]
    assert noms([{"colonne": "date", "op": ">=", "valeur": "2026-02-01"},
                 {"colonne": "date", "op": "<=", "valeur": "2026-03-05"}]) == ["fevrier", "mars"]
    assert noms([{"colonne": "paye", "op": "=", "valeur": False}]) == ["fevrier"]
    assert noms([{"colonne": "paye", "op": "=", "valeur": True}]) == ["avril", "janvier", "mars"]
    assert noms([{"colonne": "locataire", "op": "contient", "valeur": "mart"}]) == ["avril", "mars"]
    assert noms([{"colonne": "tags", "op": "a", "valeur": "a"}]) == ["janvier"]
    with pytest.raises(Invalide):
        bases.calculer(lignes, [{"colonne": "paye", "op": ">=", "valeur": 1}])
    with pytest.raises(Invalide):
        bases.calculer(lignes, [{"colonne": "montant", "op": ">=", "valeur": "beaucoup"}])


def test_groupes_avec_sous_totaux_dans_l_ordre(racine):
    _base(racine)
    t = bases.calculer(_lignes(racine), tri="date", groupe="locataire")
    g = {x["valeur"]: x for x in t["groupes"]}
    assert [x["valeur"] for x in t["groupes"]] == ["[[Durand]]", "[[Martin]]", "libre"]
    assert g["[[Durand]]"]["agregats"]["montant"]["somme"] == 1600
    assert g["[[Martin]]"]["agregats"]["montant"]["somme"] == -120.5
    assert [t["lignes"][i]["chemin"] for i in g["[[Martin]]"]["lignes"]] == ["Base/mars.md", "Base/avril.md"]
    sans = bases.calculer(_lignes(racine), groupe="montant")["groupes"]
    assert sans[-1]["valeur"] is None and len(sans[-1]["lignes"]) == 1


def test_troncature_au_plafond(racine):
    _base(racine)
    t = bases.table(racine / "Base", "Base", [], plafond=2)
    assert t["tronque"] and t["total"] == 5 and len(t["lignes"]) == 2


def test_lecture_seule_aucun_octet_modifie(racine):
    _base(racine)
    avant = {p: p.read_bytes() for p in (racine / "Base").glob("*.md")}
    bases.table(racine / "Base", "Base", [], tri="montant", groupe="locataire")
    assert {p: p.read_bytes() for p in avant} == avant


@pytest.fixture
def client(config, vault, faux, racine):
    _base(racine)
    ecrire(racine, "Prive/secret.md", "---\nmontant: 1\n---\n")
    config.notes = ConfigNotes(exclure=["Prive"], ttl_s=0.2)
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url="http://127.0.0.1:8399") as c:
        yield c


def test_route_table_filtre_tri_groupe(client):
    f = quote(json.dumps([{"colonne": "paye", "op": "=", "valeur": True}]))
    r = client.get(f"/api/bases/table?dossier=Base&filtres={f}&tri=-montant&groupe=locataire", headers=H)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dossier"] == "Base" and d["total"] == 5 and d["filtrees"] == 3 and not d["tronque"]
    assert [l["chemin"] for l in d["lignes"]] == ["Base/janvier.md", "Base/mars.md", "Base/avril.md"]
    assert d["agregats"]["montant"]["somme"] == 800 - 120.5 and len(d["groupes"]) == 2


@pytest.mark.parametrize("dossier", ["..", "../vault/Base", "Base/../..", "/etc", "Prive", ".obsidian", "Absent"])
def test_route_traversee_et_exclus_refuses(client, dossier):
    assert client.get(f"/api/bases/table?dossier={quote(dossier)}", headers=H).status_code == 404


def test_route_lien_symbolique_sortant_refuse(client, racine, tmp_path):
    dehors = tmp_path / "dehors"
    ecrire(dehors, "x.md", "---\nmontant: 1\n---\n")
    try:
        os.symlink(dehors, racine / "Lien", target_is_directory=True)
    except OSError:
        pytest.skip("liens symboliques indisponibles")
    assert client.get("/api/bases/table?dossier=Lien", headers=H).status_code == 404


def test_route_filtres_illisibles_400(client):
    assert client.get("/api/bases/table?dossier=Base&filtres=pas-du-json", headers=H).status_code == 400
    assert client.get("/api/bases/table?dossier=Base&groupe=inconnue", headers=H).status_code == 400
