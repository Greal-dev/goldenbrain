"""Adaptateur Claude Code : lancer un tour en `claude -p`, lire un transcript.

Rôle : traduire le flux `stream-json` en `Evenement`, arrêter l'arbre de processus,
lire `~/.claude/projects/*/<session>.jsonl`.
Frontières : n'écrit pas dans le vault ; une instance par tour.
Invariants portés : aucun en propre (INV-EXEC-3 repose sur l'événement `session` émis tôt).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import shutil
import threading
from pathlib import Path
from typing import AsyncIterator

from . import Evenement, Message, distant as _distant, suivi as _suivi
from .processus import SESSION_PROPRE, arreter_arbre


_VERROU = threading.Lock()
_TRANSCRIPTS: dict[tuple, list[Message]] = {}  # analyses récentes de transcripts (voir `transcript`)


def _instant(texte: str):
    """Date ISO comparable (transcripts en UTC, journaux en heure locale sans fuseau)."""
    try:
        d = dt.datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone() if d.tzinfo is None else d

LIMITE_LIGNE = 64 * 1024 * 1024  # un événement stream-json dépasse souvent les 64 Ko par défaut


def _resume_outil(bloc: dict) -> str:
    entree = bloc.get("input") or {}
    detail = next((str(v) for v in entree.values() if isinstance(v, str)), "") \
        if isinstance(entree, dict) else ""
    detail = " ".join(detail.split())
    return f"{bloc.get('name', '?')}: {detail[:160]}" if detail else str(bloc.get("name", "?"))


def _blocs(contenu) -> list[dict]:
    if isinstance(contenu, str):
        return [{"type": "text", "text": contenu}]
    return [b for b in contenu or [] if isinstance(b, dict)]


def _texte_du_tour(textes: list[str], resultat: str) -> str:
    """Texte de fin de tour : tous les messages de l'agent quand `result` n'est que le dernier
    d'entre eux (cas réel), sinon `result` seul."""
    if len(textes) > 1 and resultat.strip() == textes[-1].strip():
        return "\n\n".join(textes)
    return resultat


def _contexte(message) -> int | None:
    """Jetons du contexte au dernier appel : entrée + cache lu + cache écrit."""
    u = (message or {}).get("usage") if isinstance(message, dict) else None
    if not isinstance(u, dict):
        return None
    total = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                             "cache_creation_input_tokens"))
    return total or None


BRUIT_HARNAIS = ("Stop hook", "<task-notification", "<system-reminder", "[SYSTEM NOTIFICATION",
                 "<local-command", "<command-name", "<command-message", "Caveat: The messages below")


