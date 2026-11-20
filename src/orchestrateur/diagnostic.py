"""Diagnostic d'un tour silencieux : processeur de l'agent et descendants qui le retiennent.

Rôle : dire en une phrase ce qui retient un agent muet — un script de contrôle (hook), une
commande en cours, l'attente de la réponse du modèle — à partir de son arbre de processus.
Windows : CIM `Win32_Process` par PowerShell (commande, parent, date de création) et
`poste_ram.temps_cpu` (processeur sur une fenêtre courte). Linux : `/proc` (parent, début,
temps processeur, commande). Ailleurs : repli neutre.
Frontières : aucune décision ; n'arrête un processus que sur appel explicite (`arreter`), après
le contrôle d'appartenance fait par `vigie` ; aucune dépendance nouvelle.
Invariants portés : INV-VIGIE-1 (détection seule ; un arrêt n'est qu'un geste humain).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from . import langues, poste_ram

WINDOWS = sys.platform == "win32"
# Un descendant né dans les premières secondes du tour est de la plomberie de session (serveurs
# MCP, console) : il vit autant que l'agent et n'explique pas un silence.
PLOMBERIE_S = 20
CPU_ACTIF_PCT = 5.0
IGNORES = {"conhost.exe"}
HOOK = re.compile(r"[\\/]hooks?[\\/]", re.I)
SCRIPT = re.compile(r"([^\s\\/\"']+\.(?:sh|py|ps1|js|cmd|bat))", re.I)
PS = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | "
      "ForEach-Object { [pscustomobject]@{p=$_.ProcessId; q=$_.ParentProcessId; n=$_.Name; "
      "c=$_.CommandLine; d=if ($_.CreationDate) { ([DateTimeOffset]$_.CreationDate)"
      ".ToUnixTimeSeconds() } else { 0 } } } | ConvertTo-Json -Compress")


@dataclass
class Processus:
    pid: int
    parent: int
    nom: str
    commande: str
    debut: float  # secondes depuis l'époque ; 0 si inconnu


def _stat(pid: str) -> list[str]:
    # « pid (comm) état ppid … » : la commande peut contenir espaces et parenthèses.
    brut = open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace").read()
    return [brut[brut.index("(") + 1:brut.rindex(")")], *brut[brut.rindex(")") + 2:].split()]


def _processus_linux() -> list[Processus]:
    """INV-VIGIE-1 : diagnostic sous Linux par `/proc` (incident du 18/11 : « indisponible »)."""
    try:
        btime = next(float(l.split()[1]) for l in open("/proc/stat", encoding="utf-8")
                     if l.startswith("btime"))
        tic = os.sysconf("SC_CLK_TCK")
        pids = [d for d in os.listdir("/proc") if d.isdigit()]
    except (OSError, StopIteration, ValueError):
        return []
    out = []
    for pid in pids:
        try:
            f = _stat(pid)
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ")
            out.append(Processus(int(pid), int(f[2]), f[0], cmd.decode("utf-8", "replace").strip(),
                                 btime + int(f[20]) / tic))
        except (OSError, ValueError, IndexError):
            continue  # processus disparu entre la liste et la lecture
    return out


def temps_cpu(pids: list[int]) -> float:
    """Temps processeur cumulé de `pids` (secondes) ; `/proc` sous Linux."""
    if WINDOWS or not os.path.isdir("/proc"):
        return poste_ram.temps_cpu(pids)
    total = 0
    for pid in pids:
        try:
            f = _stat(str(pid))
            total += int(f[12]) + int(f[13])
        except (OSError, ValueError, IndexError):
            continue
    return total / os.sysconf("SC_CLK_TCK")


def processus() -> list[Processus]:
    """Tous les processus du poste (Windows, Linux) ; [] ailleurs ou si la sonde échoue."""
    if not WINDOWS:
        return _processus_linux() if os.path.isdir("/proc") else []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS],
                           capture_output=True, timeout=30, creationflags=0x08000000)
        brut = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    brut = brut if isinstance(brut, list) else [brut]
    return [Processus(int(x.get("p") or 0), int(x.get("q") or 0), str(x.get("n") or ""),
                      str(x.get("c") or ""), float(x.get("d") or 0)) for x in brut if isinstance(x, dict)]


def descendants(racine: int, procs: list[Processus]) -> list[Processus]:
    """Descendants de `racine`, du plus proche au plus lointain. Un « enfant » né avant son parent
    porte un identifiant recyclé : il est écarté."""
    par_pid = {p.pid: p for p in procs}
    enfants: dict[int, list[Processus]] = {}
    for p in procs:
        enfants.setdefault(p.parent, []).append(p)
    sortie, pile, vus = [], [racine], {racine}
    while pile:
        parent = par_pid.get(pid := pile.pop(0))
        for e in enfants.get(pid, []):
            if e.pid in vus or (parent and parent.debut and e.debut and e.debut < parent.debut - 1):
                continue
            vus.add(e.pid)
            sortie.append(e)
            pile.append(e.pid)
    return sortie


def _duree(s: float) -> str:
    return f"{int(s)} s" if s < 60 else f"{int(s // 60)} min"


def resume_commande(commande: str, nom: str = "") -> str:
    """« "C:\\…\\chrome.exe" --headless … » -> « chrome --headless … » (80 caractères d'arguments)."""
    c = commande.strip()
    if c.startswith('"'):
        exe, _, reste = c[1:].partition('"')
    else:
        exe, _, reste = c.partition(" ")
    base = re.split(r"[\\/]", exe or nom)[-1]
    base = re.sub(r"\.exe$", "", base, flags=re.I) or nom
    reste = " ".join(reste.split())
    return f"{base} {reste[:80]}{'…' if len(reste) > 80 else ''}".strip()


def _vue(p: Processus, maintenant: float) -> dict:
    return {"pid": p.pid, "nom": p.nom, "commande": p.commande[:300],
            "duree_s": int(maintenant - p.debut) if p.debut else None,
            "hook": bool(HOOK.search(p.commande))}


def analyser(racine_debut: float, desc: list[Processus], cpu_pct: float | None,
             maintenant: float) -> dict:
    """Phrase de diagnostic : un hook d'abord, sinon la plus ancienne commande hors plomberie de
    session (la tête de la chaîne : le script plutôt que ce qu'il lance), sinon le modèle."""
    candidats = [p for p in desc if p.nom.lower() not in IGNORES
                 and not (racine_debut and p.debut and p.debut - racine_debut < PLOMBERIE_S)]
    hooks = [p for p in candidats if HOOK.search(p.commande)]
    bloquant = min(hooks or candidats, key=lambda p: p.debut or maintenant, default=None)
    if bloquant is None:
        if cpu_pct is not None and cpu_pct >= CPU_ACTIF_PCT:
            phrase = langues.t("serveur.diagnostic.calcule", pct=f"{cpu_pct:.0f}")
        else:
            phrase = langues.t("serveur.diagnostic.attente_modele")
    else:
        duree = _duree(maintenant - bloquant.debut) if bloquant.debut else ""
        if hooks:
            script = SCRIPT.search(bloquant.commande)
            nom = script[1] if script else resume_commande(bloquant.commande, bloquant.nom)
            phrase = langues.t("serveur.diagnostic.controle_duree", nom=nom, duree=duree) if duree \
                else langues.t("serveur.diagnostic.controle", nom=nom)
        else:
            nom = resume_commande(bloquant.commande, bloquant.nom)
            phrase = langues.t("serveur.diagnostic.commande_duree", nom=nom, duree=duree) if duree \
                else langues.t("serveur.diagnostic.commande", nom=nom)
    return {"disponible": True, "phrase": phrase,
            "cpu_pct": None if cpu_pct is None else round(cpu_pct, 1),
            "bloquant": _vue(bloquant, maintenant) if bloquant else None,
            "enfants": [_vue(p, maintenant) for p in desc if p.nom.lower() not in IGNORES][:20],
            "date": dt.datetime.now().isoformat(timespec="seconds")}


def neutre() -> dict:
    return {"disponible": False, "phrase": langues.t("serveur.diagnostic.indisponible"),
            "cpu_pct": None, "bloquant": None, "enfants": []}


def diagnostiquer(racine: int | None, fenetre_s: float = 2.0) -> dict:
    """Bloquant (sonde système et fenêtre de mesure) : à appeler hors de la boucle asyncio."""
    procs = processus() if racine else []
    soi = next((p for p in procs if p.pid == racine), None)
    if soi is None:
        return {**neutre(), "date": dt.datetime.now().isoformat(timespec="seconds")}
    desc = descendants(racine, procs)
    pids = [racine] + [p.pid for p in desc]
    avant = temps_cpu(pids)
    time.sleep(fenetre_s)
    cpu = 100.0 * (temps_cpu(pids) - avant) / fenetre_s
    return analyser(soi.debut, desc, cpu, time.time())


def arreter(pid: int) -> bool:
    """Arrête un processus et ses descendants (geste humain, INV-VIGIE-1)."""
    try:
        if WINDOWS:
            return subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                                  timeout=30, creationflags=0x08000000).returncode == 0
        os.kill(pid, signal.SIGKILL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
