"""Verrou commun des écritures de `config.toml`.

Rôle : sérialiser les lecture-modification-écriture des sections (`[telegram]`, `[interface]`,
`[simultanes]`…) menées par des routes concurrentes.
Frontières : ne connaît ni les sections ni le format ; n'écrit rien lui-même.
Invariants portés : INV-INTERFACE-2.
"""
from __future__ import annotations

import functools
import threading

# INV-INTERFACE-2 : sans verrou commun, deux écritures de sections différentes lisent le même
# état et la seconde écrase la première (section perdue).
_VERROU = threading.RLock()


def sous_verrou_config(fonction):
    @functools.wraps(fonction)
    def enveloppe(*args, **kwargs):
        with _VERROU:
            return fonction(*args, **kwargs)
    return enveloppe
