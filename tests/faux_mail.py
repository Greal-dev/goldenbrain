"""Faux serveurs IMAP et SMTP de la boucle locale, façon Gmail, pour les tests de la messagerie (aucun réseau).

Rôle : juste assez d'IMAP4rev1 pour `imaplib` (LOGIN, LIST à attributs SPECIAL-USE, SELECT, FETCH et UID FETCH
partiels, UID SEARCH avec UNSEEN et X-GM-RAW en littéral, UID STORE, UID MOVE) et de SMTP pour `smtplib` (EHLO,
AUTH PLAIN, MAIL, RCPT, DATA). `envoyes` garde les messages reçus par SMTP ; `boites` les dossiers.
Frontières : sert pytest (`tests/test_mail.py`) et les scénarios d'interface (`tests/ui/scenario_mail.py`).
"""

from __future__ import annotations

import re
import socketserver
import threading
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
import datetime as dt

ADRESSE = "moi@example.org"
MDP = "abcdefghijklmnop"
DOSSIERS = {"INBOX": "", "[Gmail]": "\\Noselect", "[Gmail]/Tous les messages": "\\All",
            "[Gmail]/Messages envoy&AOk-s": "\\Sent", "[Gmail]/Suivis": "\\Flagged", "Factures": "",
            "Re&AOc-us": ""}


def message(objet="Bonjour", de="Ada <ada@example.org>", texte="Corps du message.", html=None, piece=None,
            a=ADRESSE, cc="", jours=0) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = de, a, objet
    if cc:
        m["Cc"] = cc
    m["Date"] = format_datetime(dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.timezone.utc) + dt.timedelta(days=jours))
    m["Message-ID"] = make_msgid(domain="example.org")
    m.set_content(texte)
    if html:
        m.add_alternative(html, subtype="html")
    if piece:
        nom, octets = piece
        m.add_attachment(octets, maintype="application", subtype="pdf", filename=nom)
    return bytes(m)


def _ensemble(texte: str, maxi: int) -> list[int]:
    sortie = []
    for bout in texte.split(","):
        a, _, b = bout.partition(":")
        lo = maxi if a == "*" else int(a)
        hi = lo if not b else (maxi if b == "*" else int(b))
        sortie += range(min(lo, hi), max(lo, hi) + 1)
    return sortie


