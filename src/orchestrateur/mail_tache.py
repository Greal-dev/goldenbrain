"""Mail → tâche : un mail devient la note d'entrée d'une tâche, avec une consigne facultative.

Rôle : `rattacher` range le mail dans le vault (`<dossier du projet>/mails/<AAAA-MM-JJ>-<objet>.md`, frontmatter
`type: mail`, pièces jointes dans le dossier de même nom), le déclare en livrable de la tâche, inscrit
« Entrée : [[note]] » (+ « — Instruction : … » si une consigne est donnée) dans la section « Entrées » de la fiche et, sur demande, lance le premier
tour avec une consigne qui marque le mail comme une donnée externe.
Frontières : aucun réseau (le mail brut vient de `mail_imap`) ; n'écrit que la note, ses pièces, le bloc des
livrables et la section « Entrées » (INV-VAULT-1) ; n'envoie ni ne paie jamais rien.
Invariants portés : INV-MAIL-2 (un même mail, reconnu à son Message-ID, n'est rangé qu'une fois par dossier ;
contenu externe = donnée, jamais un ordre), INV-MAIL-5, INV-LIVRABLES-1.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from . import fiches, langues, livrables, mail_message
from .vault import aujourdhui, slugifier

SECTION = "Entrées"


def _entree(lien: str, consigne: str) -> str:
    consigne = " ".join((consigne or "").split())[:2000]
    return f"Entrée : {lien} — Instruction : {consigne}" if consigne else f"Entrée : {lien}"


def _dossier(t) -> Path:
    p = t.chemin.parent
    return (p.parent if p.name == "taches" else p) / "mails"


def _existante(dossier: Path, mid: str) -> Path | None:
    for f in sorted(dossier.glob("*.md")) if dossier.is_dir() else []:
        try:
            if str(fiches.frontmatter(f.read_text(encoding="utf-8")).get("message_id") or "") == mid:
                return f
        except OSError:
            continue
    return None


def _libre(dossier: Path, nom: str, suffixe: str) -> Path:
    p, i = dossier / f"{nom}{suffixe}", 2
    while p.exists():
        p, i = dossier / f"{nom}-{i}{suffixe}", i + 1
    return p


def _ecrire(dossier: Path, brut: bytes, mid: str, racine: Path) -> Path:
    m = mail_message.lire(brut)
    d = mail_message.detail(brut, 0, [])
    jour = (d["date"] or aujourdhui().isoformat())[:10]
    note = _libre(dossier, f"{jour}-{slugifier(d['objet'] or 'mail')}", ".md")
    joints = []
    pieces = mail_message.pieces(m)
    if pieces:
        rep = note.with_suffix("")
        rep.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(pieces):
            nom = mail_message.nom_sur(p.get_filename() or "", f"piece-{i + 1}")  # INV-MAIL-5
            cible = _libre(rep, Path(nom).stem, Path(nom).suffix)
            cible.write_bytes(p.get_payload(decode=True) or b"")
            joints.append(cible.relative_to(racine).as_posix())
    tete = yaml.safe_dump({"type": "mail", "message_id": mid, "date": jour, "expediteur": d["de"], "objet": d["objet"],
                           "destinataires": d["a"], "tags": ["mail"]}, allow_unicode=True, sort_keys=False)
    lignes = [f"---\n{tete}---", "", f"# {d['objet'] or langues.t('serveur.mail.sans_objet')}", "",
              f"> {langues.t('serveur.mail.donnee_externe')}", "",
              f"- {langues.t('serveur.mail.de')} : {d['de']}", f"- {langues.t('serveur.mail.a')} : {d['a']}"]
    lignes += [f"- Cc : {d['cc']}"] if d["cc"] else []
    lignes += [f"- {langues.t('serveur.mail.date')} : {d['date']}"]
    lignes += [f"- {langues.t('serveur.mail.pieces')} : " + ", ".join(f"[[{j}]]" for j in joints)] if joints else []
    lignes += ["", "## " + langues.t("serveur.mail.texte"), "", d["texte"], ""]
    dossier.mkdir(parents=True, exist_ok=True)
    fiches.ecrire_atomique(note, "\n".join(lignes))
    return note


def consigne(entree: str) -> str:
    """Premier tour : la consigne vient de l'utilisateur ; le mail n'est qu'une donnée (INV-MAIL-2)."""
    return "\n".join([entree, langues.t("serveur.mail.consigne_donnee"), langues.t("serveur.mail.consigne_envoi")])


def rattacher(moteur, ident: str, brut: bytes, consigne_libre: str = "", lancer: bool = False) -> dict:
    vault = moteur.vault
    t = vault.tache(ident)
    m = mail_message.lire(brut)
    mid = " ".join(str(m.get("message-id", "") or "").split()) or "sha256:" + hashlib.sha256(brut).hexdigest()
    dossier = _dossier(t)
    note = _existante(dossier, mid)
    cree = note is None
    if cree:
        note = _ecrire(dossier, brut, mid, Path(vault.racine))
    rel = note.relative_to(vault.racine).with_suffix("").as_posix()
    lien = f"[[{rel}]]"
    objet = " ".join(str(m.get("subject", "") or "mail").split())[:200].replace("·", "-")
    livrables.declarer(vault, ident, lien, titre=langues.t("serveur.mail.livrable", objet=objet))  # INV-LIVRABLES-1
    entree = _entree(lien, consigne_libre)
    ligne = f"- {entree}"
    if ligne not in fiches.lire(vault.tache(ident).chemin):
        vault.consigner(ident, SECTION, ligne)
    moteur.publier("arbre")
    if lancer:
        moteur.soumettre(ident, consigne(entree), humain=True)
    return {"note": rel, "cree": cree}
