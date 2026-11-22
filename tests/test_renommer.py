"""Renommer une tâche (INV-RENOMMER-1) et proposition « renommer » (INV-RENOMMER-2)."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, fiches
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
ENTETE = "---\ntype: tache\nstatut: a-faire\ncle_perso:   garde  l'espace # commentaire\nupdated: 2026-01-01\n---\n"


def test_renommer_titre_ne_touche_que_le_titre():
    texte = ENTETE + "\nIntro\n\n# Ventes du club  \n\nSuite `# pas un titre`\n# Autre\n"
    sortie = fiches.renommer_titre(texte, "API/MCP ventes du club")
    assert sortie == ENTETE + "\nIntro\n\n# API/MCP ventes du club  \n\nSuite `# pas un titre`\n# Autre\n"


def test_renommer_titre_conserve_les_fins_de_ligne_crlf():
    texte = "---\r\nstatut: a-faire\r\n---\r\n# Ancien\r\n\r\nCorps\r\n"
    assert fiches.renommer_titre(texte, "Neuf") == "---\r\nstatut: a-faire\r\n---\r\n# Neuf\r\n\r\nCorps\r\n"


def test_renommer_titre_sans_titre_en_pose_un_en_tete_du_corps():
    texte = ENTETE + "Juste du texte\n"
    assert fiches.renommer_titre(texte, "Neuf") == ENTETE + "# Neuf\n\nJuste du texte\n"


def test_vault_renomme_sans_changer_identifiant_ni_fichier(vault):
    avant = vault.tache("x")
    brut = fiches.lire(avant.chemin)
    vault.renommer("x", "  Un   titre\nexplicite ")
    apres = vault.tache("x")
    assert apres.titre == "Un titre explicite" and apres.id == "x" and apres.chemin == avant.chemin
    nouveau = fiches.lire(apres.chemin)
    garde = lambda t: [ligne for ligne in fiches.decouper(t)[0] if not ligne.startswith("updated:")]
    assert garde(nouveau) == garde(brut) and fiches.decouper(nouveau)[3] == fiches.decouper(brut)[3].replace(
        f"# {avant.titre}", "# Un titre explicite")


def test_vault_refuse_un_titre_vide_ou_trop_long(vault):
    for mauvais in ("", "  \n ", "x" * 201):
        with pytest.raises(Invalide):
            vault.renommer("x", mauvais)


def test_proposition_renommer_applique_seulement_a_l_acceptation(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    ancien = vault.tache("x").titre
    p = m.proposer("renommer", "x", "API/MCP ventes", de="mere", motif="Le contenu est un accès MCP/API")
    assert p["etat"] == "en_attente" and vault.tache("x").titre == ancien
    m.trancher(p["n"], True)
    assert vault.tache("x").titre == "API/MCP ventes"
    refusee = m.proposer("renommer", "x", "Autre titre", motif="Parce que c'est plus clair")
    m.trancher(refusee["n"], False)
    assert vault.tache("x").titre == "API/MCP ventes"


def test_proposition_renommer_exige_motif_et_titre_different(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    with pytest.raises(Invalide, match="motif"):
        m.proposer("renommer", "x", "Neuf", motif="  ")
    with pytest.raises(Invalide, match="actuel"):
        m.proposer("renommer", "x", vault.tache("x").titre, motif="rien à changer")
    with pytest.raises(Invalide):
        m.proposer("renommer", "x", "  ", motif="vide")


@pytest.fixture
def client(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url=BASE) as c:
        yield c


def test_route_renommer(client, vault):
    assert client.post("/api/taches/x/renommer", json={"titre": "Neuf"}).status_code == 403  # garde INV-API-1
    r = client.post("/api/taches/x/renommer", json={"titre": "Neuf"}, headers=H)
    assert r.status_code == 200 and r.json()["titre"] == "Neuf" and r.json()["id"] == "x"
    assert any(n["titre"] == "Neuf" for n in client.get("/api/recherche?q=neuf").json())
    assert client.post("/api/taches/x/renommer", json={"titre": " "}, headers=H).status_code == 400
    assert client.post("/api/taches/inconnue/renommer", json={"titre": "N"}, headers=H).status_code == 404


def test_cli_renommer_et_proposer_renommer(monkeypatch, capsys):
    journal = []
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: journal.append((m, c, corps)) or
                        {"titre": "Neuf", "n": 1, "type": "renommer", "tache": "t1", "valeur": "Neuf"})
    monkeypatch.setenv("ORCH_TACHE", "t1")
    assert cli.main(["renommer", "t/2", "Neuf"]) == 0
    assert journal[-1] == ("POST", "/taches/t%2F2/renommer", {"titre": "Neuf"})
    assert "renommée : Neuf" in capsys.readouterr().out
    assert cli.main(["proposer", "renommer", "t1", "Neuf", "--motif", "plus clair"]) == 0
    assert journal[-1][2] == {"type": "renommer", "tache": "t1", "valeur": "Neuf", "de": "t1", "motif": "plus clair"}


def test_consignes_des_agents_citent_le_renommage():
    from pathlib import Path
    from orchestrateur import config
    assert "proposer renommer" in config.REVUE
    exemple = (Path(__file__).resolve().parents[1] / "config.exemple.toml").read_text(encoding="utf-8")
    assert exemple.count("proposer renommer") >= 2  # consigne commune et revue de cohérence
