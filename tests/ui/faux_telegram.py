"""Faux serveur de l'API Telegram pour les scénarios d'interface (aucun réseau, INV-TELEGRAM-1).

Rôle : répond à getMe, getWebhookInfo, deleteWebhook, getUpdates (un message d'Ada) et sendMessage.
Frontières : un seul jeton valable (`JETON`) ; `webhook` et `envoyes` se lisent depuis le test."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JETON = "123456:jeton-de-scenario"
CHAT = 777


class FauxTelegram:
    def __init__(self):
        self.webhook = "https://ancien.exemple/hook"
        self.envoyes: list[dict] = []
        faux = self

        class Gestion(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                jeton, methode = self.path.split("/")[1][3:], self.path.split("/")[2]
                if jeton != JETON:
                    return self._rendre({"ok": False, "description": "Unauthorized"}, 401)
                params = json.loads(corps or b"{}")
                if methode == "getMe":
                    return self._rendre({"ok": True, "result": {"username": "essai_bot"}})
                if methode == "getWebhookInfo":
                    return self._rendre({"ok": True, "result": {"url": faux.webhook}})
                if methode == "deleteWebhook":
                    faux.webhook = ""
                    return self._rendre({"ok": True, "result": True})
                if methode == "getUpdates":
                    if faux.webhook:
                        return self._rendre({"ok": False, "description": "Conflict: webhook is active"}, 409)
                    if params.get("offset", 0) > 1:  # message consommé
                        return self._rendre({"ok": True, "result": []})
                    return self._rendre({"ok": True, "result": [{"update_id": 1, "message": {
                        "message_id": 10, "date": 1763200000, "text": "bonjour",
                        "chat": {"id": CHAT, "type": "private", "first_name": "Ada", "username": "ada"}}}]})
                if methode == "sendMessage":
                    faux.envoyes.append(params)
                    return self._rendre({"ok": True, "result": {"message_id": 11}})
                return self._rendre({"ok": False, "description": "Not Found"}, 404)

            def _rendre(self, corps, code=200):
                self.send_response(code)
                self.end_headers()
                self.wfile.write(json.dumps(corps).encode())

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
        self.url = f"http://127.0.0.1:{self.serveur.server_port}"
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def arreter(self):
        self.serveur.shutdown()
