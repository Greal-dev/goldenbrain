"""Connexion guidée d'un bot Telegram : reconnaître sa discussion, détecter un webhook, message de bienvenue.

Rôle : à partir d'un `Client` déjà muni du jeton, lit les derniers messages reçus par le bot pour proposer
les discussions (identifiant + nom affichable), signale un webhook actif et le désactive à la demande.
Porte aussi la transcription des notes vocales (fournisseur compatible OpenAI, `transcrire`).
Frontières : aucun état, aucun accès au vault ; jamais le contenu d'un message ni le jeton dans le
résultat ; `getUpdates` sans décalage, donc sans consommer les messages (le connecteur les relira).
Invariants portés : INV-TELEGRAM-1 (un seul lecteur : 409 expliqué, jamais contourné), INV-TELEGRAM-2.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import langues


def bienvenue() -> str:
    return langues.t("serveur.telegram_connexion.bienvenue")


def fichier_jeton(config) -> Path:
    """Fichier du jeton : `[telegram] jeton_fichier`, sinon `<donnees>/etat/telegram.jeton` (INV-TELEGRAM-2)."""
    c = config.telegram
    return Path(c.jeton_fichier) if c.jeton_fichier else config.donnees / "etat" / "telegram.jeton"


def nom_discussion(chat: dict) -> str:
    """Nom affichable d'une discussion : prénom nom, @utilisateur, ou titre de groupe (jamais de contenu)."""
    nom = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
    if chat.get("username"):
        nom = f"{nom} (@{chat['username']})" if nom else f"@{chat['username']}"
    return nom or str(chat.get("title") or chat.get("id"))


def reconnaitre(client, vues: dict[str, dict] | None = None) -> dict:
    """{bot, webhook, discussions:[{id, nom}]} ; sans getUpdates tant qu'un webhook est actif (409 sûr).

    `vues` (connecteur en marche) : discussions déjà lues par sa boucle ; un second getUpdates
    l'interromprait (409, un seul lecteur par bot : INV-TELEGRAM-1)."""
    moi = client.appel("getMe", {}, 15)
    info = client.appel("getWebhookInfo", {}, 15) or {}
    resultat = {"bot": "@" + str(moi.get("username", "?")), "webhook": str(info.get("url") or ""),
                "discussions": []}
    if resultat["webhook"]:
        return resultat
    chats = list(vues.values()) if vues is not None else [
        (u.get("message") or {}).get("chat") or {}
        for u in client.appel("getUpdates", {"timeout": 0, "limit": 100, "allowed_updates": ["message"]}, 15) or []]
    trouvees = {str(c["id"]): {"id": str(c["id"]), "nom": nom_discussion(c)} for c in chats if c.get("id") is not None}
    resultat["discussions"] = list(trouvees.values())
    return resultat


def desactiver_webhook(client) -> None:
    # Sans drop_pending_updates : les messages en attente ne sont pas perdus.
    client.appel("deleteWebhook", {"drop_pending_updates": False}, 15)


def transcrire(url: str, modele: str, cle: str, octets: bytes, nom: str) -> str:
    """Transcription par un fournisseur compatible OpenAI (`/audio/transcriptions`, multipart)."""
    borne = uuid.uuid4().hex
    corps = (f"--{borne}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{modele}\r\n"
             f"--{borne}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nom}\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8") + octets + \
        f"\r\n--{borne}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=corps, headers={
        "Authorization": f"Bearer {cle}", "Content-Type": f"multipart/form-data; boundary={borne}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return str(json.loads(r.read().decode("utf-8")).get("text", "")).strip()
    except (urllib.error.URLError, OSError, ValueError) as e:
        from .telegram import ErreurTelegram, masquer  # import tardif : telegram importe ce module
        raise ErreurTelegram(masquer(f"transcription : {e}", cle)) from None
