"""Enregistrement d'étape : retrouver l'arbre de travail et la branche d'un tour interrompu.

Rôle : à l'arrêt d'un tour de développement, repérer (git, lecture seule) l'arbre de travail et la
branche sur lesquels l'agent travaillait, les noter dans la ligne « Situation » de la fiche, et les
rappeler à l'agent dans le message de reprise ; porter la consigne « commit d'étape » de tout tour
de développement.
Frontières : git en lecture seule (`worktree list`, `status`, `log`) ; aucun harnais lancé ; la seule
écriture vault est la ligne « Situation » de la fiche ; sans dépôt déclaré, rien n'est noté.
Invariants portés : INV-REPRISE-2.
"""

from __future__ import annotations

import datetime as dt
import logging
import subprocess
from pathlib import Path

from . import depot, fiches, langues

log = logging.getLogger(__name__)
FENETRE_S = 6 * 3600  # sans heure de départ : un arbre touché dans les six dernières heures
MARQUE = "[étape]"  # préfixe de la ligne que GoldenBrain pose dans « Situation » (remplacée à chaque arrêt)


def _git(dossier: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", dossier, *args], capture_output=True, text=True,
                           encoding="utf-8", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _arbres(dossier: str) -> list[dict]:
    """Arbres de travail secondaires du dépôt (le premier, principal, est écarté)."""
    blocs = [b for b in _git(dossier, "worktree", "list", "--porcelain").split("\n\n") if b.strip()]
    out = []
    for b in blocs[1:]:
        champs = dict(ligne.partition(" ")[::2] for ligne in b.splitlines())
        if champs.get("worktree") and champs.get("branch"):
            out.append({"arbre": champs["worktree"], "branche": champs["branch"].removeprefix("refs/heads/")})
    return out


def retrouver(moteur, ident: str, depuis: str | None = None) -> dict | None:
    """L'arbre de travail le plus récemment actif depuis `depuis` (date ISO du début du tour) :
    modifié et non enregistré (`sale`) ou enregistré depuis. None sans dépôt ni arbre actif."""
    dossier, _ = depot.dossier_de_travail(moteur.vault, ident)
    if not dossier:
        return None
    try:
        limite = dt.datetime.fromisoformat(depuis).timestamp() if depuis else dt.datetime.now().timestamp() - FENETRE_S
    except ValueError:
        limite = dt.datetime.now().timestamp() - FENETRE_S
    actifs = []
    for a in _arbres(dossier):
        if not Path(a["arbre"]).is_dir():
            continue
        date = _git(a["arbre"], "log", "-1", "--format=%ct|%h %s")
        quand, _, sujet = date.partition("|")
        sale = bool(_git(a["arbre"], "status", "--porcelain"))
        if sale or (quand.isdigit() and int(quand) >= limite):
            actifs.append({**a, "dernier": sujet.strip(), "sale": sale, "_t": int(quand) if quand.isdigit() else 0})
    if not actifs:
        return None
    meilleur = max(actifs, key=lambda a: (a["sale"], a["_t"]))
    meilleur.pop("_t")
    return meilleur


def phrase(info: dict) -> str:
    cle = "serveur.etape.note_sale" if info["sale"] else "serveur.etape.note"
    return langues.t(cle, arbre=info["arbre"], branche=info["branche"], dernier=info["dernier"] or "?")


def rappel(moteur, ident: str) -> str:
    """Fin du message de reprise : où retrouver le travail (vide si rien à retrouver)."""
    info = retrouver(moteur, ident)
    return " " + langues.t("serveur.etape.rappel", arbre=info["arbre"], branche=info["branche"]) if info else ""


def noter(moteur, ident: str, depuis: str | None) -> None:
    """INV-REPRISE-2 : l'arbre de travail et la branche, dans la « Situation » de la fiche."""
    info = retrouver(moteur, ident, depuis)
    if not info:
        return
    try:
        fiche = fiches.lire_fiche(fiches.lire(moteur.vault.tache(ident).chemin))
        reste = fiche.get("situation") or ""
        if reste.startswith(MARQUE):  # la note d'un arrêt précédent est remplacée, pas empilée
            reste = reste.partition(" | ")[2]
        fiche["situation"] = f"{MARQUE} {phrase(info)}" + (f" | {reste}" if reste else "")
        moteur.vault.modifier(ident, {}, fiche)
    except Exception as e:  # noqa: BLE001 — une note manquée ne gêne jamais l'arrêt d'un tour
        log.warning("étape de %s non notée : %s", ident, e)


def consigne(moteur, ident: str) -> str:
    """INV-REPRISE-2 : fin de la consigne d'un tour de développement (tâche d'un projet à dépôt)."""
    dossier, _ = depot.dossier_de_travail(moteur.vault, ident)
    return "\n" + langues.t("serveur.etape.consigne") if dossier else ""
