"""Version du code servi : empreinte au démarrage, empreinte sur disque, redémarrage demandé.

Rôle : dire si le code Python en mémoire est celui du disque (`GET /etat`, `perime` des 404)
et porter le code de sortie d'un redémarrage demandé (`POST /redemarrer`).
Frontières : ne lit que des métadonnées de fichiers (chemin, taille, date), jamais leur contenu ;
n'arrête rien lui-même : `__main__` fournit l'arrêt normal d'uvicorn.
Invariants portés : INV-VERSION-1, INV-VERSION-2, INV-VERSION-3.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Callable

from fastapi.responses import JSONResponse

from . import langues

log = logging.getLogger(__name__)
PAQUET = Path(__file__).resolve().parent
CODE_REDEMARRAGE = 3
INTERVALLE_S = 15
SONDE_DIFFERE_S = 2
GARDE_S = 60  # INV-VERSION-2 : pas de redémarrage sans `force` avant cet âge du serveur


def empreinte(racine: Path = PAQUET) -> str:
    """INV-VERSION-1 : chemins relatifs, tailles et dates des `.py` → hachage court."""
    h = hashlib.sha256()
    for p in sorted(racine.rglob("*.py")):
        st = p.stat()
        h.update(f"{p.relative_to(racine).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:12]


class Version:
    def __init__(self, racine: Path = PAQUET, intervalle_s: float = INTERVALLE_S, garde_s: float = GARDE_S):
        self.racine, self.intervalle_s, self.garde_s = racine, intervalle_s, garde_s
        self.redemarrages = 0  # demandes acceptées depuis le lancement (INV-VERSION-2)
        self._lance = time.monotonic()
        self.demarree = self.disque = empreinte(racine)
        self.depuis = dt.datetime.now().isoformat(timespec="seconds")
        self._instant = time.monotonic()
        self.code_sortie = 0
        # Fourni par `__main__` (arrêt normal d'uvicorn, lifespan compris) ; absent en test.
        self.arreter: Callable[[], None] | None = None
        # INV-VERSION-3 : redémarrage armé « dès que les tours sont finis ». Non persisté : le processus
        # qui le porte disparaît justement en l'exécutant ; un arrêt par une autre voie a déjà rendu le service.
        self._differe: asyncio.Task | None = None
        self.sonde_differe_s = SONDE_DIFFERE_S
        self.complements: Callable[[], dict] = dict  # INV-MAJ-3 : vue de la mise à jour automatique, jointe à `etat`

    async def etat(self) -> dict:
        if time.monotonic() - self._instant >= self.intervalle_s:
            self._instant = time.monotonic()
            # `stat` de chaque module : hors de la boucle d'événements.
            self.disque = await asyncio.to_thread(empreinte, self.racine)
        return {"demarree": self.demarree, "disque": self.disque,
                "a_jour": self.disque == self.demarree, "depuis": self.depuis,
                "redemarrages": self.redemarrages, "differe": self.differe,
                "maj_auto": self.complements()}

    @property
    def differe(self) -> bool:
        return self._differe is not None and not self._differe.done()

    def armer_differe(self, occupe: Callable[[], bool]) -> None:
        """INV-VERSION-3 : redémarre le serveur (jamais la machine) dès que `occupe()` est faux."""
        if self.differe:
            return
        log.warning("redémarrage différé armé (à la fin des tours)")

        async def attendre():
            while occupe():
                await asyncio.sleep(self.sonde_differe_s)
            log.warning("redémarrage différé : plus aucun tour, le serveur redémarre")
            self.redemarrer()
        self._differe = asyncio.get_running_loop().create_task(attendre())

    def annuler_differe(self) -> None:
        if self._differe:
            self._differe.cancel()
        self._differe = None

    def age_s(self) -> float:
        return time.monotonic() - self._lance

    def tracer(self, request, corps) -> "Version":
        """INV-VERSION-2 : qui demande, quand, depuis quel âge du serveur (avant toute décision)."""
        h = request.headers
        log.warning("redémarrage demandé : par=%r agent=%r x-orchestrateur=%r client=%s force=%s à %s "
                    "(serveur lancé depuis %.0f s, %d déjà demandés)",
                    corps.par if corps else "", h.get("user-agent", ""), h.get("x-orchestrateur", ""),
                    request.client.host if request.client else "?", bool(corps and corps.force),
                    dt.datetime.now().isoformat(timespec="seconds"), self.age_s(), self.redemarrages)
        return self

    def refus_garde(self) -> str | None:
        """INV-VERSION-2 : message de refus (429) tant que le serveur est trop jeune, sinon rien."""
        reste = self.garde_s - self.age_s()
        if reste <= 0:
            return None
        return langues.t("serveur.version.trop_jeune", garde=f"{self.garde_s:.0f}", reste=f"{reste:.0f}")

    async def marquer_404(self, reponse):
        """INV-VERSION-1 : un 404 d'un serveur périmé porte `perime: true` (la route demandée
        existe peut-être dans le code du disque)."""
        if (await self.etat())["a_jour"]:
            return reponse
        corps = b"".join([x async for x in reponse.body_iterator])
        try:
            detail = json.loads(corps)
        except ValueError:
            detail = {"detail": corps.decode("utf-8", "replace")}
        return JSONResponse({**detail, "perime": True}, status_code=404)

    def redemarrer(self, delai_s: float = 0.2) -> None:
        """Pose le code de sortie 3 puis demande l'arrêt normal (jamais brutal), après un court
        délai : la réponse 202 part d'abord."""
        self.code_sortie = CODE_REDEMARRAGE
        self.redemarrages += 1
        if self.arreter:
            asyncio.get_running_loop().call_later(delai_s, self.arreter)
