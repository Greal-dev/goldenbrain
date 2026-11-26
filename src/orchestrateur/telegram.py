"""Connecteur Telegram : instruction libre à l'assistant, envoi (transfert, pièce) rangé par lui.

Rôle : lecture longue de `getUpdates` (décalage persisté, reprise après coupure), liste blanche des
discussions, pièces et note de capture rangées dans le dossier de réception du vault, tâche permanente
de tri (conversation sur le moteur du rôle `tri`), réponse d'une ligne sur Telegram, routage d'une
réponse Telegram vers sa tâche, question d'un agent (`orch telegram`) dont le message libre suivant
est la réponse, compte rendu à boutons Valider / Renvoyer, choix et gestes de l'assistant (`telegram_assistant`),
`/nouveau`, transcription facultative des notes vocales.
Frontières : API HTTP de Telegram par urllib (aucune dépendance) ; agit sur les tâches par le moteur
(`creer`, `soumettre`) et, pour Valider, par `vault.poser_statut` (geste humain) ; n'écrit dans le
vault que sous le dossier de réception ; l'état (décalage, envois, routes, question en attente) vit
dans `<donnees>/etat/telegram.json`.
Commande `/appairer` : code d'appareil ouvert par le connecteur seul (INV-APPAIRAGE-2).
Invariants portés : INV-TELEGRAM-1 (désactivé par défaut, un seul lecteur, liste blanche),
INV-TELEGRAM-2 (jeton jamais écrit en clair ni journalisé), INV-TELEGRAM-3 (un message ou un bouton
n'est jamais un ordre de paiement ; seul un bouton humain change une tâche), INV-TELEGRAM-4 (nature
posée par le code), INV-APPAIRAGE-2.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from . import coffre, fiches, langues, manager, telegram_appairage, telegram_connexion
from . import telegram_assistant as assistant
from .vault import Conflit, Invalide, NonTrouve

log = logging.getLogger(__name__)
ROUTES_MAX = 1000  # routes « message du bot -> tâche » gardées ; les plus anciennes sortent
PAUSE_S = 10  # attente après une erreur réseau avant de relire


class ErreurTelegram(Exception):
    def __init__(self, texte: str, transitoire: bool = False):
        super().__init__(texte)
        self.transitoire = transitoire  # coupure réseau, 5xx, 429 : l'envoi sera relu, pas perdu


def masquer(texte: str, *secrets: str) -> str:
    # INV-TELEGRAM-2 : un message d'erreur peut citer l'URL, qui porte le jeton.
    for s in secrets:
        if s:
            texte = texte.replace(s, "***")
    return texte


class Client:
    """API de bot Telegram : méthodes JSON et téléchargement de fichiers ; erreurs masquées."""

    def __init__(self, api: str, jeton: str):
        self.api, self.jeton = api.rstrip("/"), jeton

    def _ouvrir(self, req: urllib.request.Request, delai: float) -> bytes:
        try:
            with urllib.request.urlopen(req, timeout=delai) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("description", "")
            except ValueError:
                detail = ""
            raise ErreurTelegram(masquer(f"{e.code} {detail or e.reason}", self.jeton),
                                 e.code >= 500 or e.code == 429) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ErreurTelegram(masquer(langues.t("serveur.telegram.reseau", detail=e), self.jeton), True) from None

    def appel(self, methode: str, params: dict | None = None, delai: float = 30):
        req = urllib.request.Request(f"{self.api}/bot{self.jeton}/{methode}",
                                     data=json.dumps(params or {}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            r = json.loads(self._ouvrir(req, delai).decode("utf-8"))
        except ValueError:
            raise ErreurTelegram(langues.t("serveur.telegram.reponse_illisible", methode=methode)) from None
        if not r.get("ok"):
            raise ErreurTelegram(masquer(f"{methode} : {r.get('description', 'refus')}", self.jeton))
        return r.get("result")

    def telecharger(self, file_id: str) -> bytes:
        chemin = self.appel("getFile", {"file_id": file_id}).get("file_path", "")
        req = urllib.request.Request(f"{self.api}/file/bot{self.jeton}/{chemin}")
        return self._ouvrir(req, 120)


def ecrire_octets(chemin: Path, octets: bytes) -> None:
    # INV-VAULT-2 : temporaire dans le même dossier puis os.replace.
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".orch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(octets)
        os.replace(tmp, chemin)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def nom_sur(nom: str) -> str:
    """Nom de fichier venu de Telegram, rendu sûr (aucun séparateur, aucun `..`)."""
    return re.sub(r"[^\w.\-]+", "-", nom).strip(".-")[:80] or "piece"


async def dans_un_fil(fonction, *args):
    """Appel bloquant dans un fil démon : une lecture longue ne retient jamais l'arrêt du serveur."""
    boucle = asyncio.get_running_loop()
    futur = boucle.create_future()

    def courir():
        try:
            r, e = fonction(*args), None
        except BaseException as x:  # noqa: BLE001 — rendu à l'appelant tel quel
            r, e = None, x
        try:
            boucle.call_soon_threadsafe(lambda: futur.done() or (
                futur.set_exception(e) if e else futur.set_result(r)))
        except RuntimeError:
            pass  # boucle fermée (arrêt du serveur) : plus personne n'attend

    threading.Thread(target=courir, daemon=True).start()
    return await futur


