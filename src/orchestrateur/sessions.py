"""Mémoire des sessions par harnais, préambule de reprise, conversation relue dans les journaux.

Rôle : `etat/sessions.json` (`tache -> {harnais: session}`) pour qu'un changement de harnais
n'oublie pas l'ancienne conversation ; texte du préambule ; reconstruction d'une conversation à
partir des journaux d'une tâche quand le harnais n'a pas de transcript lisible.
Frontières : aucune écriture vault ; ne lance aucun harnais.
Invariants portés : INV-ECO-1 (imposition du moteur choisi à la main) ; lit les journaux d’INV-EXEC-4.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

from . import fiches
from .catalogue import modele_valide
from .harnais import Evenement, Message

log = logging.getLogger(__name__)
# Types de journal relus comme messages du système (échec d’un tour, remontée d’une descendante).
SYSTEME = ("orch_echec", "orch_remontee", "orch_regroupe")  # INV-REGROUPE-2


class Sessions:
    def __init__(self, chemin: Path):
        self.chemin = chemin
        # Un fichier d'état absent ou corrompu ne doit jamais empêcher le serveur de démarrer.
        try:
            donnees = json.loads(chemin.read_text("utf-8"))
        except (OSError, ValueError):
            donnees = {}
        self.donnees: dict[str, dict[str, str]] = {
            str(t): {str(h): str(s) for h, s in d.items()}
            for t, d in (donnees.items() if isinstance(donnees, dict) else [])
            if isinstance(d, dict)}

    def memoriser(self, tache: str, harnais: str, session: str) -> None:
        d = self.donnees.setdefault(tache, {})
        d.pop(harnais, None)  # réinséré en dernier : l'ordre dit quel harnais vient d'être quitté
        d[harnais] = session
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.donnees, ensure_ascii=False, indent=1))

    def session(self, tache: str, harnais: str) -> str:
        return self.donnees.get(tache, {}).get(harnais, "")

    def precedente(self, tache: str, harnais: str) -> tuple[str, str] | None:
        """Dernière session mémorisée de la tâche dans un AUTRE harnais."""
        autres = [(h, s) for h, s in self.donnees.get(tache, {}).items() if h != harnais]
        return autres[-1] if autres else None


def preambule(harnais: str, fiche: str, ancien: str, transcript: str) -> str:
    return (f"[Reprise de la tâche dans {harnais}. Lis sa fiche : {fiche}. Conversation "
            f"précédente ({ancien}) : {transcript or 'non disponible'}.]")


def changement(t, memoire: Sessions, harnais: str | None, modele: str | None,
               defaut: str) -> dict:
    """Clés à écrire pour poser harnais/modèle (None = inchangé, "" = défaut)."""
    maj: dict = {}
    if modele is not None:
        maj["modele"] = modele_valide(modele) or None
    if harnais is not None:
        ancien, nouveau = str(t.fm.get("harnais") or defaut), harnais or defaut
        if nouveau != ancien:
            # Une session n'est pas transportable d'un harnais à l'autre : on la garde de côté
            # pour un retour, et on reprend celle du nouveau harnais s'il en a une.
            if session := str(t.fm.get("session") or ""):
                memoire.memoriser(t.id, ancien, session)
            maj["session"] = memoire.session(t.id, nouveau) or None
            maj.setdefault("modele", None)  # un modèle n'a pas de sens d'un harnais à l'autre
        maj["harnais"] = harnais or None
    if harnais is not None or modele is not None:
        # INV-ECO-1 : un moteur choisi à la main n'est jamais rebasculé ; « défaut » lève l'imposition.
        maj["moteur_impose"] = "oui" if (harnais or modele) else None
    return maj


def premier_message(texte: str, consigne: str, harnais, memoire: Sessions, t, nom: str,
                    registre: dict, confs: dict) -> str:
    """Premier message d'une conversation neuve : consigne (si non native) et préambule de reprise."""
    if precedente := memoire.precedente(t.id, nom):
        ancien, session = precedente
        try:
            chemin = registre[ancien](confs.get(ancien, {})).chemin_transcript(session)
        except Exception:  # harnais retiré ou sans transcript : le préambule le dit
            chemin = ""
        texte = f"{preambule(nom, str(t.chemin), ancien, chemin)}\n\n{texte}"
    if consigne and not getattr(harnais, "consigne_native", True):
        texte = f"{consigne}\n\n{texte}"
    return texte


