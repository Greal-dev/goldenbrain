"""Appairage d'un exécuteur (INV-APPAIRAGE-1, INV-DISTANT-1) : code court à usage unique, durée
limitée, essais limités, garde de l'interface distante, échange de bout en bout et jeton jamais
affiché. Aucun réseau : le client de l'exécuteur parle à l'API du chef par TestClient."""

import json

import pytest
from fastapi.testclient import TestClient

from conftest import PORT
from orchestrateur import api, appairage, executeur
from orchestrateur.config import ConfigExecuteurs
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}
ECOUTE = "100.64.0.5"
ECHANGE = "/api/executeurs/appairage/echange"


@pytest.fixture
def chef(config, vault, faux):
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    m = Moteur(config, vault, {"faux": faux})
    app = api.creer_app(config, m)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as poste, \
            TestClient(app, base_url=f"http://{ECOUTE}:{PORT}") as distant:
        yield m, poste, distant


def test_code_court_lisible_et_a_usage_unique(chef):
    m, poste, distant = chef
    c = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()
    brut = appairage.normaliser(c["code"])
    assert len(brut) == appairage.LONGUEUR and c["code"][4] == "-" and c["valide_s"] == appairage.VALIDITE_S
    assert not set(brut) & set("01OIL")
    r = distant.post(ECHANGE, json={"code": c["code"].lower()}, headers=H)  # sans jeton, casse libre
    assert r.status_code == 200 and r.json()["nom"] == "portable"
    assert m.executeurs.identifier(r.json()["jeton"]) == "portable"
    assert distant.post(ECHANGE, json={"code": c["code"]}, headers=H).status_code == 400  # consommé


def test_le_code_expire(chef):
    m, poste, _ = chef
    t = [1000.0]
    m.executeurs.appairage._horloge = lambda: t[0]
    c = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()
    t[0] += appairage.VALIDITE_S - 1
    assert poste.get("/api/executeurs").json()["appairages"] == [{"nom": "portable", "reste_s": 1}]
    t[0] += 2
    assert poste.get("/api/executeurs").json()["appairages"] == []
    assert poste.post(ECHANGE, json={"code": c["code"]}, headers=H).status_code == 400


def test_essais_limites_puis_verrou_qui_tombe(chef):
    m, poste, _ = chef
    t = [1000.0]
    m.executeurs.appairage._horloge = lambda: t[0]
    c = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()
    for _ in range(appairage.ECHECS_MAX):
        assert poste.post(ECHANGE, json={"code": "AAAA-AAAA"}, headers=H).status_code == 400
    # verrouillé : même le bon code est refusé
    assert poste.post(ECHANGE, json={"code": c["code"]}, headers=H).status_code == 429
    t[0] += appairage.VERROU_S + 1
    assert poste.post(ECHANGE, json={"code": c["code"]}, headers=H).status_code == 200


def test_un_nouveau_code_remplace_l_ancien_du_meme_nom(chef):
    _, poste, _ = chef
    a = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()["code"]
    b = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()["code"]
    assert poste.post(ECHANGE, json={"code": a}, headers=H).status_code == 400
    assert poste.post(ECHANGE, json={"code": b}, headers=H).status_code == 200


def test_nom_invalide_refuse_a_l_ouverture(chef):
    _, poste, _ = chef
    for nom in ("chef", "a b", "é"):
        assert poste.post("/api/executeurs/appairage", json={"nom": nom}, headers=H).status_code == 400


def test_interface_distante_n_admet_que_l_echange(chef):
    m, poste, distant = chef
    jeton = m.executeurs.creer_jeton("pc2")
    # ouvrir un code est réservé au poste : ni sans jeton, ni avec un jeton d'exécuteur
    assert distant.post("/api/executeurs/appairage", json={"nom": "x"}, headers=H).status_code == 401
    r = distant.post("/api/executeurs/appairage", json={"nom": "x"}, headers={**H, "X-Orch-Jeton": jeton})
    assert r.status_code == 401
    # le reste de l'API exige toujours le jeton, et l'échange ne vaut qu'en POST
    assert distant.get("/api/arbre").status_code == 401
    assert distant.get(ECHANGE).status_code == 401
    # le code ne figure dans aucune lecture
    c = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()["code"]
    lecture = poste.get("/api/executeurs").text
    assert c not in lecture and appairage.normaliser(c) not in lecture


def test_echange_de_bout_en_bout_puis_connexion(chef, tmp_path):
    m, poste, distant = chef
    c = poste.post("/api/executeurs/appairage", json={"nom": "portable"}, headers=H).json()["code"]

    def appel(url, corps):
        r = distant.post(url, json=corps, headers=H)
        return r.status_code, r.json()

    fichier = tmp_path / "liaison.json"
    serveur = f"http://{ECOUTE}:{PORT}"
    assert executeur.lier(serveur, c, fichier, appel) == "portable"
    assert executeur.liaison(fichier)[0] == serveur
    jeton = executeur.liaison(fichier)[1]
    assert m.executeurs.identifier(jeton) == "portable"
    # le jeton obtenu ouvre bien l'annonce, par l'interface distante
    r = distant.post("/api/executeurs/annonce", json={"harnais": ["faux"]}, headers={**H, "X-Orch-Jeton": jeton})
    assert r.status_code == 200 and m.executeurs.connecte("portable")
    # un code déjà consommé est refusé avec le motif du chef
    with pytest.raises(executeur.AppairageRefuse, match="invalide ou expiré"):
        executeur.lier(serveur, c, fichier, appel)
    assert json.loads(fichier.read_text(encoding="utf-8"))["jeton"] == jeton  # l'échec n'efface rien


def test_chef_injoignable_est_un_refus_net(tmp_path):
    def appel(url, corps):
        raise ConnectionRefusedError("fermé")
    with pytest.raises(executeur.AppairageRefuse, match="injoignable"):
        executeur.lier("http://x", "ABCD-EFGH", tmp_path / "l.json", appel)
    assert not (tmp_path / "l.json").exists()


def test_main_ne_montre_jamais_le_jeton_et_le_retient(monkeypatch, tmp_path, capsys):
    fichier = tmp_path / "liaison.json"
    secret = "jeton-secret-de-test"

    def faux_lier(serveur, code, fichier_=fichier, appel=None):
        fichier.write_text(json.dumps({"serveur": serveur, "jeton": secret}), encoding="utf-8")
        return "portable"

    vus = []

    class Faux:
        def __init__(self, serveur, jeton, *a, **k):
            vus.append((serveur, jeton))
            self.disponibles = []

        async def tourner(self):
            return None

    monkeypatch.setattr(executeur, "lier", faux_lier)
    monkeypatch.setattr(executeur, "LIAISON", fichier)
    monkeypatch.setattr(executeur, "Executeur", Faux)
    monkeypatch.setattr(executeur.asyncio, "run", lambda c: c.close())
    assert executeur.main("http://chef:8300", "", None, 1, "ABCD-EFGH") == 0
    sortie = capsys.readouterr()
    assert secret not in sortie.out + sortie.err and "portable" in sortie.out
    assert vus == [("http://chef:8300", secret)]
    # relance sans code ni serveur : le jeton retenu suffit ; pour un autre chef, il ne sert pas
    assert executeur.main("", "", None, 1) == 0 and vus[-1] == ("http://chef:8300", secret)
    assert executeur.main("http://autre:8300", "", None, 1) == 2
