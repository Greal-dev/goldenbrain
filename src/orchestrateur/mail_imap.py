"""Boîte aux lettres IMAP (Gmail) et envoi SMTP : la seule frontière réseau de la messagerie.

Rôle : `Boite` tient UNE connexion IMAP par compte, réutilisée tant qu'elle répond (verrou : un seul échange à la fois),
résout les vues (Boîte de réception, Non lus, Suivis, Envoyés, Tous les messages, libellés), liste par page, cherche
avec la syntaxe Gmail (X-GM-RAW), lit un message brut, pose lu / non lu, archive ; `envoyer` passe par SMTP.
Frontières : appels bloquants, toujours lancés hors de la boucle d'événements (`asyncio.to_thread`, `api_mail`) ;
délais bornés (`delai_s`) ; aucun calcul sur le contenu (`mail_message`) ; un nom de dossier ne vient jamais du
client : seulement de la liste rendue par le serveur IMAP.
Invariants portés : INV-MAIL-1 (mot de passe lu du coffre à la connexion, jamais rendu ni journalisé ; masqué dans
tout message d'erreur), INV-MAIL-6 (IMAP hors boucle, délais bornés).
"""

from __future__ import annotations

import base64
import imaplib
import re
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import coffre, langues, mail_message
from .vault import ErreurOrch, Invalide

ENTETES = "FROM TO SUBJECT DATE CONTENT-TYPE CONTENT-TRANSFER-ENCODING"
RESUME = f"(UID FLAGS BODY.PEEK[HEADER.FIELDS ({ENTETES})] BODY.PEEK[TEXT]<0.2048>)"
INACTIF_S = 240  # au-delà, un NOOP vérifie la connexion avant de s'en servir
TAILLE_MAX = 40 * 1024 * 1024
_LISTE = re.compile(rb'\((?P<attrs>[^)]*)\) (?:"[^"]*"|NIL) (?P<nom>"(?:[^"\\]|\\.)*"|\S+)$')
VUES = {"inbox": ("INBOX", None), "non-lus": ("INBOX", "UNSEEN"), "suivis": ("\\Flagged", None),
        "envoyes": ("\\Sent", None), "tous": ("\\All", None)}
SPECIAUX = {"\\All", "\\Sent", "\\Flagged", "\\Drafts", "\\Junk", "\\Trash", "\\Important", "\\Noselect", "\\NonExistent"}


class ErreurMail(ErreurOrch):
    code = 502


@dataclass
class Compte:
    """Un compte de messagerie ; aujourd'hui la seule section `[messagerie]`."""
    adresse: str
    conf: object  # ConfigMessagerie
    fichier_mdp: Path


def compte(config) -> Compte:
    c = config.messagerie
    return Compte(c.adresse, c, Path(c.mdp_fichier) if c.mdp_fichier else config.donnees / "etat" / "messagerie.mdp")


def mot_de_passe(cpt: Compte) -> tuple[str, str]:
    mdp, source = coffre.lire(cpt.conf.mdp_variable, cpt.fichier_mdp)
    return mdp.replace(" ", ""), source  # Google montre le mot de passe d'application par groupes de quatre


def _utf7(nom: str) -> str:
    """Nom IMAP (UTF-7 modifié, RFC 3501) → texte affichable."""
    def un(m):
        b = m.group(1)
        return "&" if not b else base64.b64decode(b.replace(",", "/") + "=" * (-len(b) % 4)).decode("utf-16-be", "replace")
    return re.sub(r"&([^-]*)-", un, nom)


def _cite(nom: str) -> str:
    return '"' + nom.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ok(reponse, cpt=None):
    typ, data = reponse
    if typ != "OK":
        raise ErreurMail(langues.t("serveur.mail.refus", detail=_masquer(str(data), cpt)))
    return data


def _masquer(texte: str, cpt: Compte | None) -> str:
    mdp = mot_de_passe(cpt)[0] if cpt else ""
    return texte.replace(mdp, "•••") if mdp else texte


def _messages(data) -> list[tuple[int, list[str], bytes]]:
    """Réponse FETCH → [(uid, drapeaux, en-têtes + corps partiel)] ; l'ordre des éléments varie selon le serveur."""
    sortie, cur = [], None
    for el in data:
        prefixe, litteral = (el[0], el[1]) if isinstance(el, tuple) else (el, None)
        if not isinstance(prefixe, bytes):
            continue
        if re.match(rb"\d+ \(", prefixe):
            cur = {"uid": 0, "flags": [], "parts": {}}
            sortie.append(cur)
        if cur is None:
            continue
        if m := re.search(rb"UID (\d+)", prefixe):
            cur["uid"] = int(m.group(1))
        if m := re.search(rb"FLAGS \(([^)]*)\)", prefixe):
            cur["flags"] = m.group(1).decode("ascii", "replace").split()
        if litteral is not None and (m := re.search(rb"BODY\[([^\]]*)\](?:<\d+>)? \{\d+\}$", prefixe)):
            cur["parts"][m.group(1).split(b" ")[0]] = litteral
    return [(c["uid"], c["flags"], c["parts"].get(b"HEADER.FIELDS", b"") + c["parts"].get(b"TEXT", b"")
             + c["parts"].get(b"", b"")) for c in sortie if c["uid"]]


