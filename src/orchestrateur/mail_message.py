"""Messages électroniques : lecture d'un mail brut (en-têtes, texte, HTML isolé, pièces jointes) et composition
d'une réponse ou d'un transfert.

Rôle : calcul pur sur des octets RFC 5322 (stdlib `email`) — résumé d'une ligne de liste, détail d'un mail ouvert,
document HTML servi dans un cadre isolé, pièce jointe, message à envoyer.
Frontières : aucun réseau (`mail_imap`), aucune écriture ; le HTML d'un mail n'est jamais interprété ici, seulement
encadré (balises `base` et `referrer`, rafraîchissement retiré) : son isolement tient à la politique de sécurité
posée par la route et au cadre `sandbox` de l'interface.
Invariants portés : INV-MAIL-3 (HTML jamais exécuté dans la page), INV-MAIL-4 (en-têtes d'envoi non injectables),
INV-MAIL-5 (nom de pièce jointe assaini).
"""

from __future__ import annotations

import datetime as dt
import html
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses, make_msgid, parsedate_to_datetime

from . import langues
from .notes import RESERVES
from .vault import Invalide

EXTRAIT = 160
_BALISES = re.compile(r"(?is)<(script|style|head)\b.*?</\1>|<[^>]+>")
_RAFRAICHIR = re.compile(r"(?is)<script\b.*?(?:</script\s*>|$)|<meta[^>]+http-equiv\s*=\s*[\"']?refresh[^>]*>")
PREFIXES = {"repondre": "Re: ", "repondre_tous": "Re: ", "transferer": "Fwd: "}


def lire(brut: bytes) -> EmailMessage:
    return BytesParser(policy=policy.default).parsebytes(brut)


def _entete(m, nom: str) -> str:
    try:
        return " ".join(str(m.get(nom, "") or "").split())
    except (ValueError, TypeError, IndexError):  # en-tête mal formé : illisible plutôt que fatal
        return ""


def _date(m) -> str:
    try:
        return parsedate_to_datetime(_entete(m, "date")).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def texte_html(source: str) -> str:
    """Texte lisible d'un HTML (extrait, note du vault) : balises retirées, entités décodées."""
    return re.sub(r"[ \t]*\n\s*\n\s*", "\n\n", html.unescape(_BALISES.sub(" ", source))).strip()


def _contenu(part) -> str:
    try:
        return part.get_content()
    except (LookupError, ValueError, AssertionError, KeyError):  # encodage inconnu, base64 tronqué
        return ""


def corps(m) -> tuple[str, str]:
    """(texte, html) : premières parties text/plain et text/html qui ne sont pas des pièces jointes."""
    texte = html_ = ""
    for part in m.walk() if m.is_multipart() else [m]:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        genre = part.get_content_type()
        if genre == "text/plain" and not texte:
            texte = _contenu(part)
        elif genre == "text/html" and not html_:
            html_ = _contenu(part)
    return texte, html_


def texte_seul(m) -> str:
    texte, html_ = corps(m)
    return texte.strip() or texte_html(html_)


def resume(uid: int, flags: list[str], brut: bytes) -> dict:
    """Ligne de la liste ; `brut` = en-têtes choisis + début du corps (lecture partielle, IMAP)."""
    m = lire(brut)
    extrait = " ".join(texte_seul(m).split())[:EXTRAIT]
    return {"uid": uid, "de": _entete(m, "from"), "objet": _entete(m, "subject"), "date": _date(m),
            "extrait": extrait, "lu": "\\Seen" in flags, "suivi": "\\Flagged" in flags,
            "piece": m.get_content_type() == "multipart/mixed"}


def nom_sur(nom: str, defaut: str = "piece") -> str:
    """INV-MAIL-5 : nom de fichier venu d'un mail, sans séparateur, `..`, caractère de contrôle ni nom réservé Windows."""
    n = re.sub(r"[^\w.\- ]+", "-", nom or "").strip(" .-")[:100] or defaut
    return "_" + n if RESERVES.fullmatch(n.split(".")[0].rstrip(" ")) else n


def pieces(m) -> list:
    return [p for p in m.walk() if not p.is_multipart() and (p.get_content_disposition() == "attachment"
                                                              or (p.get_filename() and p.get_content_maintype() != "text"))]


def detail(brut: bytes, uid: int, flags: list[str]) -> dict:
    m = lire(brut)
    texte, html_ = corps(m)
    return {**resume(uid, flags, brut), "a": _entete(m, "to"), "cc": _entete(m, "cc"), "message_id": _entete(m, "message-id"),
            "texte": texte.strip() or texte_html(html_), "html": bool(html_.strip()),
            "pieces": [{"n": i, "nom": nom_sur(p.get_filename() or "", f"piece-{i + 1}"), "type": p.get_content_type(),
                        "taille": len(p.get_payload(decode=True) or b"")} for i, p in enumerate(pieces(m))]}


