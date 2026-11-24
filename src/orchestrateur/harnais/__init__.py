"""Protocole d'un harnais et registre des adaptateurs.

Rôle : contrat commun (événements de tour, éléments de transcript) et fabrique `HARNAIS[nom](conf)`,
où `conf` est la section `[harnais.<nom>]` de la configuration.
Frontières : aucune logique de tour, aucune E/S vault.
Invariants portés : aucun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Protocol


@dataclass
class Evenement:
    type: str            # "session" | "texte" | "outil" | "suivi" | "fin" | "erreur"
    session: str = ""
    texte: str = ""
    brut: dict | None = None
    # Événement `fin` : {"contexte": jetons du dernier appel, "cout": dollars|None}, quand le harnais le dit.
    mesure: dict | None = None
    # Événement `suivi` (INV-TRAVAUX-1) : {"sous_agent": {"id", "description", "genre", "fin", "erreur"}}
    # ou {"avancement": {"fait", "total"}}, quand le flux du harnais le dit.
    suivi: dict | None = None


@dataclass
class Message:
    role: str            # "utilisateur" | "assistant"
    texte: str
    outils: list[str] = field(default_factory=list)
    horodatage: str = ""
    # Message de l'agent en réponse à un hook de fin de session, après sa vraie réponse :
    # l'interface le range parmi les étapes, jamais comme réponse finale.
    secondaire: bool = False
    # Message du système : « echec » (tour échoué), « remontee » (compte rendu d'une descendante), « regroupe ». Vide sinon.
    genre: str = ""


class Harnais(Protocol):
    nom: str
    # Faux : le moteur place la consigne en tête du PREMIER message de la conversation.
    consigne_native: bool
    # Faux : la dérivation avec fil est refusée (409).
    sait_deriver: bool

    def lancer(self, message: str, *, session: str | None, deriver: bool,
               consigne: str, env: dict[str, str],
               modele: str = "") -> AsyncIterator[Evenement]: ...

    async def arreter(self) -> None: ...

    # Peut lever NotImplementedError : la conversation est alors relue dans les journaux.
    def transcript(self, session: str, limite: int) -> list[Message]: ...

    def commande_terminal(self, session: str) -> str: ...

    # Compactage (INV-COMPACT-1) : `compactage_natif` vrai = le harnais sait se compacter seul ; le
    # moteur pose `compactage = (pct, jetons)` avant `lancer`, l'adaptateur le traduit en son option.
    # `ordre_compactage` : ordre à envoyer en tour pour compacter (repli commun), "" = aucun.
    compactage_natif: bool
    compactage: tuple[float, int] | None
    ordre_compactage: str

    # Facultatifs : `chemin_transcript(session) -> str` (préambule de reprise),
    # `decouvrir_modeles() -> list[str]` (modeles = "auto"), `analyser(brut, etat)` (relecture
    # des journaux).


from .claude import HarnaisClaude  # noqa: E402  (le module importe Evenement/Message ci-dessus)
from .codex import HarnaisCodex  # noqa: E402
from .opencode import HarnaisOpencode  # noqa: E402
from .agy import HarnaisAgy  # noqa: E402
from .copilot import HarnaisCopilot  # noqa: E402

HARNAIS: dict[str, Callable[[dict], Harnais]] = {
    "claude": HarnaisClaude, "codex": HarnaisCodex, "opencode": HarnaisOpencode,
    "agy": HarnaisAgy, "copilot": HarnaisCopilot}
