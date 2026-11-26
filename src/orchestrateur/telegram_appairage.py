"""Commande Telegram `/appairer` : code d'appareil ouvert par le connecteur, envoyé en image QR (INV-APPAIRAGE-2).

Rôle : depuis la discussion autorisée, ouvrir un code d'appairage d'appareil et l'y envoyer (QR PNG + lien).
Frontières : aucune décision de liste blanche (le connecteur l'a déjà prise) ; le registre des appareils
garde le code (INV-DISTANT-5) ; le code n'entre dans aucun journal, fil ni tâche.
Invariants portés : INV-APPAIRAGE-2 (appelé par le seul tri du connecteur ; au plus 3 codes par 10 min).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

from . import api_appareils, langues, qr

APPAIRER = "/appairer"
APPAIRER_MAX = 3  # codes ouverts par Telegram sur APPAIRER_FENETRE_S
APPAIRER_FENETRE_S = 600


def multipart(champs: dict, nom: str, fichier: bytes, type_: str) -> tuple[bytes, str]:
    """Corps `multipart/form-data` (champs texte puis un fichier) et son en-tête `Content-Type`."""
    limite = "orch" + os.urandom(8).hex()
    corps = b"".join(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                     for k, v in champs.items())
    corps += (f'--{limite}\r\nContent-Disposition: form-data; name="{nom}"; filename="{nom}.png"\r\n'
              f'Content-Type: {type_}\r\n\r\n').encode() + fichier + f"\r\n--{limite}--\r\n".encode()
    return corps, f"multipart/form-data; boundary={limite}"


def photo(client, chat: str, png: bytes, legende: str = "") -> None:
    """`sendPhoto` ; ErreurTelegram si l'image est refusée."""
    from .telegram import ErreurTelegram
    corps, type_ = multipart({"chat_id": chat, "caption": legende[:1000]}, "photo", png, "image/png")
    req = urllib.request.Request(f"{client.api}/bot{client.jeton}/sendPhoto", data=corps,
                                 headers={"Content-Type": type_})
    try:
        ok = json.loads(client._ouvrir(req, 30).decode("utf-8")).get("ok")
    except ValueError:
        ok = False
    if not ok:
        raise ErreurTelegram("sendPhoto : refus")


async def appairer(c, chat: str, texte: str, reponse_a: int | None) -> None:
    """`/appairer [nom]` : ouvre un code d'appareil (INV-DISTANT-5) et l'envoie dans la discussion autorisée.

    INV-APPAIRAGE-2 : appelé par le seul tri du connecteur, après la liste blanche et sur un message
    écrit par l'expéditeur (jamais un transfert) ; aucune route ni tâche ne l'atteint, et le code
    n'entre ni dans le fil de l'assistant ni dans un journal. Au plus APPAIRER_MAX codes par fenêtre.
    """
    from .telegram import ErreurTelegram, dans_un_fil  # import tardif : telegram importe ce module
    registre, t = c.appareils, time.time()
    base = api_appareils.adresse(c.config)
    if registre is None or not base or not c.config.distant.appareils:
        r = langues.t("serveur.telegram.appairer_inactif")
    elif len([x for x in c._appairages if t - x < APPAIRER_FENETRE_S]) >= APPAIRER_MAX:
        r = langues.t("serveur.telegram.appairer_limite")
        registre.noter("refus", "telegram", langues.t("serveur.telegram.appairer_limite")[:80], sauver=True)
    else:
        c._appairages = [x for x in c._appairages if t - x < APPAIRER_FENETRE_S] + [t]
        try:
            code = registre.ouvrir_code(texte[len(APPAIRER):].strip())
        except Exception as e:  # noqa: BLE001 — trop de codes ouverts : dit tel quel, sans code
            await c.envoyer(chat, str(e), c.tache_tri(), reponse_a)
            return
        registre.noter(langues.t("serveur.appareils.genre_ouverture_telegram"), "telegram", code["nom"], sauver=True)
        lien = f"{base}/appairer.html#{code['code']}"
        r = langues.t("serveur.telegram.appairer_lien", nom=code["nom"], minutes=code["valide_s"] // 60, lien=lien)
        try:
            await dans_un_fil(photo, c.client(), chat, qr.png(lien), r)
            return  # le lien est dans la légende de l'image ; rien n'est routé vers une tâche
        except ErreurTelegram:
            pass  # image refusée : le lien seul
    await c.envoyer(chat, r, c.tache_tri(), reponse_a)
