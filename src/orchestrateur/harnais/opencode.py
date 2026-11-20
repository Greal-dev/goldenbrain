"""Adaptateur OpenCode : un tour en `opencode run --format json`, reprise par `-s <id>`.

Rôle : traduire le flux JSON d'`opencode run` en `Evenement` (formats observés en réel le 13/11
sur opencode 1.18.31, extraits dans `tests/donnees/opencode-*.jsonl`) ; découvrir les modèles
(`opencode models`).
Frontières : n'écrit pas dans le vault ; une instance par tour ; pas de transcript lisible
(la route `/conversation` se rabat sur les journaux).
Guet du journal (incident du 18/11) : sur un quota épuisé, `opencode run` écrit l'erreur dans son
journal (`~/.local/share/opencode/log/*.log`) et reste vivant ; le guet la lit et arrête le tour.
Invariants portés : INV-QUOTA-2 (quota lu dans le journal du harnais) ; INV-EXEC-3 repose sur
l'événement `session` émis tôt.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from contextlib import aclosing, suppress
from pathlib import Path
from typing import AsyncIterator

from . import Evenement, Message, suivi as _suivi
from .processus import Processus, resoudre
from .. import echecs

GUET_S = 3.0  # INV-QUOTA-2 : intervalle de lecture du journal d'OpenCode
ERREUR_JOURNAL = re.compile(r'error\.error="((?:[^"\\]|\\.)*)"')


def _journal_courant(dossier: Path) -> Path | None:
    try:
        return max(dossier.glob("*.log"), key=lambda f: f.stat().st_mtime, default=None)
    except OSError:
        return None


def quota_du_journal(lignes: list[str], session: str) -> str:
    """Motif d'un quota épuisé dans des lignes du journal d'OpenCode (session du tour), ou ""."""
    for ligne in lignes:
        if "level=ERROR" in ligne and (not session or f"session.id={session}" in ligne):
            motif = (m[1] if (m := ERREUR_JOURNAL.search(ligne)) else ligne).strip()
            if echecs.est_quota(motif):
                return motif
    return ""


def _resume_outil(part: dict) -> str:
    etat = part.get("state") or {}
    entree = etat.get("input") or {}
    detail = entree.get("command") if isinstance(entree, dict) else None
    detail = " ".join(str(detail or etat.get("title") or "").split())
    nom = str(part.get("tool") or "?")
    return f"{nom}: {detail[:160]}" if detail else nom


def analyser(brut: dict, etat: dict) -> list[Evenement]:
    """Une ligne JSON d'`opencode run --format json` -> événements ; `etat` porte le fil du tour."""
    out: list[Evenement] = []
    sid = brut.get("sessionID")
    if sid and sid != etat.get("session"):
        etat["session"] = str(sid)
        out.append(Evenement("session", session=etat["session"], brut=brut))
    part = brut.get("part") if isinstance(brut.get("part"), dict) else {}
    type_ = brut.get("type")
    if type_ == "text" and str(part.get("text") or "").strip():
        etat["dernier"] = str(part["text"])
        out.append(Evenement("texte", texte=etat["dernier"], brut=brut))
    elif type_ == "step_finish":
        t = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        c = t.get("cache") if isinstance(t.get("cache"), dict) else {}
        etat["contexte"] = (int(t.get("input") or 0) + int(c.get("read") or 0) + int(c.get("write") or 0)) or None
        etat["cout"] = (etat.get("cout") or 0) + float(part.get("cost") or 0)
    elif type_ == "tool_use":
        out.append(Evenement("outil", texte=_resume_outil(part), brut=brut))
        out.extend(_suivi.opencode(part))  # INV-TRAVAUX-1
    elif type_ == "error":
        erreur = brut.get("error") if isinstance(brut.get("error"), dict) else {}
        donnees = erreur.get("data") if isinstance(erreur.get("data"), dict) else {}
        etat["conclu"] = True
        out.append(Evenement("erreur", brut=brut, texte=str(
            donnees.get("message") or erreur.get("name") or "erreur opencode")))
    return out


