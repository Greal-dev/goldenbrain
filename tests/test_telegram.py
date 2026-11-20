"""Connecteur Telegram contre un faux serveur Telegram local (jamais le vrai) : liste blanche, texte,
photo, document, voix, tâche de tri, issue d'un envoi, réponse routée, reprise après coupure, jeton
absent des journaux (INV-TELEGRAM-1, INV-TELEGRAM-2), dialogue question → réponse libre, compte rendu à
boutons (INV-TELEGRAM-3), réglages par l'API."""

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, coffre, telegram
from orchestrateur.config import ConfigTelegram
from orchestrateur.moteur import Moteur
from test_moteur import executer, finir, moteur

JETON = "123456:SECRET-de-test-xyz"
CHAT = "4242"


class FauxTelegram:
    """Serveur HTTP local qui imite l'API de bot : getUpdates, getFile, fichiers, sendMessage, getMe."""

    def __init__(self):
        self.majs: list[dict] = []
        self.envoyes: list[dict] = []
        self.requetes: list[tuple[str, dict]] = []
        self.fichiers: dict[str, bytes] = {}
        self.webhook = ""  # adresse du webhook actif (ancien pipeline), vide = aucun
        self.pannes = 0  # nombre de prochaines requêtes qui échouent (coupure)
        self.n = 100
        faux = self

        class Gestion(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _repondre(self, code, corps, brut=False):
                donnees = corps if brut else json.dumps(corps).encode()
                self.send_response(code)
                self.end_headers()
                self.wfile.write(donnees)

            def do_GET(self):
                nom = self.path.rsplit("/", 1)[-1]
                self._repondre(200, faux.fichiers[nom], brut=True)

            def do_POST(self):
                corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path.endswith("/audio/transcriptions"):
                    assert self.headers["Authorization"] == "Bearer cle-transcription"
                    return self._repondre(200, {"text": "acheter du pain"})
                if faux.pannes:
                    faux.pannes -= 1
                    return self._repondre(502, {"ok": False, "description": "Bad Gateway"})
                jeton, methode = self.path.split("/")[1][3:], self.path.split("/")[2]
                if jeton != JETON:
                    return self._repondre(401, {"ok": False, "description": "Unauthorized"})
                params = json.loads(corps or b"{}")
                faux.requetes.append((methode, params))
                if methode == "getUpdates":
                    debut = params.get("offset", 0)
                    return self._repondre(200, {"ok": True, "result": [
                        u for u in faux.majs if u["update_id"] >= debut]})
                if methode == "getFile" and params["file_id"] == "trop-gros":
                    return self._repondre(400, {"ok": False, "description": "Bad Request: file is too big"})
                if methode == "getFile":
                    return self._repondre(200, {"ok": True, "result": {"file_path": f"x/{params['file_id']}"}})
                if methode == "sendMessage":
                    faux.n += 1
                    faux.envoyes.append({**params, "message_id": faux.n})
                    return self._repondre(200, {"ok": True, "result": {"message_id": faux.n}})
                if methode == "getWebhookInfo":
                    return self._repondre(200, {"ok": True, "result": {"url": faux.webhook}})
                if methode == "deleteWebhook":
                    faux.webhook = ""
                    return self._repondre(200, {"ok": True, "result": True})
                if methode == "getMe":
                    return self._repondre(200, {"ok": True, "result": {"username": "essai_bot"}})
                if methode == "answerCallbackQuery":
                    return self._repondre(200, {"ok": True, "result": True})
                return self._repondre(404, {"ok": False, "description": "Not Found"})

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
        self.url = f"http://127.0.0.1:{self.serveur.server_port}"
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def message(self, uid, chat=CHAT, **champs):
        self.majs.append({"update_id": uid, "message": {"message_id": uid * 10, "date": 1763200000,
                                                         "chat": {"id": int(chat)}, **champs}})


@pytest.fixture
def tg(config, monkeypatch):
    faux = FauxTelegram()
    config.telegram = ConfigTelegram(actif=True, api=faux.url, discussions=[CHAT],
                                     conteneur="Projets/C1-Alpha", attente_s=0)
    monkeypatch.setenv("GOLDENBRAIN_TELEGRAM_JETON", JETON)
    monkeypatch.delenv("GOLDENBRAIN_TRANSCRIPTION_CLE", raising=False)
    yield faux
    faux.serveur.shutdown()


def relever(config, vault, faux_harnais, *etapes):
    """Exécute dans une même boucle : relèves et appels du connecteur ; rend (connecteur, moteur)."""
    async def scenario():
        m = moteur(config, vault, faux_harnais)
        c = telegram.Connecteur(m)
        for etape in etapes:
            await etape(c)
            await finir(m)
        return c, m
    return executer(scenario())


async def une_releve(c):
    await c.relever()


def test_liste_blanche_ignore_sans_contenu_au_journal(config, vault, faux, tg, caplog):
    tg.message(1, chat="777", text="texte confidentiel")
    with caplog.at_level(logging.WARNING):
        c, _ = relever(config, vault, faux, une_releve)
    assert not faux.lances and not c.etat.get("tache_tri")
    assert "777" in caplog.text and "confidentiel" not in caplog.text
    assert c.etat["offset"] == 2  # INV-TELEGRAM-1 : ignoré, mais consommé


TRANSFERE = {"forward_origin": {"type": "user", "date": 1763100000}}


def test_texte_transfere_cree_la_tache_de_tri_et_lui_soumet_l_envoi(config, vault, faux, tg):
    tg.message(1, text="Rappeler le plombier", **TRANSFERE)
    c, m = relever(config, vault, faux, une_releve)
    tri = c.etat["tache_tri"]
    t = vault.tache(tri)
    assert t.titre == "Assistant Telegram" and t.conteneur == "Projets/C1-Alpha"
    assert t.fm.get("nature") == "permanente"
    note = config.vault.racine / c.etat["envois"]["1"]["note"]
    assert note.parent.name == "telegram" and "Rappeler le plombier" in note.read_text("utf-8")
    msg = faux.lances[0]["message"]
    assert "[Envoi Telegram n°1]" in msg and "orch creer" in msg and c.etat["envois"]["1"]["note"] in msg
    assert "[contenu] Rappeler le plombier" in msg  # INV-TELEGRAM-4 : transféré = contenu
    # Second envoi : même tâche de tri, pas une nouvelle.
    tg.message(2, text="Deuxième", **TRANSFERE)
    c2, _ = relever(config, vault, faux, une_releve)
    assert c2.etat["tache_tri"] == tri and c2.etat["compteur"] == 2


def test_photo_et_document_ranges_sous_le_vault(config, vault, faux, tg):
    tg.fichiers.update({"p-grand": b"JPEG", "d-1": b"%PDF"})
    tg.message(1, caption="Facture", photo=[{"file_id": "p-petit"}, {"file_id": "p-grand"}])
    tg.message(2, document={"file_id": "d-1", "file_name": "../../hors du vault.pdf"})
    c, _ = relever(config, vault, faux, une_releve)
    reception = config.vault.racine / "Inbox" / "telegram"
    fichiers = {p.name: p.read_bytes() for p in reception.iterdir() if not p.name.endswith(".md")}
    assert sorted(fichiers.values()) == [b"%PDF", b"JPEG"]
    assert any(n.endswith("-hors-du-vault.pdf") for n in fichiers)  # nom rendu sûr, resté dans le dossier
    note = (config.vault.racine / c.etat["envois"]["1"]["note"]).read_text("utf-8")
    assert "Facture" in note and "photo : ![[Inbox/telegram/" in note


def test_voix_sans_fournisseur_est_rangee_et_signalee(config, vault, faux, tg):
    tg.fichiers["v-1"] = b"OGG"
    tg.message(1, voice={"file_id": "v-1"})
    c, _ = relever(config, vault, faux, une_releve)
    assert "sans transcription" in faux.lances[0]["message"]
    assert any(p.name.endswith("note-vocale.ogg") for p in (config.vault.racine / "Inbox/telegram").iterdir())


def test_voix_transcrite_par_le_fournisseur(config, vault, faux, tg, monkeypatch):
    config.telegram.transcription_url = tg.url + "/v1/audio/transcriptions"
    monkeypatch.setenv("GOLDENBRAIN_TRANSCRIPTION_CLE", "cle-transcription")
    tg.fichiers["v-1"] = b"OGG"
    tg.message(1, voice={"file_id": "v-1"})
    relever(config, vault, faux, une_releve)
    assert "Transcription : acheter du pain" in faux.lances[0]["message"]


def test_agent_de_tri_cree_la_tache_puis_la_reponse_lui_revient(config, vault, faux, tg):
    tg.message(1, text="Ranger le devis du couvreur", **TRANSFERE)

    async def agent_de_tri(c):
        # Ce que fait `orch creer … --envoi 1` : POST /api/taches puis l'issue de l'envoi.
        ident = c.moteur.creer("Comparer le devis du couvreur", conteneur="Projets/C1-Alpha")
        r = await c.issue(1, ident, True)
        assert r["texte"].startswith("Tâche créée : Comparer le devis du couvreur — ")
        c.cree = ident

    async def reponse(c):
        bot = tg.envoyes[-1]
        tg.message(2, text="Fais-le avant vendredi", reply_to_message={"message_id": bot["message_id"]})
        await c.relever()

    c, _ = relever(config, vault, faux, une_releve, agent_de_tri, reponse)
    envoye = tg.envoyes[0]
    assert envoye["chat_id"] == CHAT and envoye["reply_to_message_id"] == 10
    assert faux.lances[-1]["message"].startswith("[Réponse Telegram]\n[instruction] Fais-le avant vendredi")
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == c.cree
    note = (config.vault.racine / c.etat["envois"]["1"]["note"]).read_text("utf-8")
    assert f"Rangé : [[{c.cree}]]" in note


def test_question_d_un_agent_et_reponse_routee(config, vault, faux, tg):
    async def question(c):
        await c.question("mere", "Quel budget ?")
        tg.message(1, text="500 €", reply_to_message={"message_id": tg.envoyes[-1]["message_id"]})
        await c.relever()

    relever(config, vault, faux, question)
    assert tg.envoyes[0]["text"] == "[Mère] Quel budget ?"
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == "mere" and "500 €" in faux.lances[-1]["message"]


def test_reprise_apres_coupure_et_decalage_persiste(config, vault, faux, tg, monkeypatch):
    monkeypatch.setattr(telegram, "PAUSE_S", 0)
    tg.pannes = 1
    tg.message(1, text="un")

    async def boucle(c):
        tache = asyncio.create_task(c.boucle())
        for _ in range(200):
            if c.etat.get("offset") == 2:
                break
            await asyncio.sleep(0.02)
        tache.cancel()

    c, _ = relever(config, vault, faux, boucle)
    assert c.etat["offset"] == 2 and len(faux.lances) == 1  # la coupure n'a rien perdu
    tg.message(2, text="deux")
    relever(config, vault, faux, une_releve)  # nouveau connecteur : repart du décalage persisté
    assert [p.get("offset") for m_, p in tg.requetes if m_ == "getUpdates"][-1] == 2
    assert len(faux.lances) == 2


def test_jeton_absent_des_journaux_et_des_erreurs(config, vault, faux, tg, caplog, monkeypatch):
    monkeypatch.setattr(telegram, "PAUSE_S", 0)
    tg.pannes = 10**6  # coupure continue : sous Linux, trois pannes se résorbent avant la première lecture de l'erreur

    async def boucle(c):
        tache = asyncio.create_task(c.boucle())
        for _ in range(100):
            if c.erreur:
                break
            await asyncio.sleep(0.02)
        tache.cancel()
        c.vue = c.erreur

    with caplog.at_level(logging.DEBUG):
        c, _ = relever(config, vault, faux, boucle)
    assert c.vue and "502" in c.vue
    assert JETON not in caplog.text and JETON not in c.vue
    assert telegram.masquer(f"https://x/bot{JETON}/getMe", JETON) == "https://x/bot***/getMe"
    assert JETON not in json.dumps(c.public())


def test_desactive_par_defaut_ne_lit_pas(config, vault, faux, tg):
    assert ConfigTelegram().actif is False

    async def demarrer(c):
        c.cfg.actif = False
        c.demarrer()
        assert c.tache is None
        c.cfg.actif = True
        c.demarrer()
        assert c.tache is not None
        c.arreter()

    relever(config, vault, faux, demarrer)


def test_reglages_par_l_api(config, vault, faux, tg, tmp_path):
    config.chemin = tmp_path / "config.toml"
    config.chemin.write_text("[serveur]\nport = 8399\n", encoding="utf-8")
    config.telegram.actif = False
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url="http://127.0.0.1:8399") as client:
        h = {"X-Orchestrateur": "1"}
        etat = client.get("/api/telegram").json()
        assert etat["jeton"] == "variable" and etat["actif"] is False and JETON not in json.dumps(etat)
        assert client.post("/api/telegram/tester", headers=h).json() == {
            "ok": True, "bot": "@essai_bot", "en_marche": False, "bienvenue": CHAT}
        r = client.put("/api/telegram", headers=h, json={"discussions": ["12", " -100 "], "reception": "Inbox/tg"})
        assert r.status_code == 200 and r.json()["discussions"] == ["12", "-100"]
        texte = config.chemin.read_text("utf-8")
        assert texte.startswith("[serveur]\nport = 8399\n") and 'discussions = ["12", "-100"]' in texte
        assert "jeton" not in texte.split("[telegram]")[1]
        assert client.put("/api/telegram", headers=h, json={"reception": "../dehors"}).status_code == 400
        assert config.telegram.reception == "Inbox/tg"  # un refus ne change rien
        assert client.put("/api/telegram", headers=h, json={"discussions": ["abc"]}).status_code == 400
        assert client.post("/api/telegram/envois/9/issue", headers=h, json={"tache": "mere"}).status_code == 404


