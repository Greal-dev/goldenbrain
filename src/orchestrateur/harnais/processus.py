"""Processus d'un harnais en ligne de commande : résolution de l'exécutable, flux JSON par ligne, arrêt.

Rôle : outillage commun aux adaptateurs `codex` et `opencode` (lancement, lecture des lignes
JSON de stdout, arrêt de l'arbre de processus).
Frontières : ne connaît aucun format d'événement ; n'écrit pas dans le vault.
Invariants portés : aucun.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import AsyncIterator

from .. import poste_ram

LIMITE_LIGNE = 64 * 1024 * 1024  # une ligne d'événement dépasse souvent les 64 Ko par défaut


def resoudre(commande: str) -> list[str]:
    """Argv de tête pour lancer `commande` sans passer par un lanceur `.cmd`.

    Un `.cmd` npm ne se lance pas par `create_subprocess_exec` et ses guillemets sont fragiles :
    on lit sa cible (`"%dp0%\\…\\x.exe"` ou `x.js` lancé par node) et on lance celle-ci.
    """
    exe = shutil.which(commande)
    if not exe:
        raise FileNotFoundError(f"exécutable introuvable : {commande}")
    lanceur = Path(exe)
    if lanceur.suffix.lower() not in (".cmd", ".bat"):
        return [exe]
    cibles = re.findall(r'"%dp0%\\([^"]+\.(?:exe|js))"',
                        lanceur.read_text("utf-8", errors="replace"), re.I)
    cibles = [c for c in cibles if c.lower() != "node.exe"]
    if not cibles:
        raise FileNotFoundError(f"lanceur non résolu : {exe}")
    cible = lanceur.parent / cibles[-1]
    if cible.suffix.lower() != ".js":
        return [str(cible)]
    node = lanceur.parent / "node.exe"
    node = str(node) if node.exists() else shutil.which("node")
    if not node:
        raise FileNotFoundError("node introuvable")
    return [node, str(cible)]


# Sous POSIX le fils mène son propre groupe : l'arrêt vise tout l'arbre (chaîne MCP, outils), pas
# seulement le fils. Windows : `taskkill /T /F`, inchangé.
SESSION_PROPRE = {} if sys.platform == "win32" else {"start_new_session": True}


def _groupe_de(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None  # sorti entre le recensement et la lecture


async def arreter_arbre(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        # taskkill /T : le harnais lance des sous-processus (outils) qu'un kill laisserait.
        tk = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(proc.pid), "/T", "/F",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await tk.wait()
        return
    try:
        groupe = os.getpgid(proc.pid)
        # Recensé AVANT le signal : un processus qui a changé de groupe (navigateur Playwright,
        # serveur lancé par l'agent) échappe à `killpg` mais pas à la parenté ni à la session.
        detaches = [p for p in poste_ram.arbre(proc.pid) if p != proc.pid and _groupe_de(p) not in (groupe, None)]
        if groupe == os.getpgrp():  # fils lancé sans session propre : ne jamais tuer notre groupe
            proc.kill()
        else:
            os.killpg(groupe, signal.SIGKILL)
        for p in detaches:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass  # déjà parti
    except ProcessLookupError:
        pass  # déjà parti
    except PermissionError:
        proc.kill()


class Processus:
    """Un processus de tour : prompt par stdin, une ligne JSON (dict) par événement."""

    def __init__(self):
        self.proc: asyncio.subprocess.Process | None = None
        self.code: int | None = None
        self.stderr = ""

    async def lignes(self, argv: list[str], entree: str, dossier: str,
                     env: dict[str, str]) -> AsyncIterator[dict]:
        self.proc = proc = await asyncio.create_subprocess_exec(
            *argv, cwd=dossier, env={**os.environ, **env}, limit=LIMITE_LIGNE,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, **SESSION_PROPRE)
        erreurs = asyncio.create_task(proc.stderr.read())
        try:
            # Prompt par stdin, jamais en argument : citations de la ligne de commande Windows.
            proc.stdin.write(entree.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()
            async for ligne in proc.stdout:
                try:
                    brut = json.loads(ligne)
                except ValueError:
                    continue
                if isinstance(brut, dict):
                    yield brut
            self.code = await proc.wait()
            self.stderr = (await erreurs).decode("utf-8", "replace").strip()
        finally:
            # Sortie anormale (exception, annulation, générateur abandonné) : pas d'orphelin.
            if proc.returncode is None:
                await self.arreter()
            erreurs.cancel()

    def fin_anormale(self) -> str:
        return self.stderr[-2000:] or f"processus terminé (code {self.code})"

    async def arreter(self) -> None:
        proc = self.proc
        if not proc or proc.returncode is not None:
            return
        await arreter_arbre(proc)
