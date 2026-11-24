"""Repli d'une reprise sur une session que le harnais ne connaît pas.

Rôle : un identifiant de session écrit dans la fiche sans transcript derrière lui (interface native
fermée avant le premier message, tour tué trop tôt, fiche copiée) fait refuser `--resume` /
`resume` par le harnais. Ce n'est pas un échec de raisonnement : le tour repart une seule fois en
conversation neuve, la trace est journalisée et la fiche perd l'identifiant orphelin.
Frontières : ne lance rien lui-même ; enveloppe le flux d'événements d'un harnais.
Invariants portés : INV-SESSION-1 (voir docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing

from .harnais import Evenement

# Messages exacts des harnais quand la session reprise n'existe pas (claude 2.1.x, codex, opencode,
# agy, copilot) ; la comparaison ignore la casse.
MOTIFS = re.compile(
    r"no conversation found|session[^\n]{0,40}not found|no (saved )?session[^\n]{0,40}found"
    r"|unknown session|could not find (a )?(session|conversation|thread)"
    r"|(thread|conversation)[^\n]{0,40}not found|session introuvable", re.IGNORECASE)


def session_absente(erreur: str | None) -> bool:
    """Vrai si l'erreur dit que la session reprise n'existe pas (et non qu'un raisonnement a échoué)."""
    return bool(erreur and MOTIFS.search(erreur))


async def avec_repli(lancer: Callable[..., AsyncIterator[Evenement]], neuf: Callable[[], str],
                     session: str | None, deriver: bool, **kw) -> AsyncIterator[Evenement]:
    """Flux de `lancer` ; si la reprise échoue pour session inconnue AVANT toute sortie utile, un
    événement `session_perdue` (journalisé, la fiche est nettoyée) puis un seul second lancement
    sans session, sur le texte `neuf()` (premier message d'une conversation neuve)."""
    if not session:
        async for ev in lancer(session=None, deriver=deriver, **kw):
            yield ev
        return
    perdue = False
    async with aclosing(lancer(session=session, deriver=deriver, **kw)) as flux:
        async for ev in flux:
            if ev.type == "erreur" and session_absente(ev.texte):
                perdue = True
                break
            yield ev
            if ev.type in ("texte", "outil", "fin"):  # sortie utile : plus de repli possible
                break
        else:
            return
        if not perdue:  # sortie utile vue : on suit le flux jusqu'au bout
            async for ev in flux:
                yield ev
            return
    yield Evenement("session_perdue", session=session,
                    texte=f"session {session} inconnue du harnais : repli en conversation neuve")
    kw["message"] = neuf()
    async for ev in lancer(session=None, deriver=False, **kw):
        yield ev