@pytest.mark.skipif(coffre.WINDOWS, reason="fichier 0600 : hors Windows")
def test_jeton_en_fichier_0600_hors_windows(tmp_path):
    fichier = tmp_path / "etat" / "telegram.jeton"
    coffre.proteger(JETON, fichier)
    assert fichier.stat().st_mode & 0o777 == 0o600  # INV-TELEGRAM-2 : lisible de l'utilisateur seul
    assert coffre.lire("VARIABLE_ABSENTE", fichier) == (JETON, "fichier")
    coffre.proteger(JETON + "2", fichier)  # remplacement : droits conservés, aucun reste temporaire
    assert fichier.stat().st_mode & 0o777 == 0o600 and [f.name for f in fichier.parent.iterdir()] == ["telegram.jeton"]
    coffre.proteger("", fichier)
    assert not fichier.exists()


def test_connexion_jeton_reconnaissance_webhook_bienvenue(config, vault, faux, tg, tmp_path, monkeypatch):
    monkeypatch.delenv("GOLDENBRAIN_TELEGRAM_JETON")
    config.telegram.actif = False
    config.telegram.discussions = []
    config.telegram.jeton_fichier = str(tmp_path / "telegram.jeton")
    tg.webhook = "https://n8n.exemple/webhook"
    tg.message(1, chat=CHAT, text="SECRET-contenu-du-message")
    tg.majs[0]["message"]["chat"].update({"first_name": "Ada", "username": "ada"})
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url="http://127.0.0.1:8399") as client:
        h = {"X-Orchestrateur": "1"}
        r = client.put("/api/telegram", headers=h, json={"jeton": JETON})  # accepté sur tous les systèmes
        assert r.status_code == 200 and r.json()["jeton"] == "fichier" and JETON not in r.text
        r = client.post("/api/telegram/reconnaitre", headers=h).json()
        assert r["ok"] and r["bot"] == "@essai_bot" and r["webhook"] and r["discussions"] == []
        assert not [m for m, _ in tg.requetes if m == "getUpdates"]  # webhook actif : aucune lecture
        assert client.post("/api/telegram/webhook/desactiver", headers=h).json() == {"ok": True}
        r = client.post("/api/telegram/reconnaitre", headers=h)
        assert r.json()["discussions"] == [{"id": CHAT, "nom": "Ada (@ada)"}]
        assert "SECRET-contenu" not in r.text and JETON not in r.text  # nom seulement, jamais le contenu
        assert all("offset" not in p for m, p in tg.requetes if m == "getUpdates")  # rien n'est consommé
        assert client.post("/api/telegram/tester", headers=h).json()["bienvenue"] == ""  # pas encore autorisée
        client.put("/api/telegram", headers=h, json={"discussions": [CHAT]})
        t = client.post("/api/telegram/tester", headers=h).json()
        assert t == {"ok": True, "bot": "@essai_bot", "en_marche": False, "bienvenue": CHAT}
        assert tg.envoyes[-1]["chat_id"] == CHAT and "connecté" in tg.envoyes[-1]["text"]


