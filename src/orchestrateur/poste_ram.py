"""Mesure de la mémoire et du processeur du poste ; suspension et reprise d'un arbre de processus.

Rôle : seule frontière avec le système d'exploitation pour la régulation des agents simultanés
(INV-SIMULT-1). Windows : API Win32 par ctypes (GlobalMemoryStatusEx, GetSystemTimes,
CreateToolhelp32Snapshot, NtSuspendProcess / NtResumeProcess, K32EmptyWorkingSet,
K32GetProcessMemoryInfo, GetProcessTimes). Ailleurs : RAM par `/proc/meminfo`, suspension non prise en charge
(l'appelant se replie sur l'arrêt du tour et sa remise en file).
Frontières : aucune décision (quand suspendre, qui) ; aucune dépendance nouvelle (pas de psutil).
Pause demandée à la main (tableau « En cours ») : `figer` / `degeler`, partout (Windows : même API
de suspension ; ailleurs : SIGSTOP / SIGCONT au groupe de processus du tour, lancé en session propre).
Invariants portés : INV-SIMULT-1 (une suspension ne tue rien ; elle échoue en rendant False),
INV-TRAVAUX-2 (le gel ne vise jamais le groupe du serveur).
"""

from __future__ import annotations

import ctypes
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

WINDOWS = sys.platform == "win32"


@dataclass
class Mesure:
    total: int        # octets
    libre: int        # octets disponibles
    cpu: float = 0.0  # occupation du processeur depuis la mesure précédente, en %

    @property
    def occupee(self) -> int:
        return self.total - self.libre


if WINDOWS:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")

    class _MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64)]

    class _PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32)]
    _k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32)]
    _k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMSTAT)]
    _k32.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
    _k32.K32EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    _k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _DROITS = 0x0800 | 0x0400 | 0x0100 | 0x0010  # SUSPEND_RESUME, QUERY_INFORMATION, SET_QUOTA, VM_READ
    _INVALIDE = wintypes.HANDLE(-1).value

_cpu_prec: tuple[int, int] | None = None


def _cpu_windows() -> float:
    global _cpu_prec
    inactif, noyau, util = (wintypes.FILETIME() for _ in range(3))
    if not _k32.GetSystemTimes(ctypes.byref(inactif), ctypes.byref(noyau), ctypes.byref(util)):
        return 0.0
    val = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
    total, repos = val(noyau) + val(util), val(inactif)  # le temps noyau inclut le temps inactif
    prec, _cpu_prec = _cpu_prec, (total, repos)
    if not prec or total <= prec[0]:
        return 0.0
    return max(0.0, 100.0 * (1 - (repos - prec[1]) / (total - prec[0])))


def mesurer() -> Mesure | None:
    """RAM du poste (et processeur sous Windows) ; None si le système ne la donne pas."""
    if WINDOWS:
        m = _MEMSTAT(dwLength=ctypes.sizeof(_MEMSTAT))
        if not _k32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return None
        return Mesure(m.ullTotalPhys, m.ullAvailPhys, _cpu_windows())
    try:
        champs = dict(ligne.split(":", 1) for ligne in
                      Path("/proc/meminfo").read_text(encoding="utf-8").splitlines() if ":" in ligne)
        ko = lambda c: int(champs[c].split()[0]) * 1024  # noqa: E731
        return Mesure(ko("MemTotal"), ko("MemAvailable"))
    except (OSError, KeyError, ValueError):
        return None


def arbre(racine: int) -> list[int]:
    """La racine et tous ses descendants (Windows) ; [racine] ailleurs."""
    if not WINDOWS:
        return [racine]
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap == _INVALIDE:
        return [racine]
    enfants: dict[int, list[int]] = {}
    try:
        e = _PROCESSENTRY32(dwSize=ctypes.sizeof(_PROCESSENTRY32))
        ok = _k32.Process32First(snap, ctypes.byref(e))
        while ok:
            enfants.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            ok = _k32.Process32Next(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    vus, pile = [], [racine]
    while pile:
        p = pile.pop()
        if p not in vus:
            vus.append(p)
            pile.extend(enfants.get(p, []))
    return vus


def _sur_chacun(pids: list[int], geste) -> bool:
    ok = bool(pids)
    for pid in pids:
        h = _k32.OpenProcess(_DROITS, False, pid)
        if not h:
            # Processus sorti entre l'instantané et le geste (un outil terminé) : rien à figer.
            ok = ok and ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER
            continue
        try:
            ok = geste(h) and ok
        finally:
            _k32.CloseHandle(h)
    return ok


def suspendre(pids: list[int]) -> bool:
    """INV-SIMULT-1 : suspend sans tuer, puis vide la mémoire de travail (déchargée sur disque
    par le système). False si un processus n'a pu être suspendu (l'appelant reprend les autres)."""
    if not WINDOWS:
        return False
    ok = _sur_chacun(pids, lambda h: _ntdll.NtSuspendProcess(h) == 0)
    if ok:
        _sur_chacun(pids, lambda h: bool(_k32.K32EmptyWorkingSet(h)))
    return ok


def reprendre(pids: list[int]) -> bool:
    if not WINDOWS:
        return False
    return _sur_chacun(pids, lambda h: _ntdll.NtResumeProcess(h) == 0)


def _groupe(pids: list[int], sig) -> bool:
    try:
        groupe = os.getpgid(pids[0])
        if groupe == os.getpgrp():  # INV-TRAVAUX-2 : jamais notre propre groupe
            return False
        os.killpg(groupe, sig)
        return True
    except (OSError, IndexError):
        return False


def figer(pids: list[int]) -> bool:
    """Pause à la main : l'arbre du tour est suspendu sans rien tuer ; False si impossible."""
    return suspendre(pids) if WINDOWS else _groupe(pids, signal.SIGSTOP)


def degeler(pids: list[int]) -> bool:
    return reprendre(pids) if WINDOWS else _groupe(pids, signal.SIGCONT)


def memoire_travail(pids: list[int]) -> int:
    """Somme des mémoires de travail (octets) ; 0 hors Windows."""
    if not WINDOWS:
        return 0
    total = 0

    def lire(h) -> bool:
        nonlocal total
        pmc = _PMC(cb=ctypes.sizeof(_PMC))
        if _k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            total += pmc.WorkingSetSize
        return True
    _sur_chacun(pids, lire)
    return total


def temps_cpu(pids: list[int]) -> float:
    """Temps processeur cumulé (noyau + utilisateur, secondes) ; 0 hors Windows. Deux lectures
    espacées donnent l'activité de l'arbre (diagnostic d'un tour silencieux, INV-VIGIE-1)."""
    if not WINDOWS:
        return 0.0
    total = 0

    def lire(h) -> bool:
        nonlocal total
        f = [wintypes.FILETIME() for _ in range(4)]
        if _k32.GetProcessTimes(h, *(ctypes.byref(x) for x in f)):
            total += sum((x.dwHighDateTime << 32) | x.dwLowDateTime for x in f[2:])
        return True
    _sur_chacun(pids, lire)
    return total / 1e7
