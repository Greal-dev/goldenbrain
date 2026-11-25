"""Équipe (fichiers de personas, filtre de déclenchement) et routes du lot 3 serveur."""

import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli
from orchestrateur import config as cfg_mod
from orchestrateur.equipe import Equipe, normaliser_persona, s_applique
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from conftest import ecrire, tache_md
from test_api import BASE, H, attendre_inactif
from test_revues import OK, evs, multi, rendu

FICHE = {"fait": "écrit le script", "situation": "", "reste": "", "prochain_pas": "",
         "sous_taches": []}


def p(**extra):
    return normaliser_persona("x", {"actif": True, "declenchement": "filtre", **extra})


@pytest.mark.parametrize("persona, attendu", [
    (p(declenchement="toujours"), True),
    (p(), True),  # filtre sans critère = toujours
    (p(declenchement="a-la-demande"), False),
    (p(declenchement="toujours", actif=False), False),
    (p(casquettes=["C1-Pro"]), True),
    (p(casquettes=["C2"]), False),
    (p(conteneurs=["Projets/C1-Alpha"]), True),
    (p(conteneurs=["Projets/C2-Beta"]), False),
    (p(mots=["script"]), True),
    (p(mots=["Écrit"]), True),  # sans casse ni accents
    (p(mots=["scr"]), False),  # mot entier
    (p(mots=["code"], casquettes=["C1"]), False),  # tous les critères renseignés
])
def test_filtre_de_declenchement(persona, attendu):
    assert s_applique(persona, "Préparer", FICHE, "C1", "Projets/C1-Alpha") is attendu


def test_amorce_ecriture_lecture_retrait(tmp_path):
    e = Equipe(tmp_path / "equipe")
    e.amorcer()
    exemples = e.lister()
    assert [x["id"] for x in exemples] == ["relecteur", "revue-code", "rssi"]
    assert not any(x["actif"] for x in exemples)
    assert e.lire("rssi")["declenchement"] == "toujours"
    assert e.lire("revue-code")["mots"] == ["code", "script", "dev"]
    assert all(3 <= len(x[k].splitlines()) <= 5 for x in exemples for k in ("mandat", "focus"))
    ecrit = e.ecrire("dev", {"nom": "Dev : relecteur", "actif": True, "mots": ["a b"],
                             "mandat": "M\nM2", "focus": "F"})
    assert e.lire("dev") == ecrit and ecrit["mandat"] == "M\nM2"
    e.retirer("dev")
    e.ecrire("dev", {"nom": "Dev"})
    e.retirer("dev")
    assert len(list((tmp_path / "equipe" / "_retires").glob("dev*.md"))) == 2  # rien d'écrasé
    with pytest.raises(Invalide):
        e.ecrire("Mauvais id", {})
    with pytest.raises(Invalide):
        e.ecrire("ok", {"declenchement": "parfois"})


def test_fichier_illisible_ignore(tmp_path, caplog):
    e = Equipe(tmp_path)
    e.ecrire("bon", {"nom": "Bon"})
    (tmp_path / "casse.md").write_text("---\nnom: [pas fermé\n---\n", encoding="utf-8")
    (tmp_path / "sans.md").write_text("pas de frontmatter", encoding="utf-8")
    assert [x["id"] for x in e.lister()] == ["bon"]
    assert "casse.md" in caplog.text


def test_dossier_d_equipe_amorce_au_demarrage(config, vault, faux):
    Moteur(config, vault, {"faux": faux})
    assert len(list((config.donnees / "equipe").glob("*.md"))) == 3


