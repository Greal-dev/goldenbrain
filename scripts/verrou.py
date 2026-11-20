"""Verrou d'exemplaire unique : `prendre(nom)` rend le fichier verrouillé, ou None si un autre vit.

Rôle : empêcher deux `check_ui.py` simultanés (≈ 1,4 Go en pic). Frontières : fichier sous
`tempfile.gettempdir()` ; `fcntl.flock` sous POSIX, `msvcrt.locking` sous Windows. Le verrou tombe
avec le processus (même tué) : aucun fichier périmé à nettoyer.
"""

import sys
import tempfile
from pathlib import Path


def prendre(nom: str):
    chemin = Path(tempfile.gettempdir()) / f"goldenbrain-{nom}.verrou"
    fichier = open(chemin, "a+", encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fichier.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fichier.close()
        return None
    return fichier
