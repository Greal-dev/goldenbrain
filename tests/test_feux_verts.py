"""Feu vert lié à une version (INV-FEU-1) : demande, accord, refus, sha exact, vérification.

Chaîne complète : commande `orch feu-vert` → API → registre + trace dans la fiche demandeuse.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, fiches
from orchestrateur.moteur import Moteur
from test_api import BASE, H, attendre_inactif

SHA = "a" * 40
AUTRE = "b" * 40


@pytest.fixture
def orch(config, vault, faux, monkeypatch):
    """`orch(*args, tache=…)` : la commande, routée vers un vrai serveur en mémoire."""
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        def appeler(methode, chemin, corps=None):
            r = c.request(methode, "/api" + chemin, json=corps, headers=H)
            if r.status_code >= 400:
                raise cli.ErreurCli(f"erreur {r.status_code} : {r.json().get('detail')}")
            return r.json()

        monkeypatch.setattr(cli, "appeler", appeler)

        def lancer(*args, tache="mere"):
            monkeypatch.setenv("ORCH_TACHE", tache)
            code = cli.main(list(args))
            for t in ("mere", "enfant"):
                attendre_inactif(c, t)
            return code

        lancer.client = c
        yield lancer


def corps(vault, ident):
    return fiches.corps_sans_fiche(fiches.lire(vault.tache(ident).chemin))


def test_demande_transmise_au_controleur_et_consignee(orch, vault, faux, capsys):
    assert orch("feu-vert", "demander", SHA, "fusion du lot 3", "--a", "enfant") == 0
    assert "feu vert demandé à enfant" in capsys.readouterr().out
    message = faux.lances[-1]["message"]
    assert SHA in message and "fusion du lot 3" in message and "feu-vert accorder" in message
    assert f"feu vert demandé pour `{SHA}` par mere (contrôleur : enfant)" in corps(vault, "mere")
    assert orch("feu-vert", "verifier", SHA) == 1  # en attente : pas de feu vert


def test_accord_puis_verification_du_sha_exact(orch, vault, faux, capsys):
    orch("feu-vert", "demander", SHA, "fusion", "--a", "enfant")
    assert orch("feu-vert", "accorder", SHA, "porte verte, journal joint", tache="enfant") == 0
    texte = corps(vault, "mere")
    assert f"feu vert ACCORDÉ pour `{SHA}` par enfant" in texte and "porte verte" in texte
    assert texte.count("## Feux verts") == 1  # les lignes s'ajoutent à la même section
    assert "ACCORDÉ" in faux.lances[-1]["message"]  # le demandeur est prévenu
    capsys.readouterr()
    assert orch("feu-vert", "verifier", SHA) == 0
    assert "accordé" in capsys.readouterr().out
    assert orch("feu-vert", "verifier", SHA.upper()) == 0  # même sha, casse indifférente
    assert orch("feu-vert", "verifier", AUTRE) == 1  # sha différent : refusé
    assert orch("feu-vert", "verifier", SHA[:12]) == 1  # préfixe : refusé
    assert orch("feu-vert", "demander", SHA, "encore", "--a", "enfant") == 1  # déjà accordé


def test_refus_consigne_et_verification_echoue(orch, vault, capsys):
    orch("feu-vert", "demander", SHA, "déploiement", "--a", "enfant")
    assert orch("feu-vert", "refuser", SHA, "épreuve rouge", tache="enfant") == 0
    assert f"feu vert REFUSÉ pour `{SHA}` par enfant" in corps(vault, "mere")
    assert orch("feu-vert", "verifier", SHA) == 1
    assert "refuse" in capsys.readouterr().err
    # Une nouvelle demande rouvre ; l'accord vaut alors.
    orch("feu-vert", "demander", SHA, "déploiement, épreuve corrigée", "--a", "enfant")
    orch("feu-vert", "accorder", SHA, "vert", tache="enfant")
    assert orch("feu-vert", "verifier", SHA) == 0


def test_seul_le_controleur_designe_tranche(orch, capsys):
    orch("feu-vert", "demander", SHA, "fusion", "--a", "enfant")
    assert orch("feu-vert", "accorder", SHA, "moi-même", tache="mere") == 1
    assert "403" in capsys.readouterr().err
    assert orch("feu-vert", "verifier", SHA) == 1


def test_demandes_invalides(orch, capsys):
    assert orch("feu-vert", "demander", "abc", "fusion", "--a", "enfant") == 1
    assert orch("feu-vert", "demander", SHA, "fusion", "--a", "mere") == 1  # soi-même
    assert orch("feu-vert", "demander", SHA, "fusion", "--a", "inconnue") == 1
    assert orch("feu-vert", "accorder", AUTRE, "rien demandé", tache="enfant") == 1
    assert orch("feu-vert", "verifier", SHA) == 1


def test_registre_persiste_au_redemarrage(orch, config, vault, faux):
    orch("feu-vert", "demander", SHA, "fusion", "--a", "enfant")
    orch("feu-vert", "accorder", SHA, "ok", tache="enfant")
    registre = json.loads((config.donnees / "etat" / "feux-verts.json").read_text("utf-8"))
    assert registre[SHA]["etat"] == "accorde" and registre[SHA]["auteur"] == "enfant"
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url=BASE) as c:
        assert c.get(f"/api/feux-verts/{SHA}", headers=H).json()["etat"] == "accorde"


def test_verifier_sans_serveur_echoue(monkeypatch, capsys):
    monkeypatch.setenv("ORCH_URL", "http://127.0.0.1:1")
    assert cli.main(["feu-vert", "verifier", SHA]) == 1
    assert "pas de feu vert" in capsys.readouterr().err


def test_section_ajoutee_avant_la_fiche_sans_toucher_le_reste():
    texte = ("---\nstatut: a-faire\n---\n\n# T\n\nCorps.\n\n"
             f"{fiches.DEBUT}\n## Fiche\n- **Fait** : x\n{fiches.FIN}\n")
    un = fiches.ajouter_a_section(texte, "Feux verts", "- l1")
    deux = fiches.ajouter_a_section(un, "Feux verts", "- l2")
    assert deux.startswith("---\nstatut: a-faire\n---\n\n# T\n\nCorps.\n\n## Feux verts\n- l1\n- l2\n")
    assert fiches.lire_fiche(deux)["fait"] == "x"
    assert fiches.ajouter_a_section("# T\r\n", "Feux verts", "- l") == "# T\r\n\r\n## Feux verts\r\n- l\r\n"


def test_porte_lancee_par_un_agent_au_3e_saut_reste_verte():
    """Régression : ORCH_SAUTS=3 hérité de l'agent qui lance la porte la rendait rouge sans défaut."""
    env = {**os.environ, "ORCH_SAUTS": "3", "ORCH_TACHE": "t", "ORCH_URL": "http://127.0.0.1:1"}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "tests/test_feux_verts.py", "tests/test_pilotage.py",
                        "-k", "not 3e_saut"],
                       cwd=Path(__file__).resolve().parent.parent, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-1500:]