class HarnaisOpencode:
    nom = "opencode"
    # Pas d'option de consigne système en `run` : le moteur la place en tête du 1er message.
    consigne_native = False
    sait_deriver = True  # `-s <id> --fork` (essai réel du 13/11)
    compactage_natif = False  # aucune option de seuil dans `opencode run` : repli commun
    ordre_compactage = "/compact"
    compactage: tuple[float, int] | None = None
    analyser = staticmethod(analyser)

    def __init__(self, conf: dict | None = None):
        conf = conf or {}
        self.commande = conf.get("commande", "opencode")
        self.dossier = conf.get("dossier") or str(Path.home())
        self.arguments = list(conf.get("arguments", []))
        self.journal = Path(conf.get("journal") or "~/.local/share/opencode/log").expanduser()
        self._p = Processus()
        self._trace = ""

    def _argv(self, session: str | None, deriver: bool, modele: str) -> list[str]:
        # Message par stdin (lu par `opencode run` quand stdin n'est pas un terminal).
        argv = [*resoudre(self.commande), "run", "--format", "json", *self.arguments]
        if session:
            argv += ["-s", session] + (["--fork"] if deriver else [])
        if modele:
            argv += ["-m", modele]
        return argv

    async def lancer(self, message: str, *, session: str | None, deriver: bool,
                     consigne: str, env: dict[str, str], modele: str = "") -> AsyncIterator[Evenement]:
        etat: dict = {}
        guet = asyncio.ensure_future(self._guetter(etat))
        try:
            async with aclosing(self._p.lignes(self._argv(session, deriver, modele), message,
                                               self.dossier, env)) as flux:
                async for brut in flux:
                    for ev in analyser(brut, etat):
                        yield ev
        finally:
            guet.cancel()
            with suppress(asyncio.CancelledError):
                await guet
        if etat.get("quota"):  # INV-QUOTA-2 : processus arrêté par le guet, motif du journal
            yield Evenement("erreur", texte=etat["quota"])
            return
        if etat.get("conclu"):
            return
        # Pas d'événement de fin dans le flux : la fin propre est la sortie en code 0.
        if self._p.code == 0:
            yield Evenement("fin", session=etat.get("session", ""), texte=etat.get("dernier", ""),
                            mesure={"contexte": etat.get("contexte"), "cout": etat.get("cout")})
        else:
            yield Evenement("erreur", texte=self._p.fin_anormale())

    async def _guetter(self, etat: dict) -> None:
        """INV-QUOTA-2 : lit les octets nouveaux du journal ; un quota de la session arrête le tour."""
        fichier = _journal_courant(self.journal)
        debut = fichier.stat().st_size if fichier else 0
        while True:
            await asyncio.sleep(GUET_S)
            if (courant := _journal_courant(self.journal)) != fichier:
                fichier, debut = courant, 0  # rotation : nouveau fichier, lu depuis le début
            if not fichier:
                continue
            try:
                with open(fichier, encoding="utf-8", errors="replace") as f:
                    f.seek(debut)
                    lignes = f.read().splitlines()
                    debut = f.tell()
            except OSError:
                continue
            if lignes:
                self._trace = lignes[-1]
            if motif := quota_du_journal(lignes, str(etat.get("session") or "")):
                etat["quota"] = motif
                await self._p.arreter()
                return

    def derniere_trace(self) -> str:
        """Dernière ligne du journal d'OpenCode lue pendant le tour (vigie, INV-VIGIE-1)."""
        return self._trace

    async def arreter(self) -> None:
        await self._p.arreter()

    def transcript(self, session: str, limite: int) -> list[Message]:
        raise NotImplementedError

    def decouvrir_modeles(self) -> list[str]:
        """`opencode models` (appel bloquant : à lancer hors de la boucle d'événements)."""
        sortie = subprocess.run([*resoudre(self.commande), "models"], cwd=self.dossier,
                                capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        lignes = sortie.stdout.decode("utf-8", "replace").splitlines()
        return [m.strip() for m in lignes if "/" in m and " " not in m.strip()]

    def commande_terminal(self, session: str) -> str:
        return " ".join([self.commande, "-s", session])