class HarnaisClaude:
    nom = "claude"
    consigne_native = True  # --append-system-prompt
    sait_deriver = True     # --fork-session
    compactage_natif = True  # CLAUDE_AUTOCOMPACT_PCT_OVERRIDE (vérifié dans claude 2.1.325)
    ordre_compactage = "/compact"

    def __init__(self, conf: dict | None = None):
        conf = conf or {}
        self.commande = conf.get("commande", "claude")
        self.dossier = conf.get("dossier") or str(Path.home())
        self.arguments = list(conf.get("arguments", []))
        # INV-MCP-1 : sans « heritage », le tour ne charge aucun serveur MCP de l'utilisateur.
        self.mcp = "heritage" if conf.get("mcp") == "heritage" else "aucun"
        self.transcripts = Path(conf.get("transcripts") or Path.home() / ".claude" / "projects")
        self._proc: asyncio.subprocess.Process | None = None
        self.compactage: tuple[float, int] | None = None  # posé par le moteur (INV-COMPACT-1)
        # Exécution dans un codespace (INV-CODESPACE-1) : posé par le moteur, jamais par config.toml.
        self.distant: dict | None = conf.get("distant")
        # INV-RETOUR-1 : posé par le moteur après « Modifier » ; reprise de la session à ce point.
        self.reprendre_a = ""

    def _argv(self, session: str | None, deriver: bool, consigne: str,
              modele: str = "") -> list[str]:
        exe = self.commande if self.distant else shutil.which(self.commande)
        if not exe:
            raise FileNotFoundError(f"exécutable introuvable : {self.commande}")
        argv = [exe, *self.arguments, "-p", "--output-format", "stream-json", "--verbose"]
        if session:
            argv += ["--resume", session]
            if self.reprendre_a:  # option cachée de claude 2.1.325, vérifiée par essai réel (16/11)
                argv += ["--resume-session-at", self.reprendre_a]
            if deriver or self.reprendre_a:
                argv.append("--fork-session")
        if self.mcp == "aucun":
            argv.append("--strict-mcp-config")  # sans --mcp-config : aucun serveur MCP
        if consigne:
            argv += ["--append-system-prompt", consigne]
        if modele:
            nom, _, effort = modele.partition("@")  # `modèle@effort` (INV-REX-1)
            argv += (["--model", nom] if nom else []) + (["--effort", effort] if effort else [])
        return argv

    def _env_compactage(self) -> dict[str, str]:
        # Pourcentage de la fenêtre propre à Claude ; le plafond en jetons y est déjà converti.
        if not self.compactage:
            return {}
        return {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": str(max(1, min(100, round(self.compactage[0]))))}

    async def lancer(self, message: str, *, session: str | None, deriver: bool,
                     consigne: str, env: dict[str, str],
                     modele: str = "") -> AsyncIterator[Evenement]:
        env = {**env, **self._env_compactage()}  # INV-COMPACT-1 (transmis aussi au codespace)
        argv = await _distant.envelopper(self._argv(session, deriver, consigne, modele),
                                         self.distant, env)
        self._proc = proc = await asyncio.create_subprocess_exec(
            *argv, cwd=self.dossier,
            env={**os.environ, **env}, limit=LIMITE_LIGNE,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, **SESSION_PROPRE)
        erreurs = asyncio.create_task(proc.stderr.read())
        try:
            # Prompt par stdin : un argument casserait sur les citations de la ligne de commande
            # Windows.
            proc.stdin.write(message.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()
            vue, conclu, contexte = "", False, None
            ouverts: set[str] = set()  # sous-agents lancés, pas encore revenus (INV-TRAVAUX-1)
            # Tous les textes du tour : un hook de fin de session (ex. « LIAGE TÂCHE ») force un
            # second message après la vraie réponse, et `result` ne porte que le dernier. Les
            # blocs <fiche>, <decoupage>, <avis> se cherchent donc dans le tour entier
            # (parcours réel du 14/11 : découpage rendu, déclaré « insuffisant »).
            textes: list[str] = []
            async for ligne in proc.stdout:
                try:
                    brut = json.loads(ligne)
                except ValueError:
                    continue
                if not isinstance(brut, dict):
                    continue
                if (sid := brut.get("session_id")) and sid != vue:
                    vue = sid
                    yield Evenement("session", session=sid, brut=brut)
                if brut.get("type") == "assistant":
                    contexte = _contexte(brut.get("message")) or contexte  # dernier appel = contexte courant
                    for bloc in _blocs((brut.get("message") or {}).get("content")):
                        if bloc.get("type") == "text" and bloc.get("text"):
                            textes.append(bloc["text"])
                            yield Evenement("texte", texte=bloc["text"], brut=brut)
                        elif bloc.get("type") == "tool_use":
                            yield Evenement("outil", texte=_resume_outil(bloc), brut=brut)
                elif brut.get("type") == "result":
                    conclu = True
                    if brut.get("is_error") or brut.get("subtype", "success") != "success":
                        # `errors` porte la cause (« No conversation found with session ID »)
                        # quand `result` est absent : INV-SESSION-1 la reconnaît.
                        cause = (brut.get("result") or "; ".join(map(str, brut.get("errors") or []))
                                 or brut.get("subtype"))
                        yield Evenement("erreur", brut=brut,
                                        texte=_distant.indice(str(cause), self.distant))
                    else:
                        yield Evenement("fin", session=brut.get("session_id", vue),
                                        texte=_texte_du_tour(textes, str(brut.get("result") or "")),
                                        brut=brut, mesure={"contexte": contexte,
                                                           "cout": brut.get("total_cost_usd")})
                for ev in _suivi.claude(brut, ouverts):
                    yield ev
            code = await proc.wait()
            stderr = (await erreurs).decode("utf-8", "replace").strip()
            if not conclu:
                yield Evenement("erreur", texte=stderr[-2000:] or f"processus terminé (code {code})")
        finally:
            # Sortie anormale (exception, annulation, générateur abandonné) : pas d'orphelin.
            if proc.returncode is None:
                await self.arreter()
            erreurs.cancel()

    async def arreter(self) -> None:
        proc = self._proc
        if not proc or proc.returncode is not None:
            return
        await arreter_arbre(proc)

    def chemin_transcript(self, session: str) -> str:
        if self.distant:
            return ""
        fichier = next(self.transcripts.glob(f"*/{session}.jsonl"), None) if session else None
        return str(fichier) if fichier else ""

    def transcript(self, session: str, limite: int) -> list[Message]:
        if self.distant:  # transcript resté dans le codespace : les journaux en tiennent lieu
            raise NotImplementedError
        fichier = next(self.transcripts.glob(f"*/{session}.jsonl"), None) if session else None
        if not fichier:
            return []
        # Analyse mémorisée par (fichier, date, taille) : l'ouverture d'une tâche relit son fil plusieurs fois (premier affichage,
        # puis chaque fin de tour) ; un transcript de plusieurs Mo ne se ré-analyse que s'il a changé.
        st = fichier.stat()
        cle = (str(fichier), st.st_mtime_ns, st.st_size)
        if (vu := _TRANSCRIPTS.get(cle)) is None:
            vu = self._analyser(fichier)
            with _VERROU:  # appelé depuis des fils de travail
                while len(_TRANSCRIPTS) >= 4:
                    _TRANSCRIPTS.pop(next(iter(_TRANSCRIPTS)))
                _TRANSCRIPTS[cle] = vu
        return list(vu[-limite:] if limite > 0 else vu)

    @staticmethod
    def _analyser(fichier: Path) -> list[Message]:
        messages: list[Message] = []
        apres_hook = False
        for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                brut = json.loads(ligne)
            except ValueError:
                continue
            if not isinstance(brut, dict) or brut.get("type") not in ("user", "assistant"):
                continue
            blocs = _blocs((brut.get("message") or {}).get("content"))
            textes = [b.get("text", "") for b in blocs if b.get("type") == "text"]
            outils = [str(b.get("name", "?")) for b in blocs if b.get("type") == "tool_use"]
            if not any(t.strip() for t in textes) and not outils:
                continue  # message fait de seuls tool_result (ou de réflexion) : bruit
            if brut["type"] == "user" and textes[:1] and textes[0].lstrip().startswith(BRUIT_HARNAIS):
                # Messages que le harnais s'adresse à lui-même sous le rôle « utilisateur » : retour
                # de hook, fin d'une commande d'arrière-plan, rappel système. L'utilisateur ne les a pas
                # écrits (constat du 13/11 : un <task-notification> affiché comme son message).
                apres_hook = apres_hook or textes[0].lstrip().startswith("Stop hook")
                continue
            role = "utilisateur" if brut["type"] == "user" else "assistant"
            if role == "utilisateur":
                apres_hook = False
            messages.append(Message(role, "\n".join(textes).strip(), outils,
                                    str(brut.get("timestamp") or ""),
                                    secondaire=apres_hook and role == "assistant"))
        return messages

    def point_de_reprise(self, session: str, texte: str, date: str) -> str:
        """INV-RETOUR-1 : identifiant de l'entrée qui précède le message `texte` dans la session
        (le message le plus proche de `date` s'il revient plusieurs fois), "" si introuvable ou
        si le message ouvre la session (rien à garder : conversation neuve)."""
        if not (chemin := self.chemin_transcript(session)):
            return ""
        fichier = Path(chemin)
        extrait = " ".join(texte.split())[:80]
        quand = _instant(date)
        retenus = []
        for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                brut = json.loads(ligne)
            except ValueError:
                continue
            if not isinstance(brut, dict) or brut.get("type") != "user":
                continue
            textes = [b.get("text", "") for b in _blocs((brut.get("message") or {}).get("content"))
                      if b.get("type") == "text"]
            if extrait and extrait in " ".join(" ".join(textes).split()):
                retenus.append(brut)
        if not retenus:
            return ""
        if quand:
            retenus.sort(key=lambda b: abs(((_instant(str(b.get("timestamp") or "")) or quand)
                                            - quand).total_seconds()))
        return str(retenus[0].get("parentUuid") or "")

    def commande_terminal(self, session: str) -> str:
        commande = " ".join([self.commande, *self.arguments, "--resume", session])
        return _distant.commande_terminal(commande, self.distant) if self.distant else commande

    def argv_natif(self, session: str, neuve: bool, consigne: str, modele: str,
                   message: str) -> list[str]:
        """Interface native (INV-NATIF-1) : `claude` interactif sur la session de la tâche — neuve
        (`--session-id`, premier message en argument) ou reprise —, même consigne qu'un tour."""
        argv = [shutil.which(self.commande) or self.commande, *self.arguments,
                "--session-id" if neuve else "--resume", session]
        if consigne:
            argv += ["--append-system-prompt", consigne]
        if modele:
            nom, _, effort = modele.partition("@")  # `modèle@effort` (INV-REX-1)
            argv += (["--model", nom] if nom else []) + (["--effort", effort] if effort else [])
        return argv + ([message] if message else [])
