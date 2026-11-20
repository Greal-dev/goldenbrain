"""Saisie sécurisée du jeton Telegram (INV-TELEGRAM-2, INV-INSTALL-1) : commande exacte, terminal, coffre, CLI.
Faux Telegram local ; aucun terminal réel n'est ouvert, aucun réseau."""

import sys

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, coffre, config as cfg, telegram_jeton
from orchestrateur.config import ConfigExecuteurs
from orchestrateur.moteur import Moteur
from test_telegram import JETON, tg  # noqa: F401  (fixture)

H = {"X-Orchestrateur": "1"}


@pytest.fixture
def poste(config, tmp_path, monkeypatch, tg):  # noqa: F811
    monkeypatch.delenv("GOLDENBRAIN_TELEGRAM_JETON", raising=False)
    config.telegram.jeton_fichier = str(tmp_path / "coffre" / "telegram.jeton")
    return config


def test_saisie_enregistre_sans_jamais_afficher_le_jeton(poste, tg):  # noqa: F811
    sortie, invites = [], []
    code = telegram_jeton.saisir(poste, lire=lambda i: invites.append(i) or JETON, sortie=sortie.append)
    assert code == 0 and sortie == ["jeton enregistré pour @essai_bot"]
    assert JETON not in "".join(sortie + invites)
    assert coffre.lire("VARIABLE_ABSENTE", telegram_jeton.fichier_jeton(poste))[0] == JETON


def test_jeton_refuse_n_ecrit_rien_et_ne_fuit_pas(poste, tg):  # noqa: F811
    sortie = []
    code = telegram_jeton.saisir(poste, lire=lambda _: "999:mauvais-jeton", sortie=sortie.append)
    assert code == 1 and "refusé" in sortie[0] and "999:mauvais-jeton" not in "".join(sortie)
    assert not telegram_jeton.fichier_jeton(poste).exists()
    assert telegram_jeton.saisir(poste, lire=lambda _: "  ", sortie=sortie.append) == 1


def test_saisie_vide_redemande_au_lieu_de_fermer(poste, tg):  # noqa: F811
    reponses, sortie = iter(["", "  ", JETON]), []
    code = telegram_jeton.saisir(poste, lire=lambda _: next(reponses), sortie=sortie.append)
    assert code == 0 and sortie[-1] == "jeton enregistré pour @essai_bot"
    assert "Ctrl+Maj+V" in sortie[0] and "Nouvel essai (2/3)" in sortie[0]


def test_jeton_refuse_puis_bon_jeton_enregistre(poste, tg):  # noqa: F811
    reponses = iter(["999:mauvais-jeton", JETON])
    assert telegram_jeton.saisir(poste, lire=lambda _: next(reponses), sortie=lambda _: None) == 0


def test_saisie_abandonnee_apres_trois_essais_ou_interruption(poste, tg):  # noqa: F811
    lus = []
    assert telegram_jeton.saisir(poste, lire=lambda i: lus.append(i) or "", sortie=lambda _: None) == 1
    assert len(lus) == telegram_jeton.ESSAIS

    def interrompre(_):
        raise KeyboardInterrupt
    assert telegram_jeton.saisir(poste, lire=interrompre, sortie=lambda _: None) == 1


def test_pause_demandee_meme_en_cas_d_echec(poste, tg):  # noqa: F811
    pauses = []
    telegram_jeton.saisir(poste, lire=lambda _: "", sortie=lambda _: None, pause=pauses.append)
    assert len(pauses) == 1


def test_la_commande_montree_est_celle_qui_se_lance(poste):
    poste.chemin = poste.donnees / "config.toml"
    argv = telegram_jeton.argv(poste)
    assert argv[0] == sys.executable and argv[2:4] == ["telegram-jeton", "--pause"] and argv[-2:] == ["--config", str(poste.chemin)]
    assert JETON not in telegram_jeton.commande(poste)


def test_route_terminal_exige_la_commande_exacte(poste, vault, faux, monkeypatch):
    lances = []
    monkeypatch.setattr(telegram_jeton, "ouvrir_terminal", lambda a: lances.append(a) or "")
    with TestClient(api.creer_app(poste, Moteur(poste, vault, {"faux": faux})), base_url="http://127.0.0.1:8399") as c:
        etat = c.get("/api/telegram").json()
        assert etat["commande_jeton"] == telegram_jeton.commande(poste) and etat["jeton"] == ""
        assert c.post("/api/telegram/jeton/terminal", headers=H, json={"accord": "rm -rf /"}).status_code == 400
        assert lances == []  # texte libre : jamais lancé (INV-INSTALL-1)
        r = c.post("/api/telegram/jeton/terminal", headers=H, json={"accord": etat["commande_jeton"]})
        assert r.json() == {"ok": True, "motif": ""} and lances == [telegram_jeton.argv(poste)]
        monkeypatch.setattr(telegram_jeton, "ouvrir_terminal", lambda a: "aucun terminal graphique trouvé")
        r = c.post("/api/telegram/jeton/terminal", headers=H, json={"accord": etat["commande_jeton"]})
        assert r.json()["ok"] is False and "terminal" in r.json()["motif"]


def test_route_terminal_reservee_au_poste(poste, vault, faux):
    poste.executeurs = ConfigExecuteurs(ecoute="10.0.0.5")
    m = Moteur(poste, vault, {"faux": faux})
    jeton = m.executeurs.creer_jeton("pc2")
    with TestClient(api.creer_app(poste, m), base_url=f"http://10.0.0.5:{poste.port}") as c:
        r = c.post("/api/telegram/jeton/terminal", headers={**H, "X-Orch-Jeton": jeton}, json={"accord": ""})
        assert r.status_code == 401  # ouvrir un terminal se décide au poste, pas à distance


def test_terminal_linux_sans_affichage_ou_sans_emulateur(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert "affichage" in telegram_jeton.ouvrir_terminal(["x"])
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(telegram_jeton.shutil, "which", lambda b: None)
    assert "aucune invite de commandes" in telegram_jeton.ouvrir_terminal(["x"])
    lances = []
    monkeypatch.setattr(telegram_jeton.shutil, "which", lambda b: f"/usr/bin/{b}" if b == "konsole" else None)
    monkeypatch.setattr(telegram_jeton.subprocess, "Popen", lambda cmd, **k: lances.append((cmd, k)))
    assert telegram_jeton.ouvrir_terminal(["py", "orch.py"]) == ""
    assert lances[0][0] == ["/usr/bin/konsole", "-e", "py", "orch.py"] and lances[0][1]["start_new_session"]


def test_cli_telegram_jeton_delegue(monkeypatch, poste):
    appels = []
    monkeypatch.setattr(cfg, "charger", lambda chemin=None: poste)
    monkeypatch.setattr(telegram_jeton, "saisir", lambda c, pause=None: appels.append((c, pause)) or 0)
    assert cli.main(["telegram-jeton"]) == 0 and appels == [(poste, None)]
    assert cli.main(["telegram-jeton", "--pause"]) == 0 and appels[1][1] is input


def test_reglages_conservent_api_et_jeton_fichier(tmp_path):
    from orchestrateur.api_interface import remplacer_section
    f = tmp_path / "c.toml"
    f.write_text('[telegram]\napi = "http://127.0.0.1:1"\nactif = false\n', encoding="utf-8")
    remplacer_section(f, "telegram", [("actif", "true")], garder=("api",))
    texte = f.read_text("utf-8")
    assert 'api = "http://127.0.0.1:1"' in texte and "actif = true" in texte