def test_reconnaissance_sans_jeton_explique(config, vault, faux, tg, tmp_path, monkeypatch):
    monkeypatch.delenv("GOLDENBRAIN_TELEGRAM_JETON")
    config.telegram.jeton_fichier = str(tmp_path / "absent.jeton")
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url="http://127.0.0.1:8399") as client:
        r = client.post("/api/telegram/reconnaitre", headers={"X-Orchestrateur": "1"}).json()
        assert r["ok"] is False and "jeton du bot absent" in r["motif"]


@pytest.mark.skipif(not coffre.WINDOWS, reason="DPAPI : Windows seulement")
def test_jeton_protege_par_dpapi(config, vault, faux, tg, tmp_path, monkeypatch):
    monkeypatch.delenv("GOLDENBRAIN_TELEGRAM_JETON")
    fichier = tmp_path / "telegram.jeton"
    coffre.proteger(JETON, fichier)
    assert JETON.encode() not in fichier.read_bytes()  # INV-TELEGRAM-2 : jamais en clair
    assert coffre.lire("GOLDENBRAIN_TELEGRAM_JETON", fichier) == (JETON, "fichier")
    coffre.proteger("", fichier)
    assert not fichier.exists()


def test_envoi_en_echec_durable_ne_bloque_pas_les_suivants(config, vault, faux, tg):
    tg.message(1, document={"file_id": "trop-gros", "file_name": "film.mp4"})
    tg.message(2, text="suivant")
    c, _ = relever(config, vault, faux, une_releve)
    assert c.etat["offset"] == 3 and len(faux.lances) == 1 and "suivant" in faux.lances[0]["message"]