class Connecteur:
    def __init__(self, moteur):
        self.moteur = moteur
        self.config = moteur.config
        self.cfg = moteur.config.telegram
        self.chemin = moteur.config.donnees / "etat" / "telegram.json"
        self.etat = self._lire()
        self.tache: asyncio.Task | None = None
        self.vues: dict[str, dict] = {}  # INV-TELEGRAM-5 : discussions lues par la boucle (« Me reconnaître »)
        self.appareils, self._appairages = None, []  # registre posé par `api.creer` ; INV-APPAIRAGE-2
        self.erreur = ""
        self.fil = manager.Fil(self)  # INV-MANAGER-1 : fil commun avec le volet de l'interface

    # --- état et secrets ---------------------------------------------------------------------
    def _lire(self) -> dict:
        try:
            etat = json.loads(self.chemin.read_text("utf-8"))
        except (OSError, ValueError):
            etat = {}
        etat = etat if isinstance(etat, dict) else {}
        for cle in ("envois", "routes", "boutons", "vises"):
            etat[cle] = etat.get(cle) if isinstance(etat.get(cle), dict) else {}
        return etat

    def _sauver(self) -> None:
        routes = self.etat["routes"]
        for cle in list(routes)[:-ROUTES_MAX]:
            del routes[cle]
        for d in (self.etat["envois"], self.etat["boutons"], self.etat["vises"]):
            for cle in list(d)[:-ROUTES_MAX]:
                del d[cle]
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.etat, ensure_ascii=False))

    def fichier_jeton(self) -> Path:
        return telegram_connexion.fichier_jeton(self.config)

    def jeton(self) -> tuple[str, str]:
        return coffre.lire(self.cfg.jeton_variable, self.fichier_jeton())

    def client(self) -> Client:
        jeton, _ = self.jeton()
        if not jeton:
            raise Invalide(langues.t("serveur.telegram.jeton_absent"))
        return Client(self.cfg.api, jeton)

    def reception(self) -> Path:
        racine = self.config.vault.racine.resolve()
        dossier = (racine / self.cfg.reception).resolve()
        if dossier != racine and racine not in dossier.parents:  # INV-NOTE-1
            raise Invalide(langues.t("serveur.telegram.reception_hors_vault"))
        return dossier

    # --- cycle ---------------------------------------------------------------------------------
    def demarrer(self) -> None:
        # INV-TELEGRAM-1 : un seul lecteur par bot ; rien ne lit sans réglage explicite.
        if self.tache or not self.cfg.actif or not self.jeton()[0]:
            return
        self.tache = asyncio.get_running_loop().create_task(self.boucle())

    def arreter(self) -> None:
        if self.tache:
            self.tache.cancel()
        self.tache = None

    async def boucle(self) -> None:
        while True:
            try:
                await self.relever()
                self.erreur = ""
            except asyncio.CancelledError:
                raise
            except Exception as e:  # le connecteur survit à une coupure ; jamais le jeton au journal
                self.erreur = masquer(str(e), self.jeton()[0])
                log.warning("Telegram : %s", self.erreur)
                await asyncio.sleep(PAUSE_S)

    async def relever(self) -> int:
        """Une lecture longue ; chaque mise à jour traitée fait avancer le décalage persisté."""
        client = self.client()
        params = {"timeout": self.cfg.attente_s, "allowed_updates": ["message", "callback_query"]}
        if self.etat.get("offset"):
            params["offset"] = self.etat["offset"]
        maj = await dans_un_fil(client.appel, "getUpdates", params, self.cfg.attente_s + 15)
        for u in maj or []:
            try:
                if "callback_query" in u:
                    await self.bouton(client, u["callback_query"])
                else:
                    await self.traiter(client, u)
            except ErreurTelegram as e:
                if e.transitoire:
                    raise  # INV-TELEGRAM-1 : décalage non avancé, l'envoi sera relu après la coupure
                log.warning("Telegram : envoi %s non traité : %s", u.get("update_id"), e)
            except Exception as e:  # un envoi en échec durable ne bloque pas les suivants
                log.warning("Telegram : envoi %s non traité : %s", u.get("update_id"),
                            masquer(f"{type(e).__name__}: {e}", client.jeton))
            self.etat["offset"] = int(u["update_id"]) + 1
            self._sauver()
        return len(maj or [])

    # --- réception -----------------------------------------------------------------------------
    async def traiter(self, client: Client, u: dict) -> None:
        m = u.get("message")
        if not isinstance(m, dict):
            return
        chat = str(m.get("chat", {}).get("id", ""))
        self.vues[chat] = m.get("chat") or {}  # identifiant et nom seulement, jamais le contenu
        if chat not in {str(d) for d in self.cfg.discussions}:
            # INV-TELEGRAM-1 : ni contenu ni nom de l'expéditeur au journal.
            log.warning("Telegram : envoi ignoré, discussion %s hors liste blanche", chat)
            return
        texte = str(m.get("text") or m.get("caption") or "").strip()
        if texte == assistant.NOUVEAU and not assistant.transfere(m):
            self.fil.ajouter("vous", texte, "telegram")
            r = self.fil.ajouter("manager", assistant.nouveau_fil(self), "telegram")["texte"]
            await self.envoyer(chat, r, self.tache_tri(), m.get("message_id"))
            return
        if texte.split(None, 1)[:1] == [telegram_appairage.APPAIRER] and not assistant.transfere(m):
            await telegram_appairage.appairer(self, chat, texte, m.get("message_id"))  # INV-APPAIRAGE-2
            return
        pieces, transcrits = await dans_un_fil(self._ranger_pieces, client, m)
        etiquettes = assistant.etiqueter(m, texte, pieces, transcrits)  # INV-TELEGRAM-4
        reponse = m.get("reply_to_message") or {}
        cible, etiquettes = assistant.citation(self, chat, reponse, etiquettes)
        if cible and cible != self.etat.get("tache_tri"):
            self.moteur.soumettre(cible, "\n".join(["[Réponse Telegram]", *etiquettes]))
            return
        if texte and not pieces and not assistant.transfere(m):  # instruction libre : à l'assistant, sans note
            ident = self.tache_tri()
            self.fil.ajouter("vous", texte, "telegram")
            self.moteur.soumettre(ident, "\n".join([*assistant.entete(self, ident, texte),
                                                    "[Instruction Telegram]", *etiquettes]))
            self._sauver()
            return
        n = int(self.etat.get("compteur", 0)) + 1
        self.etat["compteur"] = n
        note = self._noter(n, m, texte, pieces, transcrits)
        self.etat["envois"][str(n)] = {"chat": chat, "message": m.get("message_id"), "note": note}
        ident = self.tache_tri()
        self.fil.ajouter("vous", texte or langues.t("serveur.telegram.envoi_resume", n=n, pieces=len(pieces)), "telegram")
        self.moteur.soumettre(ident, self._consigne(n, note, etiquettes, assistant.entete(self, ident)))
        self._sauver()

    def _ranger_pieces(self, client: Client, m: dict) -> tuple[list[tuple[str, str]], list[str]]:
        """(pièces [(chemin relatif, nature)], lignes de transcription) ; s'exécute hors de la boucle."""
        trouvees = []
        if m.get("photo"):
            trouvees.append(("photo", m["photo"][-1]["file_id"], "photo.jpg"))
        for nature, defaut in (("document", "document"), ("voice", "note-vocale.ogg"), ("audio", "audio")):
            if isinstance(m.get(nature), dict):
                trouvees.append((nature, m[nature]["file_id"], m[nature].get("file_name") or defaut))
        if not trouvees:
            return [], []
        dossier = self.reception()
        dossier.mkdir(parents=True, exist_ok=True)
        prefixe = self._prefixe(m)
        racine = self.config.vault.racine.resolve()
        pieces, transcrits = [], []
        for nature, file_id, nom in trouvees:
            octets = client.telecharger(file_id)
            chemin = dossier / f"{prefixe}-{nom_sur(nom)}"
            ecrire_octets(chemin, octets)
            pieces.append((chemin.relative_to(racine).as_posix(), nature))
            if nature == "voice":
                transcrits.append(self._transcrire(octets, chemin.name))
        return pieces, transcrits

    def _transcrire(self, octets: bytes, nom: str) -> str:
        cle, _ = coffre.lire(self.cfg.transcription_variable, Path(self.cfg.transcription_fichier)
                             if self.cfg.transcription_fichier else
                             self.config.donnees / "etat" / "transcription.cle")
        if not (self.cfg.transcription_url and cle):
            return "Note vocale sans transcription : aucun fournisseur de transcription réglé."
        try:
            return "Transcription : " + telegram_connexion.transcrire(self.cfg.transcription_url, self.cfg.transcription_modele,
                                                   cle, octets, nom)
        except ErreurTelegram as e:
            return f"Note vocale sans transcription : {e}"

    def _prefixe(self, m: dict) -> str:
        quand = dt.datetime.fromtimestamp(int(m.get("date") or 0) or dt.datetime.now().timestamp())
        return f"{quand:%Y-%m-%d-%H%M%S}-{m.get('message_id', 0)}"

    def _noter(self, n: int, m: dict, texte: str, pieces: list, transcrits: list[str]) -> str:
        dossier = self.reception()
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"{self._prefixe(m)}-telegram.md"
        corps = [f"---\ntype: capture\nsource: telegram\nenvoi: {n}\ncreated: {dt.date.today()}\n---\n",
                 f"# Envoi Telegram n°{n}\n", texte or "(sans texte)"]
        if pieces:
            corps += ["\n## Pièces", *(f"- {nature} : ![[{p}]]" for p, nature in pieces)]
        corps += [f"\n{t}" for t in transcrits]
        fiches.ecrire_atomique(chemin, "\n".join(corps) + "\n")
        return chemin.relative_to(self.config.vault.racine.resolve()).as_posix()

    def _consigne(self, n: int, note: str, etiquettes: list[str], entete: list[str]) -> str:
        lignes = [*entete, f"[Envoi Telegram n°{n}] Note de capture : {note}",
                  *(etiquettes or ["(sans texte)"])]
        return "\n".join(lignes)

    def tache_tri(self) -> str:
        """Tâche permanente de tri, créée au premier envoi si absente (ou disparue).

        Elle garde sa conversation (session) sur le moteur du rôle `tri` : chaque envoi et chaque
        réponse y arrivent dans le même fil, au lieu d'un tour éphémère (INV-TELEGRAM-3).
        """
        ident = str(self.etat.get("tache_tri") or "")
        try:
            self.moteur.vault.tache(ident)
            return ident
        except NonTrouve:
            pass
        choix = self.moteur.roles.choisir("tri")
        ident = self.moteur.creer(self.cfg.titre_tri, self.cfg.consigne.strip(),
                                  conteneur=self.cfg.conteneur or None,
                                  harnais=choix.harnais if choix else None,
                                  modele=choix.modele if choix else None)
        chemin = self.moteur.vault.tache(ident).chemin
        texte = fiches.lire(chemin)
        # Fichier que l'on vient de créer : `nature` n'est pas une clé gérée, on l'ajoute à la création.
        fiches.ecrire_atomique(chemin, texte.replace("type: tache\n", "type: tache\nnature: permanente\n", 1))
        self.moteur.vault._index = None  # relire `nature` (INV-EXEC-7 : la tâche reste ouverte)
        self.etat["tache_tri"] = ident
        self._sauver()
        return ident

    # --- retours sur Telegram -------------------------------------------------------------------
    async def envoyer(self, chat: str, texte: str, tache: str, reponse_a: int | None = None,
                      boutons: bool = False, clavier: dict | None = None) -> str:
        params = {"chat_id": chat, "text": texte[:4000]}
        if reponse_a:
            params["reply_to_message_id"] = reponse_a
        if boutons:  # compte rendu : Valider clôt la tâche, Renvoyer attend la remarque suivante
            params["reply_markup"] = {"inline_keyboard": [[
                {"text": langues.t("serveur.telegram.valider"), "callback_data": "valider"},
                {"text": langues.t("serveur.telegram.renvoyer"), "callback_data": "renvoyer"}]]}
        if clavier:
            params["reply_markup"] = clavier
        r = await dans_un_fil(self.client().appel, "sendMessage", params)
        cle = f"{chat}:{r['message_id']}"
        self.etat["routes"][cle] = tache  # une réponse à ce message va à `tache`
        self._sauver()
        return cle

    def _place(self, tache: str) -> tuple[str, str]:
        t = self.moteur.vault.tache(tache)
        return t.titre, " > ".join(self.moteur.vault.fil_ariane(tache)) or langues.t("serveur.telegram.arrivee")

    async def issue(self, n: int, tache: str, cree: bool) -> dict:
        """Envoi rangé par l'agent de tri : une ligne sur Telegram, la note pointe vers la tâche."""
        e = self.etat["envois"].get(str(n))
        if not e:
            raise NonTrouve(langues.t("serveur.telegram.envoi_inconnu", n=n))
        titre, place = self._place(tache)
        texte = assistant.ligne_issue(cree, titre, place)
        self.etat["routes"][f"{e['chat']}:{e['message']}"] = tache
        e["tache"] = self.etat["derniere"] = tache
        note = self.config.vault.racine / e["note"]
        if note.is_file():
            fiches.ecrire_atomique(note, fiches.lire(note).rstrip("\n") + f"\n\nRangé : [[{tache}]]\n")
        self.fil.ajouter("manager", texte, "telegram")
        await self.envoyer(e["chat"], texte, tache, e["message"])
        return {"envoi": n, "tache": tache, "texte": texte}

    async def question(self, tache: str, texte: str, boutons: bool = False, choix: list[str] = (),
                       geste: str = "", vise: str = "") -> dict:
        """Question ou compte rendu d'un agent, envoyé à la première discussion autorisée.

        Une question laisse la main au message libre suivant (`attente`) ; un compte rendu (`boutons`)
        n'attend que Valider ou Renvoyer. La réponse revient dans l'un et l'autre cas à `tache`.
        `vise` ajoute la ligne de la tâche touchée (titre, place, lien) ; `choix` (2-3 tâches) propose
        des boutons au lieu de deviner ; `geste` (sur `vise`) attend Confirmer / Annuler.
        """
        gere = tache == self.etat.get("tache_tri")  # INV-MANAGER-1 : l'assistant parle aussi dans le volet
        actif = bool(self.cfg.actif and self.cfg.discussions)
        if not (actif or gere):
            raise Invalide(langues.t("serveur.telegram.desactive"))
        if not texte.strip():
            raise Invalide(langues.t("serveur.telegram.question_vide"))
        if geste and not vise:
            raise Invalide(langues.t("serveur.telegram.geste_sans_tache"))
        clavier, attente = None, {}
        if choix:
            clavier, attente = assistant.clavier_choix(self.moteur, list(choix)), {"choix": list(choix)}
        elif geste:
            cle, valeur = assistant.verifier_geste(geste, self.moteur.vault.statuts)
            clavier, attente = assistant.clavier_geste(), {"tache": vise, "cle": cle, "valeur": valeur}
        titre, _ = self._place(tache)
        # l'assistant parle en son nom : son titre en tête n'apprend rien (retour d'essai, 18/11)
        corps = texte.strip() if tache == self.etat.get("tache_tri") else f"[{titre}] {texte.strip()}"
        if vise:
            corps += "\n" + assistant.ligne_tache(self.moteur, vise)
            self.etat["derniere"] = vise  # reconnaissance par le contexte du fil
        cle = f"volet:{self.fil.prochain()}"
        try:
            if actif:
                cle = await self.envoyer(str(self.cfg.discussions[0]), corps, tache, boutons=boutons,
                                         clavier=clavier)
        except ErreurTelegram:
            if not gere:
                raise  # le volet garde la réponse de l'assistant même si Telegram est injoignable
        if gere:
            touches = [{"texte": b["text"], "data": b["callback_data"]}
                       for ligne in (clavier or {}).get("inline_keyboard", []) for b in ligne]
            self.fil.ajouter("manager", corps, "volet", **({"cle": cle, "boutons": touches} if touches else {}))
        if vise:
            self.etat["vises"][cle] = vise  # répondre à ce message vise cette tâche
        if attente:
            self.etat["boutons"][cle] = attente
        elif not boutons and tache != self.etat.get("tache_tri"):
            self.etat["attente"] = tache  # l'assistant reçoit déjà tout message libre
        self._sauver()
        return {"tache": tache, "envoye": True}

    async def bouton(self, client: Client, cb: dict) -> None:
        """Bouton d'un compte rendu (INV-TELEGRAM-3) : seul un humain, sur discussion autorisée, clôt.

        Valider pose `fait` par la voie humaine (`poser_statut`, comme `POST /statut`). Renvoyer ouvre
        l'attente : la remarque suivante de l'utilisateur revient à la tâche.
        """
        m = cb.get("message") if isinstance(cb.get("message"), dict) else {}
        chat = str(m.get("chat", {}).get("id", ""))
        tache = self.etat["routes"].get(f"{chat}:{m.get('message_id')}")
        texte = langues.t("serveur.telegram.compte_rendu_inactif")
        if tache and chat in {str(d) for d in self.cfg.discussions}:
            if cb.get("data") == "valider":
                try:
                    self.moteur.vault.poser_statut(tache, "fait", humain=True)
                    texte = langues.t("serveur.telegram.tache_validee")
                except (Invalide, Conflit, NonTrouve) as e:
                    texte = str(e)
            elif cb.get("data") == "renvoyer":
                self.etat["attente"] = tache
                self._sauver()
                texte = langues.t("serveur.telegram.ecris_remarque")
            else:  # choix ou geste : une seule fois, volet ou Telegram (INV-TELEGRAM-3)
                try:
                    toast, message = assistant.trancher(self, f"{chat}:{m.get('message_id')}",
                                                        str(cb.get("data") or ""))
                    if message:
                        texte = toast
                        self.moteur.soumettre(tache, message)
                except (Invalide, Conflit, NonTrouve) as e:
                    texte = str(e)
        await dans_un_fil(client.appel, "answerCallbackQuery",
                          {"callback_query_id": cb.get("id"), "text": texte})

    async def tester(self) -> dict:
        """Nom du bot, état du connecteur, et bienvenue à la première discussion autorisée."""
        try:
            client = self.client()
            moi = await dans_un_fil(client.appel, "getMe", {}, 15)
            r = {"ok": True, "bot": "@" + str(moi.get("username", "?")), "en_marche": bool(self.tache), "bienvenue": ""}
            if self.cfg.discussions:
                r["bienvenue"] = str(self.cfg.discussions[0])
                await dans_un_fil(client.appel, "sendMessage",
                                  {"chat_id": r["bienvenue"], "text": telegram_connexion.bienvenue()}, 15)
            return r
        except (ErreurTelegram, Invalide) as e:
            return {"ok": False, "motif": str(e)}

    def public(self) -> dict:
        return {"actif": self.cfg.actif, "discussions": [str(d) for d in self.cfg.discussions],
                "reception": self.cfg.reception, "conteneur": self.cfg.conteneur,
                "jeton": self.jeton()[1], "windows": coffre.WINDOWS,
                "transcription": bool(self.cfg.transcription_url), "en_marche": bool(self.tache),
                "tache_tri": self.etat.get("tache_tri"), "envois": int(self.etat.get("compteur", 0)),
                "erreur": self.erreur}
