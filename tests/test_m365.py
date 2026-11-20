"""Connecteur Microsoft 365 Copilot contre un serveur factice : aucun appel réel (INV-M365-1..3 détaillés
dans docs/ARCHITECTURE.md)."""

import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from orchestrateur import cli, m365

CLIENT = "00000000-0000-0000-0000-000000000001"


class Faux(BaseHTTPRequestHandler):
    journal: list = []
    attente = 0  # réponses « authorization_pending » avant d'accorder le code d'appareil

    def log_message(self, *a):
        pass

    def do_POST(self):
        brut = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        corps = (dict(urllib.parse.parse_qsl(brut)) if "urlencoded" in self.headers["Content-Type"]
                 else json.loads(brut))
        Faux.journal.append((self.path, corps, self.headers.get("Authorization")))
        code, rep = 200, {}
        if self.path.endswith("/devicecode"):
            rep = {"device_code": "dc", "user_code": "ABCD", "verification_uri": "https://exemple",
                   "message": "Ouvrez la page et saisissez ABCD", "interval": 1, "expires_in": 60}
        elif self.path.endswith("/token") and corps.get("grant_type", "").endswith("device_code"):
            if Faux.attente:
                Faux.attente -= 1
                code, rep = 400, {"error": "authorization_pending"}
            else:
                rep = {"access_token": "acces-0", "refresh_token": "rafraichi-1"}
        elif self.path.endswith("/token"):
            if corps["refresh_token"] == "perime":
                code, rep = 400, {"error": "invalid_grant"}
            else:
                rep = {"access_token": "acces-" + corps["scope"].split()[0], "refresh_token": "rafraichi-2"}
        elif self.path == "/rest/conversations":
            code, rep = 201, {"id": "conv/1"}
        elif self.path == "/rest/conversations/conv%2F1/chat":
            rep = {"messages": [{"text": corps["message"]["text"]}, {
                "text": "Le budget est de 12 k€ [^1^].", "attributions": [
                    {"attributionType": "citation", "providerDisplayName": "Budget.xlsx",
                     "seeMoreWebUrl": "https://exemple/budget"},
                    {"attributionType": "annotation", "providerDisplayName": "Personne"}]}]}
        elif self.path == "/v1.0/copilot/retrieval":
            rep = {"retrievalHits": [{"webUrl": "https://exemple/doc", "resourceMetadata": {
                "title": "Note", "author": "Auteur"}, "extracts": [{"text": " Extrait un "}, {"text": ""}]}]}
        else:
            code, rep = 403, {"error": {"code": "Forbidden", "message": "interdit"}}
        donnees = json.dumps(rep).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)


@pytest.fixture
def conf(tmp_path):
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Faux)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    Faux.journal, Faux.attente = [], 0
    base = f"http://127.0.0.1:{serveur.server_port}"
    c = m365.ConfigM365(actif=True, client_id=CLIENT, jeton=str(tmp_path / "jeton.bin"),
                        login_url=f"{base}/login", chat_url=f"{base}/rest",
                        retrieval_url=f"{base}/v1.0/copilot/retrieval")
    yield c
    serveur.shutdown()


def test_connecter_par_code_d_appareil_enregistre_le_jeton_chiffre(conf, tmp_path):
    Faux.attente = 2
    messages = []
    m365.connecter(conf, afficher=messages.append, attendre=lambda s: None)
    assert messages[0] == "Ouvrez la page et saisissez ABCD"
    assert m365.lire_jeton(conf) == "rafraichi-1"
    if sys.platform == "win32":  # INV-M365-2 : chiffré DPAPI, jamais en clair sur disque
        assert b"rafraichi" not in (tmp_path / "jeton.bin").read_bytes()
    assert "offline_access" in Faux.journal[0][1]["scope"]