@pytest.fixture
def client(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    with TestClient(api.creer_app(config, m), base_url=BASE) as c:
        c.moteur = m
        yield c


def test_routes_equipe(client, config):
    assert len(client.get("/api/equipe").json()) == 3
    corps = {"nom": "RSSI", "actif": True, "declenchement": "toujours", "focus": "secrets"}
    r = client.put("/api/equipe/rssi", headers=H, json=corps)
    assert r.status_code == 200 and r.json()["actif"] is True
    assert set(r.json()) == {"id", "nom", "actif", "declenchement", "casquettes", "conteneurs",
                             "mots", "harnais", "modele", "mandat", "focus"}
    assert client.put("/api/equipe/Bad_Id", headers=H, json=corps).status_code == 400
    assert client.put("/api/equipe/x", headers=H, json={"harnais": "inconnu"}).status_code == 400
    (config.donnees / "equipe" / "abime.md").write_text("---\n: :\n", encoding="utf-8")
    assert client.get("/api/equipe").status_code == 200
    assert client.delete("/api/equipe/rssi", headers=H).status_code == 204
    assert client.delete("/api/equipe/rssi", headers=H).status_code == 404
    assert (config.donnees / "equipe" / "_retires" / "rssi.md").is_file()


def test_valider_renvoyer_liberer(client, racine, faux):
    multi(faux, {"": evs("s-1", rendu())})
    ecrire(racine, "Projets/C1-Alpha/taches/pc.md",
           "---\r\ntype: tache\r\npaperclip: run-9\r\nexecution:\r\n  id: 4\r\n  agent: a\r\n"
           "statut: en-cours\r\n# note\r\n---\r\n\r\n# PC\r\n")
    assert client.post("/api/taches/pc/valider", headers=H).status_code == 409  # INV-VAULT-4
    t = client.post("/api/taches/pc/liberer", headers=H).json()
    assert t["statut_verrouille"] is False
    octets = (racine / "Projets/C1-Alpha/taches/pc.md").read_bytes()
    assert octets == b"---\r\ntype: tache\r\nstatut: en-cours\r\n# note\r\n---\r\n\r\n# PC\r\n"
    assert client.post("/api/taches/pc/liberer", headers=H).status_code == 409
    r = client.post("/api/taches/mere/renvoyer", headers=H, json={"texte": "reprends"})
    assert r.status_code == 200
    attendre_inactif(client, "mere")
    assert faux.lances[-1]["message"] == "reprends"
    t = client.get("/api/taches/mere").json()
    assert t["statut"] == "fait" and t["renvois"] == 0 and t["revues"] == []
    assert client.get("/api/etat").json()["a_valider"] == 1
    assert client.post("/api/taches/mere/valider", headers=H).json()["statut"] == "cloture"
    assert client.get("/api/etat").json()["a_valider"] == 0


def test_solliciter_route(client, faux):
    multi(faux, {"": evs("s-1", rendu("en_attente").replace("</fiche>", "prochain_pas: Choisis A ou B ?\n</fiche>")), "rssi": evs("p-1", OK)})
    client.put("/api/equipe/rssi", headers=H, json={"nom": "RSSI", "focus": "f"})
    r = client.post("/api/taches/mere/solliciter", headers=H, json={"persona": "rssi"})
    assert r.status_code == 202
    for _ in range(300):
        if client.get("/api/taches/mere/revues").json()[:1] and faux.lances[-1]["persona"] == "":
            break
        time.sleep(0.01)
    attendre_inactif(client, "mere")
    avis = client.get("/api/taches/mere/revues").json()
    assert avis[0]["persona"] == "rssi" and avis[0]["verdict"] == "ok"
    assert set(avis[0]) == {"persona", "nom", "verdict", "points", "date", "origine", "moteur", "modele"}
    assert faux.lances[-1]["message"].startswith("[Avis de RSSI]")
    assert client.get("/api/taches/mere").json()["revues"][0]["persona"] == "rssi"
    assert client.post("/api/taches/mere/solliciter", headers=H,
                       json={"persona": "inconnu"}).status_code == 404
    assert client.post("/api/taches/mere/solliciter", headers=H,
                       json={"persona": "relecteur"}).status_code == 409  # inactif
    assert client.get("/api/taches/inconnue/revues").status_code == 404


def test_orch_solliciter(monkeypatch, capsys):
    appels = []
    monkeypatch.setattr(cli, "appeler", lambda *a: appels.append(a) or {})
    monkeypatch.setenv("ORCH_TACHE", "t/1")
    monkeypatch.delenv("ORCH_PERSONA", raising=False)
    assert cli.main(["solliciter", "rssi", "Est-ce sûr ?"]) == 0
    assert appels == [("POST", "/taches/t%2F1/solliciter",
                       {"persona": "rssi", "question": "Est-ce sûr ?"})]
    monkeypatch.setenv("ORCH_PERSONA", "rssi")  # INV-EQUIPE-1
    assert cli.main(["solliciter", "rssi", "?"]) == 1
    assert len(appels) == 1 and "persona" in capsys.readouterr().err


def test_config_sans_validation_ni_equipe(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('[vault]\nracine = "."\ntaches = []\n', encoding="utf-8")
    c = cfg_mod.charger(f)
    assert (c.validation.mode, c.validation.persona, c.validation.boucles_max) == \
        ("humain", "relecteur", 2)
    assert c.equipe.dossier == ""
    f.write_text('[vault]\nracine = "."\ntaches = []\n[validation]\nmode = "x"\n', "utf-8")
    with pytest.raises(ValueError):
        cfg_mod.charger(f)


def test_fiche_sans_statut_et_tache_existante_lisibles(vault, racine):
    ecrire(racine, "_meta/taches/ancienne.md", tache_md(statut="retour-humain"))
    assert vault.ouverte(vault.tache("ancienne"))
