"""Étiquettes libres : normalisation, contexte servi à l'agent, pondération du rapprochement, renommage/fusion
annulable, pose en bloc, refus d'un agent, bornage des liens, recherche (INV-ETIQUETTE-1, -2, -3)."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, etiquettes, recherche
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from conftest import ecrire, tache_md

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
HA = {**H, "X-Orch-Tache": "a"}
ALPHA = "Projets/C1-Alpha/taches"


@pytest.fixture
def client(config, vault, faux, racine):
    ecrire(racine, f"{ALPHA}/a.md", tache_md(titre="Cartographier les accès bancaires",
                                              extra="etiquettes: [banque]\n"))
    ecrire(racine, f"{ALPHA}/b.md", tache_md(titre="Rapprocher les relevés bancaires",
                                              extra="etiquettes: [banque, compta]\n"))
    ecrire(racine, f"{ALPHA}/c.md", tache_md(titre="Acheter des ampoules", extra="etiquettes: [maison]\n"))
    ecrire(racine, f"{ALPHA}/d.md", tache_md(titre="Sans étiquette"))
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def ident(client, fin):
    return fin  # l'identifiant d'une tâche est le nom de sa fiche


@pytest.mark.parametrize("brut,attendu", [("  #Éco Nomie ", "eco-nomie"), ("Banque", "banque"), ("a_b", "a_b")])
def test_normaliser_minuscules_sans_accent_ni_espace(brut, attendu):
    assert etiquettes.normaliser(brut) == attendu


def test_normaliser_refuse_vide_et_trop_long():
    with pytest.raises(Invalide):
        etiquettes.normaliser(" # ")
    with pytest.raises(Invalide):
        etiquettes.normaliser("x" * 31)


def test_poser_et_retirer_sans_doublon_par_casse(client, vault):
    i = ident(client, "d")
    r = client.post(f"/api/taches/{i}/etiquettes", json={"ajouter": ["Banque", "banque", "Éco"]}, headers=H)
    assert r.status_code == 200 and r.json()["etiquettes"] == ["banque", "eco"]
    r = client.post(f"/api/taches/{i}/etiquettes", json={"retirer": ["banque", "eco"]}, headers=H)
    assert r.json()["etiquettes"] == [] and "etiquettes" not in vault.tache(i).fm  # clé retirée si vide


def test_tags_du_vocabulaire_ferme_restent_intacts(client, vault):
    i = ident(client, "a")
    client.post(f"/api/taches/{i}/etiquettes", json={"ajouter": ["neuf"]}, headers=H)
    assert vault.tache(i).fm["tags"] == []


def test_agent_ne_cree_pas_une_etiquette_inconnue(client):
    i = ident(client, "d")
    r = client.post(f"/api/taches/{i}/etiquettes", json={"ajouter": ["inventee"]}, headers=HA)
    assert r.status_code in (400, 409, 422) and "banque" in r.json()["detail"]
    assert client.post(f"/api/taches/{i}/etiquettes", json={"ajouter": ["banque"]}, headers=HA).status_code == 200
    assert client.post(f"/api/taches/{i}/etiquettes", json={"retirer": ["banque"]}, headers=HA).status_code == 409


def test_contexte_agent_cite_etiquettes_consigne_et_taches_liees(client, config, vault):
    client.put("/api/etiquettes/banque", json={"consigne": "Ne jamais valider un paiement."}, headers=H)
    t = client.get(f"/api/taches/{ident(client, 'a')}").json()
    assert t["etiquettes"] == ["banque"] and t["consignes_etiquettes"]["banque"].startswith("Ne jamais")
    assert [x["id"] for x in t["liees_etiquette"]] == ["b"]
    texte = etiquettes.texte_tour({k: t[k] for k in ("etiquettes", "consignes_etiquettes", "liees_etiquette")})
    assert "#banque" in texte and "Ne jamais valider" in texte and "Rapprocher les relevés" in texte
    assert etiquettes.texte_tour({"etiquettes": [], "consignes_etiquettes": {}, "liees_etiquette": []}) == ""


def test_orch_lire_rend_les_etiquettes():
    t = {"etiquettes": ["banque"], "consignes_etiquettes": {"banque": "prudence"},
         "liees_etiquette": [{"id": "x", "statut": "a-faire", "titre": "Autre", "situation": "en route",
                              "etiquettes": ["banque"]}]}
    sortie = "\n".join(cli.cli_etiquettes.rendre(t))
    assert "#banque" in sortie and "prudence" in sortie and "x [a-faire] Autre — en route" in sortie


def test_rapprochement_pese_une_etiquette_commune(client):
    sans = client.get("/api/rapprochement/proches", params={"titre": "Rapprocher les accès"}).json()["candidates"]
    avec = client.get("/api/rapprochement/proches",
                      params={"titre": "Rapprocher les accès", "etiquettes": "banque"}).json()["candidates"]
    score = lambda cs, fin: next((c["score"] for c in cs if c["id"] == fin), 0)  # noqa: E731  # sous le seuil : absente
    assert score(avec, "b") > score(sans, "b")
    autre = client.get("/api/rapprochement/proches",
                       params={"titre": "Rapprocher les accès", "etiquettes": "maison"}).json()["candidates"]
    assert score(autre, "b") < score(sans, "b")


def test_agent_ne_cree_pas_une_tache_avec_etiquette_inconnue(client):
    r = client.post("/api/taches", json={"titre": "Tout autre sujet lointain", "etiquettes": ["fantome"]},
                    headers=HA)
    assert r.status_code in (400, 409, 422)


def test_renommer_fusionner_et_annuler(client, vault):  # mots de longueurs différentes : le cache de l'index se clé sur (mtime, taille)
    client.put("/api/etiquettes/banque", json={"consigne": "prudence"}, headers=H)
    r = client.post("/api/etiquettes/renommer", json={"de": "banque", "vers": "comptabilite"}, headers=H)
    assert r.status_code == 200
    assert etiquettes.de(vault.tache("a").fm) == ["comptabilite"]
    assert etiquettes.de(vault.tache("b").fm) == ["compta", "comptabilite"]
    lots = {e["mot"]: e for e in client.get("/api/etiquettes").json()["etiquettes"]}
    assert "banque" not in lots and lots["comptabilite"]["consigne"] == "prudence" and lots["comptabilite"]["n"] == 2
    assert client.post(f"/api/lots/{r.json()['lot']}/annuler", headers=H).status_code == 200
    assert etiquettes.de(vault.tache(ident(client, "a")).fm) == ["banque"]
    assert etiquettes.de(vault.tache(ident(client, "b")).fm) == ["banque", "compta"]
    assert {e["mot"]: e for e in client.get("/api/etiquettes").json()["etiquettes"]}["banque"]["consigne"] == "prudence"


def test_un_agent_ne_renomme_pas(client):
    assert client.post("/api/etiquettes/renommer", json={"de": "banque", "vers": "x"}, headers=HA).status_code == 409


def test_pose_en_bloc_annulable(client, vault):
    ids = [ident(client, f) for f in "cd"]
    r = client.post("/api/lots", json={"taches": ids, "etiquettes": {"ajouter": ["prioritaire"], "retirer": ["maison"]}},
                    headers=H)
    assert r.status_code == 200
    assert etiquettes.de(vault.tache(ids[0]).fm) == ["prioritaire"] and etiquettes.de(vault.tache(ids[1]).fm) == ["prioritaire"]
    client.post(f"/api/lots/{r.json()['lot']}/annuler", headers=H)
    assert etiquettes.de(vault.tache(ids[0]).fm) == ["maison"] and etiquettes.de(vault.tache(ids[1]).fm) == []


def test_supprimer_une_etiquette_utilisee_est_refuse(client):
    assert client.delete("/api/etiquettes/banque", headers=H).status_code == 409
    client.put("/api/etiquettes/vide", json={"consigne": ""}, headers=H)
    assert client.delete("/api/etiquettes/vide", headers=H).status_code == 200


def test_lien_propose_sans_etiquette_commune_est_refuse(client):
    a, c = ident(client, "a"), ident(client, "c")
    r = client.post("/api/propositions", json={"type": "lier", "tache": a, "valeur": f"voir_aussi:{c}",
                                               "motif": "test"}, headers=H)
    assert r.status_code in (400, 409, 422) and "banque" in r.text and "maison" in r.text


def test_recherche_trouve_par_etiquette(client, vault):
    assert [r["titre"] for r in recherche.chercher(vault, "#maison")] == ["Acheter des ampoules"]
    assert len(recherche.chercher(vault, "banque")) == 2