class Boite:
    def __init__(self, cpt: Compte, mdp: str = ""):
        """`mdp` : mot de passe à essayer avant qu'il n'entre au coffre (saisie au terminal) ; sinon le coffre."""
        self.cpt, self._mdp, self._imap, self._vu, self._dossiers, self._choisi = cpt, mdp, None, 0.0, None, None
        self._verrou = threading.Lock()

    # --- connexion ------------------------------------------------------------------------------------------
    def _connecter(self):
        c = self.cpt.conf
        mdp = self._mdp or mot_de_passe(self.cpt)[0]
        if not c.adresse or not mdp:
            raise Invalide(langues.t("serveur.mail.non_reglee"))
        hote, port = c.hote("imap")
        try:
            imap = (imaplib.IMAP4_SSL(hote, port, ssl_context=ssl.create_default_context(), timeout=c.delai_s)
                    if c.tls else imaplib.IMAP4(hote, port, timeout=c.delai_s))
        except (OSError, imaplib.IMAP4.error) as e:
            raise ErreurMail(langues.t("serveur.mail.injoignable", detail=e)) from None
        try:
            imap.login(c.adresse, mdp)
        except imaplib.IMAP4.error as e:
            imap.shutdown()
            raise ErreurMail(langues.t("serveur.mail.identifiants", detail=str(e).replace(mdp, "•••"))) from None
        return imap

    def fermer(self) -> None:
        with self._verrou:
            self._fermer()

    def _fermer(self):
        if self._imap is not None:
            try:
                self._imap.logout()
            except (OSError, imaplib.IMAP4.error):
                pass
        self._imap, self._dossiers, self._choisi = None, None, None

    def _avec(self, f):
        """`f(imap)` sur la connexion réutilisée ; une connexion tombée est rouverte une fois."""
        with self._verrou:
            for essai in (0, 1):
                try:
                    if self._imap is not None and time.monotonic() - self._vu > INACTIF_S:
                        self._imap.noop()
                    if self._imap is None:
                        self._imap = self._connecter()
                    r = f(self._imap)
                    self._vu = time.monotonic()
                    return r
                except (imaplib.IMAP4.abort, OSError) as e:
                    self._fermer()
                    if essai:
                        raise ErreurMail(langues.t("serveur.mail.injoignable", detail=e)) from None

    # --- dossiers et vues -------------------------------------------------------------------------------------
    def _liste(self, imap) -> list[dict]:
        if self._dossiers is None:
            sortie = []
            for ligne in _ok(imap.list(), self.cpt):
                if not isinstance(ligne, bytes) or not (m := _LISTE.search(ligne)):
                    continue
                brut = m.group("nom").decode("utf-8", "replace")
                nom = brut[1:-1].replace('\\"', '"').replace("\\\\", "\\") if brut.startswith('"') else brut
                sortie.append({"nom": nom, "attrs": set(m.group("attrs").decode("ascii", "replace").split())})
            self._dossiers = sortie
        return self._dossiers

    def _resoudre(self, imap, vue: str) -> tuple[str, str | None]:
        if vue.startswith("l:"):
            if any(d["nom"] == vue[2:] and not d["attrs"] & SPECIAUX for d in self._liste(imap)):
                return vue[2:], None
            raise Invalide(langues.t("serveur.mail.vue_inconnue"))
        if vue not in VUES:
            raise Invalide(langues.t("serveur.mail.vue_inconnue"))
        dossier, critere = VUES[vue]
        if dossier.startswith("\\"):
            dossier = next((d["nom"] for d in self._liste(imap) if dossier in d["attrs"]), "")
            if not dossier:
                raise Invalide(langues.t("serveur.mail.vue_absente"))
        return dossier, critere

    def _choisir(self, imap, dossier: str) -> int:
        data = _ok(imap.select(_cite(dossier)), self.cpt)
        self._choisi = dossier
        return int(data[0] or 0)

    def dossiers(self) -> list[dict]:
        def f(imap):
            vues = [{"id": v, "genre": v} for v in VUES if not VUES[v][0].startswith("\\")
                    or any(VUES[v][0] in d["attrs"] for d in self._liste(imap))]
            libelles = [{"id": "l:" + d["nom"], "genre": "libelle", "nom": _utf7(d["nom"])} for d in self._liste(imap)
                        if d["nom"].upper() != "INBOX" and not d["attrs"] & SPECIAUX]
            return vues + sorted(libelles, key=lambda x: x["nom"].casefold())
        return self._avec(f)

    # --- lecture ----------------------------------------------------------------------------------------------
    def lister(self, vue: str, q: str = "", page: int = 0) -> dict:
        n = self.cpt.conf.par_page
        if len(q) > 500:
            raise Invalide(langues.t("serveur.mail.recherche_longue"))

        def f(imap):
            dossier, critere = self._resoudre(imap, vue)
            existe = self._choisir(imap, dossier)
            if not q and not critere:
                haut = existe - page * n
                total, cible = existe, (f"{max(1, haut - n + 1)}:{haut}" if haut >= 1 else "")
                donnees = _ok(imap.fetch(cible, RESUME), self.cpt) if cible else []
            else:
                args = ["CHARSET", "UTF-8", critere] if critere else []
                if q:
                    imap.literal = q.encode("utf-8")  # littéral : guillemets et accents passent tels quels
                    args = ["CHARSET", "UTF-8", *([critere] if critere else []), "X-GM-RAW"]
                uids = sorted((int(x) for x in b" ".join(_ok(imap.uid("SEARCH", *args), self.cpt)).split()), reverse=True)
                total, tranche = len(uids), uids[page * n:(page + 1) * n]
                donnees = _ok(imap.uid("FETCH", ",".join(map(str, tranche)), RESUME), self.cpt) if tranche else []
            messages = sorted((mail_message.resume(u, fl, b) for u, fl, b in _messages(donnees)), key=lambda x: -x["uid"])
            return {"vue": vue, "q": q, "page": page, "total": total, "par_page": n, "messages": messages}
        return self._avec(f)

    def brut(self, vue: str, uid: int, marquer_lu: bool = False) -> tuple[bytes, list[str]]:
        def f(imap):
            self._choisir(imap, self._resoudre(imap, vue)[0])
            trouve = _messages(_ok(imap.uid("FETCH", str(int(uid)), "(UID FLAGS RFC822.SIZE BODY.PEEK[])"), self.cpt))
            if not trouve:
                raise Invalide(langues.t("serveur.mail.message_inconnu"))
            _, flags, octets = trouve[0]
            if len(octets) > TAILLE_MAX:
                raise Invalide(langues.t("serveur.mail.trop_gros"))
            if marquer_lu and "\\Seen" not in flags:
                _ok(imap.uid("STORE", str(int(uid)), "+FLAGS", "(\\Seen)"), self.cpt)
                flags = [*flags, "\\Seen"]
            return octets, flags
        return self._avec(f)

    def marquer(self, vue: str, uid: int, lu: bool) -> None:
        def f(imap):
            self._choisir(imap, self._resoudre(imap, vue)[0])
            _ok(imap.uid("STORE", str(int(uid)), "+FLAGS" if lu else "-FLAGS", "(\\Seen)"), self.cpt)
        self._avec(f)

    def archiver(self, vue: str, uid: int) -> None:
        """Gmail : sortir de la Boîte de réception = déplacer vers « Tous les messages » (le libellé Inbox tombe)."""
        def f(imap):
            dossier = self._resoudre(imap, vue)[0]
            if dossier.upper() != "INBOX":
                raise Invalide(langues.t("serveur.mail.archiver_inbox"))
            tous = self._resoudre(imap, "tous")[0]
            self._choisir(imap, dossier)
            _ok(imap.uid("MOVE", str(int(uid)), _cite(tous)), self.cpt)
        self._avec(f)

    def restaurer(self, message_id: str) -> None:
        """Annuler un archivage : « Tous les messages » → Boîte de réception, le message étant retrouvé par son Message-ID (son UID a changé)."""
        def f(imap):
            self._choisir(imap, self._resoudre(imap, "tous")[0])
            imap.literal = message_id.encode("utf-8")
            trouves = b" ".join(_ok(imap.uid("SEARCH", "CHARSET", "UTF-8", "HEADER", "Message-ID"), self.cpt)).split()
            if not trouves:
                raise Invalide(langues.t("serveur.mail.message_inconnu"))
            _ok(imap.uid("MOVE", ",".join(str(int(u)) for u in trouves), _cite("INBOX")), self.cpt)
        self._avec(f)

    def tester(self) -> dict:
        self.fermer()
        self._avec(lambda imap: _ok(imap.noop(), self.cpt))
        return {"ok": True}


def envoyer(cpt: Compte, message) -> None:
    """Envoi SMTP authentifié ; Gmail range lui-même le message dans « Envoyés »."""
    c, mdp = cpt.conf, mot_de_passe(cpt)[0]
    if not c.adresse or not mdp:
        raise Invalide(langues.t("serveur.mail.non_reglee"))
    hote, port = c.hote("smtp")
    try:
        with (smtplib.SMTP_SSL(hote, port, timeout=c.delai_s, context=ssl.create_default_context())
              if c.tls else smtplib.SMTP(hote, port, timeout=c.delai_s)) as s:
            s.login(c.adresse, mdp)
            s.send_message(message)
    except (OSError, smtplib.SMTPException) as e:
        raise ErreurMail(langues.t("serveur.mail.envoi_refuse", detail=_masquer(str(e), cpt))) from None
