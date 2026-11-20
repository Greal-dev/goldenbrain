"""Instrumentation : attentes d'un départ et mémoire d'un tour, consignées dans `mesures.jsonl`.

Rôle : donner la trace qui manquait pour expliquer une lenteur ou un gel — durée passée en file,
à attendre un prérequis, le poste ou le réseau avant qu'un tour parte ; mémoire résidente du fils
du harnais et nombre de ses petits-fils en fin de tour ; mesure de contexte bornée à la fenêtre.
Frontières : lit seulement `/proc` (POSIX ; silencieux ailleurs) ; n'écrit que dans le journal de
mesure, hors vault, sans aucun contenu de conversation ; ne lance ni n'arrête rien.
Invariants portés : INV-COMPACT-1 (journal de mesure ; les lignes à `type` ne comptent pas dans la
synthèse), INV-POSTE-1 et INV-ORDO-1 (attentes mesurées sans changer l'ordre ni le créneau),
INV-RESEAU-2 (durée de gel).
"""

from __future__ import annotations

import os
import time
from pathlib import Path


def horloge() -> float:
    """Horloge monotone des attentes (substituable par les tests)."""
    return time.monotonic()


def pid_de(harnais) -> int | None:
    """Pid du fils vivant d'un adaptateur local (`_proc` chez Claude, `_p.proc` chez les autres)."""
    proc = getattr(harnais, "_proc", None) or getattr(getattr(harnais, "_p", None), "proc", None)
    pid = getattr(proc, "pid", None)
    return pid if isinstance(pid, int) and pid > 0 else None


def _lire(pid: int, champ: str, racine: str) -> str:
    try:
        for ligne in Path(racine, str(pid), "status").read_text(encoding="utf-8", errors="replace").splitlines():
            if ligne.startswith(champ + ":"):
                return ligne.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def echantillon(harnais, racine: str = "/proc") -> dict:
    """{rss_ko, petits_fils} du fils du harnais ; {} hors Linux, sans pid ou processus disparu.
    Petits-fils : tous les descendants du fils au-delà de ses enfants directs."""
    pid = pid_de(harnais)
    if pid is None or not os.path.isdir(racine):
        return {}
    rss = _lire(pid, "VmRSS", racine).split()
    if not rss or not rss[0].isdigit():
        return {}
    parents: dict[int, list[int]] = {}
    try:
        noms = [n for n in os.listdir(racine) if n.isdigit()]
    except OSError:
        return {"rss_ko": int(rss[0])}
    for n in noms:
        pp = _lire(int(n), "PPid", racine)
        if pp.isdigit():
            parents.setdefault(int(pp), []).append(int(n))
    descendants, front = 0, list(parents.get(pid, []))
    while front:
        front = [p for f in front for p in parents.get(f, [])]
        descendants += len(front)
    return {"rss_ko": int(rss[0]), "petits_fils": descendants}


def borner_contexte(contexte, fenetre) -> int | None:
    """Un contexte supérieur à la fenêtre est faux (cumul des appels d'un tour chez certains harnais) :
    mieux vaut `None` qu'une valeur qui fausse la tranche et le déclenchement du compactage."""
    if not isinstance(contexte, int) or isinstance(contexte, bool) or contexte < 0:
        return None
    return None if isinstance(fenetre, int) and fenetre > 0 and contexte > fenetre else contexte