def _journaux(donnees: Path, ident: str) -> list[Path]:
    # Motif exact : le journal de « a » ne doit pas ramasser ceux de « a-b ».
    motif = re.compile(re.escape(ident) + r"-\d{6}\.jsonl")
    racine = donnees / "journal"
    if not racine.is_dir():
        return []
    return sorted((f for d in racine.iterdir() if d.is_dir() for f in d.iterdir()
                   if motif.fullmatch(f.name)), key=lambda f: (f.parent.name, f.name))


def echecs_journaux(donnees: Path, ident: str) -> list[Message]:
    """Messages du système (échecs de tours) d'une tâche, relus dans ses journaux."""
    out = []
    for fichier in _journaux(donnees, ident):
        for ligne in fichier.read_text("utf-8", errors="replace").splitlines():
            if not any(f'"{s}"' in ligne for s in SYSTEME):
                continue
            try:
                brut = json.loads(ligne)
            except ValueError:
                continue
            if isinstance(brut, dict) and brut.get("type") in SYSTEME:
                out.append(Message("systeme", str(brut.get("texte") or ""), [],
                                   str(brut.get("date") or "")))
    return out


def _instant(texte: str) -> dt.datetime | None:
    # Transcripts en UTC (« Z »), journaux en heure locale sans fuseau : tout se compare en aware.
    try:
        d = dt.datetime.fromisoformat(texte)
    except ValueError:
        return None
    return d.astimezone() if d.tzinfo is None else d


def inserer_par_date(messages: list[Message], ajouts: list[Message]) -> list[Message]:
    """Range chaque ajout après le dernier message daté qui le précède ; sinon à la fin."""
    for a in ajouts:
        quand, place = _instant(a.horodatage), len(messages)
        if quand:
            idx = [i for i, m in enumerate(messages) if (x := _instant(m.horodatage)) and x <= quand]
            if idx:
                place = idx[-1] + 1
        messages.insert(place, a)
    return messages


def relire_journaux(donnees: Path, ident: str, limite: int, registre: dict) -> list[Message]:
    """Conversation d'une tâche : messages soumis (`orch_message`) + textes et outils des tours."""
    messages: list[Message] = []
    for fichier in _journaux(donnees, ident):
        analyser, etat, precedente, courant = None, {}, None, None
        for ligne in fichier.read_text("utf-8", errors="replace").splitlines():
            if ligne == precedente:
                continue  # une ligne brute qui porte deux événements est journalisée deux fois
            precedente = ligne
            try:
                brut = json.loads(ligne)
            except ValueError:
                continue
            if not isinstance(brut, dict):
                continue
            if brut.get("type") == "orch_message":
                analyser = getattr(registre.get(str(brut.get("harnais"))), "analyser", None)
                messages.append(Message("utilisateur", str(brut.get("texte") or ""), [],
                                        str(brut.get("date") or "")))
                courant = None
                continue
            if brut.get("type") in SYSTEME:  # INV-EXEC-8, INV-PILOTAGE-3 : message du système
                messages.append(Message("systeme", str(brut.get("texte") or ""), [],
                                        str(brut.get("date") or "")))
                courant = None
                continue
            if analyser:
                evs = analyser(brut, etat)
            elif brut.get("type") in ("texte", "outil"):
                evs = [Evenement(brut["type"], texte=str(brut.get("texte") or ""))]
            else:
                evs = []
            for ev in evs:
                if ev.type not in ("texte", "outil"):
                    continue
                if courant is None:
                    courant = Message("assistant", "", [], "")
                    messages.append(courant)
                if ev.type == "texte":
                    courant.texte = f"{courant.texte}\n\n{ev.texte}".strip()
                else:
                    courant.outils.append(ev.texte)
    return messages[-limite:] if limite > 0 else messages