def piece(brut: bytes, n: int) -> tuple[str, bytes]:
    liste = pieces(lire(brut))
    if not 0 <= n < len(liste):
        raise Invalide(langues.t("serveur.mail.piece_inconnue"))
    p = liste[n]
    return nom_sur(p.get_filename() or "", f"piece-{n + 1}"), p.get_payload(decode=True) or b""


def html_isole(brut: bytes) -> str:
    """Document du cadre de lecture. INV-MAIL-3 : liens hors du cadre, sans référent ; un rafraîchissement
    (meta refresh) le ferait naviguer : retiré, comme les scripts (bloqués de toute façon par la CSP de la route, ils ne
    feraient que bruit) ; ressources distantes bloquées par la CSP."""
    texte, html_ = corps(lire(brut))
    source = _RAFRAICHIR.sub("", html_) if html_.strip() else f"<pre>{html.escape(texte)}</pre>"
    return ('<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer"><base target="_blank">'
            '<style>body{font-family:sans-serif;margin:8px;overflow-wrap:anywhere}pre{white-space:pre-wrap}</style>' + source)


# --- composition -------------------------------------------------------------------------------------------

def _ligne(v: str, nom: str) -> str:
    # INV-MAIL-4 : un retour chariot dans un en-tête ajouterait des en-têtes (ou des destinataires) à l'insu de l'utilisateur.
    if any(c in v for c in "\r\n\x00"):
        raise Invalide(langues.t("serveur.mail.entete_invalide", champ=nom))
    return v.strip()


def adresses(v: str, nom: str) -> list[str]:
    liste = [a for _, a in getaddresses([_ligne(v, nom)]) if a]
    if any(a.count("@") != 1 or " " in a for a in liste):
        raise Invalide(langues.t("serveur.mail.adresse_invalide", champ=nom))
    return liste


def brouillon(mode: str, brut: bytes, moi: str) -> dict:
    """Destinataires et objet proposés pour répondre, répondre à tous ou transférer."""
    m = lire(brut)
    objet = _entete(m, "subject")
    pre = PREFIXES[mode]
    if not objet.lower().startswith(pre.strip().lower()):
        objet = pre + objet
    if mode == "transferer":
        return {"a": "", "cc": "", "objet": objet}
    a = _entete(m, "reply-to") or _entete(m, "from")
    cc = ""
    if mode == "repondre_tous":
        vus = {x.lower() for _, x in getaddresses([a])} | {moi.lower()}
        autres = [f"{n} <{x}>" if n else x for n, x in getaddresses([_entete(m, "to"), _entete(m, "cc")]) if x and x.lower() not in vus]
        cc = ", ".join(autres)
    return {"a": a, "cc": cc, "objet": objet}


def composer(mode: str, brut: bytes | None, moi: str, a: str, cc: str, objet: str, texte: str) -> EmailMessage:
    """Message à envoyer ; réponse : In-Reply-To et References ; transfert : texte cité et pièces jointes reprises."""
    dest, copies = adresses(a, "a"), adresses(cc, "cc")
    if not dest:
        raise Invalide(langues.t("serveur.mail.destinataire_requis"))
    msg = EmailMessage(policy=policy.SMTP)
    msg["From"], msg["To"] = moi, ", ".join(dest)
    if copies:
        msg["Cc"] = ", ".join(copies)
    msg["Subject"] = _ligne(objet, "objet")
    msg["Date"], msg["Message-ID"] = format_datetime(dt.datetime.now().astimezone()), make_msgid(domain=moi.split("@")[-1])
    corps_ = texte
    if brut:
        o = lire(brut)
        cite = texte_seul(o)
        entete = langues.t("serveur.mail.citation", de=_entete(o, "from"), date=_entete(o, "date"))
        if mode == "transferer":
            corps_ += f"\n\n{langues.t('serveur.mail.transfert')}\n{entete}\n{langues.t('serveur.mail.objet', objet=_entete(o, 'subject'))}\n\n{cite}"
        else:
            corps_ += f"\n\n{entete}\n" + "\n".join("> " + x for x in cite.splitlines())
            if mid := _entete(o, "message-id"):
                msg["In-Reply-To"] = mid
                msg["References"] = " ".join(x for x in (_entete(o, "references"), mid) if x)
    msg.set_content(corps_)
    if brut and mode == "transferer":
        for p in pieces(lire(brut)):
            msg.add_attachment(p.get_payload(decode=True) or b"", maintype=p.get_content_maintype(),
                               subtype=p.get_content_subtype(), filename=nom_sur(p.get_filename() or ""))
    return msg
