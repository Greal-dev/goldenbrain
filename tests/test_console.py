"""Console en terminal (`orch console`) : client contre un vrai serveur et le harnais factice."""

import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from orchestrateur import api, cli, console
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}


@pytest.fixture
def serveur(config, vault, faux, monkeypatch):
    # Le tour reste ouvert (« attendre ») tant que personne ne l'arrête.
    faux.scenario = [Evenement("session", session="s-1"), Evenement("texte", texte="je lis"),
                     "attendre", Evenement("fin", session="s-1", texte="fini")]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        config.port = s.getsockname()[1]
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=config.port, log_level="warning",
                                         timeout_graceful_shutdown=1))  # flux SSE encore ouverts
    fil = threading.Thread(target=srv.run, daemon=True)
    fil.start()
    while not srv.started:
        time.sleep(0.02)
    monkeypatch.setenv("ORCH_URL", f"http://127.0.0.1:{config.port}")
    yield faux
    srv.should_exit = True
    fil.join(timeout=10)


def attendre(condition, delai=10):
    fin = time.time() + delai
    while not condition():
        if time.time() > fin:
            raise AssertionError("condition jamais remplie")
        time.sleep(0.02)


def saisie(sorties, lignes):
    """Lignes saisies ; un tuple (« attendre », texte) patiente jusqu'à ce que la vue l'affiche."""
    for x in lignes:
        if isinstance(x, tuple):
            attendre(lambda: any(x[1] in s for s in sorties))
        else:
            yield x


def test_message_du_terminal_visible_cote_api_et_fermeture_sans_arret_du_tour(serveur):
    sorties = []
    code = console.executer("x", saisie(sorties, ["bonjour depuis le terminal",
                                                  ("attendre", "── Agent au travail…"), "/quitter"]),
                            sorties.append)
    assert code == 0
    assert "── Agent au travail…" in sorties  # le suivi en direct montre les étapes
    # Même route que le chat : le message est celui de l'utilisateur (sans préfixe de tâche).
    assert serveur.lances[0]["message"].endswith("bonjour depuis le terminal")
    assert cli.appeler("GET", "/taches/x")["etat_execution"] == "en_cours"  # le tour continue
    assert serveur.arrets == []
    conv = cli.appeler("GET", "/taches/x/conversation")
    assert any(m["role"] == "utilisateur" and "bonjour depuis le terminal" in m["texte"] for m in conv)


def test_console_arret_arrete_le_tour(serveur):
    sorties = []
    console.executer("x", saisie(sorties, ["travaille", ("attendre", "── Agent au travail…"), "/arret",
                                           ("attendre", "arrêt demandé"), "/quitter"]),
                     sorties.append)
    assert serveur.arrets
    attendre(lambda: cli.appeler("GET", "/taches/x")["etat_execution"] != "en_cours")


def test_console_affiche_l_echange_existant(serveur):
    sorties = []
    console.executer("x", saisie(sorties, ["premier", ("attendre", "── Agent au travail…"), "/arret",
                                           ("attendre", "arrêt demandé")]), sorties.append)
    attendre(lambda: cli.appeler("GET", "/taches/x")["etat_execution"] != "en_cours")
    relue = []
    console.executer("x", iter(["/quitter"]), relue.append)  # le harnais factice relit « bonjour s-1 »
    assert "bonjour s-1" in relue and any(r.startswith("── Agent") for r in relue)


def test_console_tache_inconnue_code_1(serveur, capsys):
    assert console.main("inconnue") == 1
    assert "404" in capsys.readouterr().err


def test_historique_distingue_l_echange_des_etapes():
    msgs = [{"role": "utilisateur", "texte": "[Message de la tâche t]\nx", "horodatage": "2026-11-15T10:42:00"},
            {"role": "utilisateur", "texte": "fais-le", "horodatage": "2026-11-15T10:43:00"},
            {"role": "assistant", "texte": "je lis le dépôt", "outils": ["Bash git status"]},
            {"role": "assistant", "texte": "C'est fait.", "outils": ["Edit a.py"],
             "horodatage": "2026-11-15T10:45:00"}]
    masque = console.rendre_historique(msgs, console.Rendu())
    assert masque[0] == "── GoldenBrain · 10:42" and masque[2] == "── Vous · 10:43"
    assert masque[4:] == ["   (3 étapes masquées — /etapes)", "── Agent · 10:45", "C'est fait."]
    vu = console.rendre_historique(msgs, console.Rendu(etapes=True))
    assert vu[4:7] == ["   ⚙ je lis le dépôt", "   ⚙ Bash git status", "   ⚙ Edit a.py"]
    assert vu[-2:] == ["── Agent · 10:45", "C'est fait."]


