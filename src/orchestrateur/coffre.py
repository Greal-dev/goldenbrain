"""Secrets du poste : lus dans une variable d'environnement ou un fichier du dossier de données.

Rôle : `lire(variable, fichier)` rend le secret (vide s'il manque) ; `proteger(texte, fichier)` l'écrit :
chiffré par DPAPI (portée de l'utilisateur, ctypes) sous Windows, sinon fichier aux droits 0600.
Frontières : ne journalise ni n'affiche jamais un secret ; la variable d'environnement garde la priorité.
Invariants portés : INV-TELEGRAM-2 (un secret n'est jamais écrit en clair dans le dépôt ni journalisé).
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"


class _Blob(ctypes.Structure):
    _fields_ = [("taille", ctypes.c_uint32), ("donnees", ctypes.POINTER(ctypes.c_char))]


def _dpapi(donnees: bytes, chiffrer: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    tampon = ctypes.create_string_buffer(donnees, len(donnees))
    entree, sortie = _Blob(len(donnees), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), _Blob()
    fonction = crypt32.CryptProtectData if chiffrer else crypt32.CryptUnprotectData
    # 0x1 = CRYPTPROTECT_UI_FORBIDDEN : jamais de boîte de dialogue dans un serveur.
    if not fonction(ctypes.byref(entree), None, None, None, None, 0x1, ctypes.byref(sortie)):
        raise OSError("DPAPI : opération refusée")
    try:
        return ctypes.string_at(sortie.donnees, sortie.taille)
    finally:
        kernel32.LocalFree(sortie.donnees)


def lire(variable: str, fichier: Path | None) -> tuple[str, str]:
    """(secret, source) ; source = "variable" | "fichier" | "" (absent ou illisible)."""
    if variable and (valeur := os.environ.get(variable, "").strip()):
        return valeur, "variable"
    if fichier and fichier.is_file():
        try:
            brut = fichier.read_bytes()
            return (_dpapi(brut, False) if WINDOWS else brut).decode("utf-8").strip(), "fichier"
        except (OSError, UnicodeDecodeError):
            return "", ""  # fichier d'un autre utilisateur ou corrompu : comme absent
    return "", ""


def proteger(texte: str, fichier: Path) -> None:
    """Écrit le secret (DPAPI sous Windows, sinon 0600) ; vide = efface le fichier (INV-TELEGRAM-2)."""
    if not texte.strip():
        fichier.unlink(missing_ok=True)
        return
    fichier.parent.mkdir(parents=True, exist_ok=True)
    tmp = fichier.with_name(fichier.name + ".tmp")
    octets = texte.strip().encode("utf-8")
    if WINDOWS:
        tmp.write_bytes(_dpapi(octets, True))
    else:
        # Droits 0600 dès la création : jamais lisible par un autre utilisateur, même un instant.
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(octets)
    os.replace(tmp, fichier)