def test_demander_rend_la_reponse_et_les_seules_citations(conf):
    m365.ecrire_jeton(conf, "r0")
    r = m365.demander(conf, "Quel budget ?")
    assert r == {"texte": "Le budget est de 12 k€ [^1^].",
                 "citations": [{"titre": "Budget.xlsx", "url": "https://exemple/budget"}]}
    jeton, ouvrir, chat = Faux.journal
    assert jeton[1]["scope"] == f"{conf.chat_portee} offline_access"
    assert ouvrir[0] == "/rest/conversations" and ouvrir[2] == f"Bearer acces-{conf.chat_portee}"
    assert chat[1] == {"message": {"text": "Quel budget ?"}, "locationHint": {"timeZone": "Europe/Paris"},
                       "contextualResources": {"webContext": {"isWebEnabled": False}}}
    assert m365.lire_jeton(conf) == "rafraichi-2"  # jeton renouvelé conservé


def test_contexte_rend_les_extraits(conf):
    m365.ecrire_jeton(conf, "r0")
    hits = m365.contexte(conf, "note de cadrage", nombre=99)
    assert hits == [{"titre": "Note", "auteur": "Auteur", "url": "https://exemple/doc",
                     "extraits": [" Extrait un ", ""]}]
    corps = Faux.journal[-1][1]
    assert corps["dataSource"] == "sharePoint" and corps["maximumNumberOfResults"] == 25
    assert m365.rendre_contexte(hits) == ["[1] Note (Auteur) — https://exemple/doc", "    Extrait un"]


def test_lecture_seule_trois_points_d_appel(conf):
    """INV-M365-1 : hors connexion, seuls ces chemins sont jamais appelés."""
    m365.ecrire_jeton(conf, "r0")
    m365.demander(conf, "q")
    m365.contexte(conf, "q", source="oneDriveBusiness")
    chemins = {p for p, _, _ in Faux.journal if not p.startswith("/login/")}
    assert chemins == {"/rest/conversations", "/rest/conversations/conv%2F1/chat", "/v1.0/copilot/retrieval"}


def test_desactive_par_defaut_n_appelle_rien(conf):
    conf.actif = False
    with pytest.raises(m365.ErreurM365, match="désactivé"):
        m365.demander(conf, "q")
    assert m365.ConfigM365().actif is False and Faux.journal == []


def test_jeton_dans_le_depot_refuse(conf):
    conf.jeton = str(m365.RACINE_DEPOT / "jeton.bin")
    with pytest.raises(m365.ErreurM365, match="hors du dépôt"):
        m365.ecrire_jeton(conf, "r0")


def test_jeton_perime_demande_une_reconnexion_sans_l_afficher(conf):
    m365.ecrire_jeton(conf, "perime")
    with pytest.raises(m365.ErreurM365, match="orch m365 connecter") as e:
        m365.contexte(conf, "q")
    assert "perime" not in str(e.value)


def test_erreurs_lisibles(conf):
    m365.ecrire_jeton(conf, "r0")
    conf.retrieval_url = conf.chat_url + "/inconnu"
    with pytest.raises(m365.ErreurM365, match="403 : interdit"):
        m365.contexte(conf, "q")
    with pytest.raises(m365.ErreurM365, match="trop longue"):
        m365.demander(conf, "x" * 1501)
    with pytest.raises(m365.ErreurM365, match="source inconnue"):
        m365.contexte(conf, "q", source="mail")


def test_commande_orch(conf, monkeypatch, capsys, tmp_path):
    m365.ecrire_jeton(conf, "r0")
    monkeypatch.setattr(m365, "charger", lambda: conf)
    assert cli.main(["m365", "demander", "Quel budget ?"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "[1] Budget.xlsx — https://exemple/budget"
    conf.actif = False
    assert cli.main(["m365", "contexte", "q"]) == 1
    assert "désactivé" in capsys.readouterr().err


def test_charger_lit_la_section(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(f'[m365]\nactif = true\nclient_id = "{CLIENT}"\nsource = "externalItem"\n', "utf-8")
    c = m365.charger(f)
    assert (c.actif, c.client_id, c.source) == (True, CLIENT, "externalItem")
    f.write_text('[m365]\nsource = "mail"\n', "utf-8")
    with pytest.raises(ValueError):
        m365.charger(f)