def test_etape_grise_indentee_tronquee_et_repli_sans_couleurs():
    longue = "\n".join(f"ligne {i}" for i in range(10)) + "\n" + "x" * 500
    brut = console.Rendu().etape(longue)
    assert brut[0] == "   ⚙ ligne 0" and brut[1] == "     ligne 1"
    assert brut[-1] == "     … (7 lignes de plus)" and len(brut) == 5
    assert all("\x1b" not in x for x in brut)  # repli : aucun code ANSI
    couleur = console.Rendu(couleurs=True)
    assert couleur.etape("Bash ls")[0] == "\x1b[2;37m   ⚙ Bash ls\x1b[0m"  # gris atténué
    assert couleur.entete("Vous") == "\x1b[1m── Vous\x1b[0m"  # l'échange reste en texte normal


def test_direct_dernier_texte_devient_la_reponse_le_reste_des_etapes():
    d = console.Direct(console.Rendu(etapes=True))
    sortie = [x for e in [{"type": "tour_debut"}, {"type": "tour_texte", "texte": "je regarde"},
                          {"type": "tour_outil", "texte": "Read a.py"},
                          {"type": "tour_texte", "texte": "Voilà."}, {"type": "tour_fin", "statut": "fait"}]
              for x in d.evenement(e)]
    assert sortie == ["── Agent au travail…", "   ⚙ je regarde", "   ⚙ Read a.py", "── Agent", "Voilà.",
                      "── Fin du tour (fait)"]
    masque = console.Direct(console.Rendu())
    assert masque.evenement({"type": "tour_outil", "texte": "Read a.py"}) == []


def test_bascule_etapes_reaffiche_l_echange_avec_les_etapes(serveur):
    sorties = []
    console.executer("x", saisie(sorties, ["travaille", ("attendre", "── Agent au travail…"), "/arret",
                                           ("attendre", "arrêt demandé")]), sorties.append)
    attendre(lambda: cli.appeler("GET", "/taches/x")["etat_execution"] != "en_cours")
    relue = []
    console.executer("x", iter(["/etapes", "/quitter"]), relue.append)
    assert "   (1 étape masquée — /etapes)" in relue
    assert relue.index("(étapes affichées)") < relue.index("   ⚙ Read")


def test_titre_onglet_titre_de_la_tache_tronque_proprement():
    assert console.titre_onglet("A; B\x07") == "A, B"
    t = console.titre_onglet("Console GoldenBrain en terminal (version minimale) et la suite")
    assert t == "Console GoldenBrain en terminal…" and len(t) <= console.LARGEUR_TITRE


def test_titre_pose_par_osc_au_demarrage_si_terminal_ansi(serveur):
    sorties = []
    console.executer("x", iter(["/quitter"]), sorties.append, console.Rendu(couleurs=True))
    assert sorties[0].startswith("\x1b]0;") and sorties[0].endswith("\x07")


def test_ouvrir_onglet_windows_terminal_titre_de_la_tache_sans_titre_d_application(monkeypatch):
    lances = []
    monkeypatch.setattr(console.shutil, "which", lambda nom: "C:/wt.exe")
    monkeypatch.setattr(console, "lancer", lambda argv, nouvelle: lances.append((argv, nouvelle)))
    commande = console.ouvrir("t-1", "A; B", "http://127.0.0.1:8399", "C:/d p/orch.py")
    argv, nouvelle = lances[0]
    assert argv[:7] == ["C:/wt.exe", "-w", "0", "nt", "--title", "A, B", "--suppressApplicationTitle"]
    assert argv[7:] == commande and commande[1:] == ["C:/d p/orch.py", "console", "t-1", "--url",
                                                     "http://127.0.0.1:8399"]
    assert nouvelle is False


def test_ouvrir_sans_windows_terminal_repli_nouvelle_console(monkeypatch):
    lances = []
    monkeypatch.setattr(console.shutil, "which", lambda nom: None)
    monkeypatch.setattr(console, "lancer", lambda argv, nouvelle: lances.append((argv, nouvelle)))
    commande = console.ouvrir("t-1", "A", "http://127.0.0.1:8399", "orch.py")
    assert lances == [(commande, True)]


def test_route_console_toujours_disponible(config, vault, faux, monkeypatch):
    lances = []
    monkeypatch.setattr(console, "lancer", lambda argv, nouvelle: lances.append(argv))
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=f"http://127.0.0.1:{config.port}") as c:
        r = c.post("/api/taches/mere/console", headers=H)  # sans session : disponible quand même
        assert r.status_code == 200 and r.json()["commande"][2:4] == ["console", "mere"]
        assert c.post("/api/taches/inconnue/console", headers=H).status_code == 404
        assert c.post("/api/taches/mere/console").status_code == 403  # INV-API-1
    assert len(lances) == 1