def test_cli_creer_avec_envoi_previent_telegram(monkeypatch, capsys):
    from orchestrateur import cli
    journal = []

    def appeler(methode, chemin, corps=None):
        journal.append((methode, chemin, corps))
        if chemin == "/taches":
            return {"id": "t9", "titre": "Payer la facture", "fil_ariane": ["C1", "Alpha"]}
        raise cli.ErreurCli("erreur 409 : Telegram : réseau")

    monkeypatch.setattr(cli, "appeler", appeler)
    assert cli.main(["creer", "Payer la facture", "--conteneur", "Projets/C1-Alpha", "--envoi", "3"]) == 0
    assert journal[1][:2] == ("POST", "/telegram/envois/3/issue") and journal[1][2] == {"tache": "t9", "cree": True}
    sortie = capsys.readouterr().out
    assert "tâche créée : t9" in sortie and "orch rattacher 3 t9" in sortie


def _bouton(tg, uid, donnee, message_id, chat=CHAT):
    tg.majs.append({"update_id": uid, "callback_query": {
        "id": f"cb{uid}", "data": donnee,
        "message": {"message_id": message_id, "chat": {"id": int(chat)}}}})


def test_question_libre_repond_sans_reponse_directe(config, vault, faux, tg):
    async def question(c):
        await c.question("mere", "Quel budget ?")
        tg.message(1, text="500 €")  # message libre : pas de reply, la question est en attente
        await c.relever()

    c, _ = relever(config, vault, faux, question)
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == "mere" and "500 €" in faux.lances[-1]["message"]
    assert not c.etat["envois"] and "attente" not in c.etat  # rien rangé comme envoi