class _Imap(socketserver.StreamRequestHandler):
    def ecrire(self, texte):
        self.wfile.write(texte if isinstance(texte, bytes) else texte.encode())

    def ligne(self):
        """Ligne de commande, littéraux {n} compris (réponse de continuation « + »)."""
        tout, litteraux = b"", []
        while True:
            brut = self.rfile.readline()
            if not brut:
                return None, []
            tout += brut.rstrip(b"\r\n")
            m = re.search(rb"\{(\d+)\}$", tout)
            if not m:
                return tout.decode("utf-8", "replace"), litteraux
            self.ecrire("+ go\r\n")
            self.wfile.flush()
            litteraux.append(self.rfile.read(int(m.group(1))))
            tout = tout[:m.start()] + b"\x00LIT"

    def handle(self):
        f = self.server.faux
        dossier = None
        self.ecrire("* OK [CAPABILITY IMAP4rev1 MOVE X-GM-EXT-1 AUTH=PLAIN] faux Gmail\r\n")
        while True:
            texte, lits = self.ligne()
            if texte is None:
                return
            tag, _, reste = texte.partition(" ")
            cmd, _, args = reste.partition(" ")
            cmd = cmd.upper()
            uid = cmd == "UID"
            if uid:
                cmd, _, args = args.partition(" ")
                cmd = cmd.upper()
            f.commandes.append(cmd)
            if cmd == "CAPABILITY":
                self.ecrire(f"* CAPABILITY IMAP4rev1 MOVE X-GM-EXT-1 AUTH=PLAIN\r\n{tag} OK fait\r\n")
            elif cmd == "LOGIN":
                u, p = [x.strip('"') for x in args.split(" ", 1)]
                self.ecrire(f"{tag} OK fait\r\n" if (u, p) == (ADRESSE, f.mdp) else f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials\r\n")
            elif cmd == "NOOP":
                self.ecrire(f"{tag} OK fait\r\n")
            elif cmd == "LOGOUT":
                self.ecrire(f"* BYE\r\n{tag} OK fait\r\n")
                return
            elif cmd == "LIST":
                for nom, attr in DOSSIERS.items():
                    self.ecrire(f'* LIST (\\HasNoChildren{" " + attr if attr else ""}) "/" "{nom}"\r\n')
                self.ecrire(f"{tag} OK fait\r\n")
            elif cmd in ("SELECT", "EXAMINE"):
                dossier = args.strip('"')
                if dossier not in f.boites:
                    self.ecrire(f"{tag} NO inconnu\r\n")
                    dossier = None
                    continue
                self.ecrire(f"* {len(f.boites[dossier])} EXISTS\r\n{tag} OK [READ-WRITE]\r\n")
            elif dossier is None:
                self.ecrire(f"{tag} BAD aucun dossier\r\n")
            elif cmd == "SEARCH":
                boite = f.boites[dossier]
                q = lits[0].decode("utf-8").lower() if lits else ""
                trouves = [m for m in boite if (q in m["brut"].decode("utf-8", "replace").lower())
                           and ("UNSEEN" not in args or "\\Seen" not in m["flags"])]
                self.ecrire(f"* SEARCH {' '.join(str(m['uid']) for m in trouves)}\r\n{tag} OK fait\r\n")
            elif cmd == "FETCH":
                ens, _, items = args.partition(" ")
                boite = f.boites[dossier]
                for seq, m in enumerate(boite, 1):
                    if (m["uid"] if uid else seq) in _ensemble(ens, boite[-1]["uid"] if uid and boite else len(boite)):
                        self.ecrire(_fetch(seq, m, items))
                self.ecrire(f"{tag} OK fait\r\n")
            elif cmd == "STORE":
                ens, op, valeur = args.split(" ", 2)
                for seq, m in enumerate(f.boites[dossier], 1):
                    if m["uid"] in _ensemble(ens, 10 ** 9):
                        drap = set(valeur.strip("()").split())
                        m["flags"] = m["flags"] | drap if op.startswith("+") else m["flags"] - drap
                        self.ecrire(f"* {seq} FETCH (UID {m['uid']} FLAGS ({' '.join(sorted(m['flags']))}))\r\n")
                self.ecrire(f"{tag} OK fait\r\n")
            elif cmd == "MOVE":
                ens, _, cible = args.partition(" ")
                cible = cible.strip('"')
                for m in [m for m in f.boites[dossier] if m["uid"] in _ensemble(ens, 10 ** 9)]:
                    f.boites[dossier].remove(m)
                    f.ajouter(cible, m["brut"], m["flags"])
                self.ecrire(f"{tag} OK fait\r\n")
            else:
                self.ecrire(f"{tag} BAD inconnue\r\n")


def _fetch(seq: int, m: dict, items: str) -> bytes:
    tete, _, corps = m["brut"].partition(b"\r\n\r\n") if b"\r\n\r\n" in m["brut"] else m["brut"].partition(b"\n\n")
    parts = [f"UID {m['uid']}", f"FLAGS ({' '.join(sorted(m['flags']))})"]
    sortie = b""
    if "HEADER.FIELDS" in items:
        noms = set(re.search(r"HEADER\.FIELDS \(([^)]*)\)", items).group(1).lower().split())
        garde, lignes = False, []
        for l in re.split(rb"\r?\n", tete):
            if l[:1] in (b" ", b"\t"):
                if garde:
                    lignes.append(l)
                continue
            garde = l.split(b":")[0].strip().decode().lower() in noms
            if garde:
                lignes.append(l)
        bloc = b"\r\n".join(lignes) + b"\r\n\r\n"
        sortie += f" BODY[HEADER.FIELDS ({' '.join(sorted(noms)).upper()})] {{{len(bloc)}}}\r\n".encode() + bloc
    if "BODY.PEEK[TEXT]" in items:
        bloc = corps[:2048]
        sortie += f" BODY[TEXT]<0> {{{len(bloc)}}}\r\n".encode() + bloc
    if "BODY.PEEK[]" in items:
        sortie += f" BODY[] {{{len(m['brut'])}}}\r\n".encode() + m["brut"]
    return f"* {seq} FETCH (" .encode() + " ".join(parts).encode() + sortie + b")\r\n"


class _Smtp(socketserver.StreamRequestHandler):
    def handle(self):
        f = self.server.faux
        self.wfile.write(b"220 faux smtp\r\n")
        donnees, dans = [], False
        while (brut := self.rfile.readline()):
            l = brut.decode("utf-8", "replace").rstrip("\r\n")
            if dans:
                if l == ".":
                    f.envoyes.append(b"\r\n".join(donnees))
                    donnees, dans = [], False
                    self.wfile.write(b"250 OK\r\n")
                else:
                    donnees.append(brut.rstrip(b"\r\n")[1:] if brut.startswith(b"..") else brut.rstrip(b"\r\n"))
                continue
            c = l.split(" ")[0].upper()
            if c in ("EHLO", "HELO"):
                self.wfile.write(b"250-faux\r\n250 AUTH PLAIN\r\n")
            elif c == "AUTH":
                import base64
                ok = base64.b64decode(l.split(" ")[2]).split(b"\x00")[1:] == [ADRESSE.encode(), f.mdp.encode()]
                self.wfile.write(b"235 OK\r\n" if ok else b"535 refus\r\n")
            elif c == "DATA":
                dans = True
                self.wfile.write(b"354 go\r\n")
            elif c == "QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 OK\r\n")


class _Serveur(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class FauxMail:
    def __init__(self, mdp: str = MDP):
        self.mdp, self.envoyes, self.commandes, self._uid = mdp, [], [], 100
        self.boites: dict[str, list[dict]] = {n: [] for n, a in DOSSIERS.items() if a != "\\Noselect"}
        self._serveurs = []
        for classe in (_Imap, _Smtp):
            s = _Serveur(("127.0.0.1", 0), classe)
            s.faux = self
            threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
            self._serveurs.append(s)
        self.imap = f"127.0.0.1:{self._serveurs[0].server_address[1]}"
        self.smtp = f"127.0.0.1:{self._serveurs[1].server_address[1]}"

    def ajouter(self, dossier: str, brut: bytes, flags=frozenset()) -> int:
        self._uid += 1
        self.boites[dossier].append({"uid": self._uid, "flags": set(flags), "brut": brut.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")})
        return self._uid

    def arreter(self):
        for s in self._serveurs:
            s.shutdown()
            s.server_close()
