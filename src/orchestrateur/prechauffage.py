"""Préchauffage du premier écran : index du vault, arbre, état global ET premières lectures lentes des routes du premier chargement.

Rôle : à froid, la première lecture de l'index coûtait 3,5 s ; mesuré le 26/11 sur le vrai vault, le reste du premier chargement
venait de routes jamais chauffées : catalogue des moteurs (découverte des modèles, 2,1 s), contrôle de mise à jour (`git fetch`, 0,9 s),
arbre tel que servi (0,55 s). `chauffer_tout` les exécute avant d'accepter une requête, chacune bornée dans le temps.
Frontières : lecture seule, aucune écriture ; une erreur ou un délai n'empêche jamais le démarrage (journal, puis on continue).
Invariant porté : INV-FROID-1.
"""

import asyncio
import logging
import time

from . import etat_main

log = logging.getLogger(__name__)


def chauffer(moteur) -> None:
    """INV-FROID-1 : remplit les caches (méta des fiches, états) que lit le premier chargement de l'interface."""
    try:
        taches = moteur.vault.index()[0]
        etat_main.annoter(moteur, moteur.vault.arbre(False, moteur.etat_de))
        moteur.etat_global()
        log.info("préchauffage : %d tâches lues", len(taches))
    except Exception:  # noqa: BLE001 — le préchauffage ne doit jamais empêcher le démarrage
        log.exception("préchauffage ignoré")


DELAI_S = 8  # une lecture lente (réseau, processus externe) ne retarde jamais le démarrage au-delà


async def chauffer_tout(moteur, *lectures) -> None:
    """INV-FROID-1 : `chauffer`, puis les `lectures` (fonctions sans argument rendant un awaitable) en parallèle, chacune bornée à `DELAI_S`."""
    t0 = time.perf_counter()
    await asyncio.to_thread(chauffer, moteur)

    async def une(lecture) -> None:
        try:
            await asyncio.wait_for(lecture(), DELAI_S)
        except Exception:  # noqa: BLE001 — délai, réseau, outil absent : le premier écran les relira, rien n'empêche le démarrage
            log.warning("préchauffage : %s ignoré", getattr(lecture, "__qualname__", lecture), exc_info=True)

    await asyncio.gather(*(une(x) for x in lectures))
    log.info("préchauffage terminé en %.2f s", time.perf_counter() - t0)