def test_compte_rendu_valider_clot_la_tache(config, vault, faux, tg):
    async def compte_rendu(c):
        await c.question("mere", "Enregistré : https://drive.example/piece", boutons=True)
        bot = tg.envoyes[-1]
        assert bot["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "valider"
        _bouton(tg, 1, "valider", bot["message_id"], chat="777")  # hors liste blanche : ignoré
        await c.relever()
        assert vault.tache("mere").statut != "fait"
        _bouton(tg, 2, "valider", bot["message_id"])
        await c.relever()

    relever(config, vault, faux, compte_rendu)
    assert vault.tache("mere").statut == "fait"  # INV-TELEGRAM-3 : seul Valider, geste humain
    toasts = [p for m, p in tg.requetes if m == "answerCallbackQuery"]
    assert toasts[-1]["callback_query_id"] == "cb2" and toasts[-1]["text"] == "Tâche validée."


def test_renvoyer_envoie_la_remarque_suivante_a_la_tache(config, vault, faux, tg):
    async def renvoi(c):
        await c.question("mere", "Enregistré.", boutons=True)
        _bouton(tg, 1, "renvoyer", tg.envoyes[-1]["message_id"])
        await c.relever()
        tg.message(2, text="Ajoute le montant")
        await c.relever()

    relever(config, vault, faux, renvoi)
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == "mere"
    assert faux.lances[-1]["message"].startswith("[Réponse Telegram]\n[instruction] Ajoute le montant")
    assert vault.tache("mere").statut != "fait"


def test_creer_lancer_envoie_la_mission_au_premier_tour(config, vault, faux, tg):
    async def creation(c):
        c.cree = c.moteur.creer("Déposer la pièce", conteneur="Projets/C1-Alpha", lancer=True,
                                mission="Enregistre le PDF et rends l'adresse")

    c, _ = relever(config, vault, faux, creation)
    assert faux.lances[-1]["message"] == "Enregistre le PDF et rends l'adresse"
    assert faux.lances[-1]["env"]["ORCH_TACHE"] == c.cree


def test_cli_creer_lancer_et_mission_transmis(monkeypatch):
    from orchestrateur import cli
    journal = []

    def appeler(methode, chemin, corps=None):
        journal.append((methode, chemin, corps))
        return {"id": "t9", "titre": "Payer la facture", "fil_ariane": ["C1"]}

    monkeypatch.setattr(cli, "appeler", appeler)
    assert cli.main(["creer", "Déposer", "--lancer", "--mission", "Range le PDF"]) == 0
    assert journal[0][2]["lancer"] is True and journal[0][2]["mission"] == "Range le PDF"
    with pytest.raises(SystemExit):
        cli.main(["creer", "Déposer", "--mission", "Range le PDF"])  # mission attend --lancer


def test_cli_telegram_validation_demande_les_boutons(monkeypatch, capsys):
    from orchestrateur import cli
    journal = []
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: journal.append((c, corps)))
    monkeypatch.setenv("ORCH_TACHE", "t9")
    assert cli.main(["telegram", "Pièce enregistrée", "--validation"]) == 0
    assert journal == [("/telegram/question", {"tache": "t9", "texte": "Pièce enregistrée", "boutons": True})]
    assert "Valider / Renvoyer" in capsys.readouterr().out
