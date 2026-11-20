"""Agents simultanés : créneaux de tours (nombre fixe, optimisation, plafond de RAM) et pauses.

Rôle : remplace le sémaphore du moteur. `Creneaux` décide si un tour peut démarrer selon
`[simultanes] mode` ; en modes `optimiser` et `plafond`, une veille mesure le poste toutes les
`intervalle_s` secondes, met en pause le tour le moins prioritaire quand la RAM dépasse le seuil
(suspension de son arbre de processus, mémoire de travail vidée) et reprend les pauses en
ordre inverse quand la RAM redevient disponible.
Frontières : aucun appel système direct (tout passe par `poste_ram`) ; aucune écriture vault ;
le repli (suspension impossible) arrête le tour et le remet en file par `reprise`.
Invariants portés : INV-SIMULT-1 (une pause ne perd aucun travail ; tant qu'une pause dure ou
que le seuil est dépassé, aucun tour en file ne démarre), INV-ALIGN-2 (`bloquer` : aucun tour
ne démarre pendant une opération exclusive), INV-ORDO-2 (un créneau libre va au tour en tête du
classement ; la pause frappe d'abord le moins prioritaire), INV-TRAVAUX-2 (pause à la main : hors
régulation, levée seulement à la main ou par la fin du tour).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import asdict, dataclass

from . import langues, ordonnancement, poste_ram, reprise
from .propositions import maintenant
from .vault import Conflit

log = logging.getLogger(__name__)
GO = 1024 ** 3
MOTIF_REPLI = "mis en pause pour libérer la RAM, la suspension ayant échoué"


@dataclass
class Pause:
    tache: str
    tour: object
    pids: list[int]
    memoire: int  # mémoire de travail avant la pause (octets) : ce que la reprise rendra
    depuis: str


def pid_de(harnais) -> int | None:
    """Processus racine du tour (adaptateurs Claude : `_proc` ; les autres : `_p.proc`)."""
    proc = getattr(harnais, "_proc", None) or getattr(getattr(harnais, "_p", None), "proc", None)
    return proc.pid if proc is not None and getattr(proc, "returncode", None) is None else None


class Creneaux:
    def __init__(self, moteur, poste=poste_ram):
        self.m, self.poste = moteur, poste
        self.pris = 0
        self.bloque = False
        self.gele = False  # INV-MAJ-3
        self.pauses: dict[str, Pause] = {}  # clé du tour ; ordre d'insertion = ordre des pauses
        self.manuelles: dict[str, Pause] = {}  # INV-TRAVAUX-2 : tâche -> pause demandée à la main
        self.mesure: poste_ram.Mesure | None = None
        self.demarres = 0  # démarrages depuis la dernière mesure (un seul par mesure en régulé)
        self._evt: asyncio.Event | None = None
        self._veille: asyncio.Task | None = None
        self.attente: dict[int, tuple[str | None, object]] = {}  # numéro d'arrivée -> (tâche, envoi)
        self._numeros = itertools.count()

    @property
    def cfg(self):
        return self.m.config.simultanes

    # --- décision ------------------------------------------------------------------------
    def regule(self) -> bool:
        return self.cfg.mode != "fixe" and self.mesure is not None

    def limite(self) -> int:
        return self.cfg.garde_max if self.regule() else max(1, self.m.config.moteur.simultanes_max)

    def seuil(self, m: poste_ram.Mesure) -> int:
        """RAM occupée à ne pas dépasser (octets)."""
        if self.cfg.mode == "optimiser":
            return int(m.total * (1 - self.cfg.marge_pct / 100))
        return int(self.cfg.plafond * GO if self.cfg.unite == "go" else m.total * self.cfg.plafond / 100)

    def depasse(self, m: poste_ram.Mesure, en_plus: int = 0) -> bool:
        return m.occupee + en_plus > self.seuil(m)

    def peut_demarrer(self) -> bool:
        if self.bloque or self.gele or self.pris >= self.limite():
            return False
        if not self.regule():
            return True
        # INV-SIMULT-1 : la file attend tant qu'une pause dure ou que le seuil est dépassé ; un
        # seul démarrage par mesure, pour que la RAM du nouveau tour soit vue avant le suivant.
        return not (self.pauses or self.demarres or self.depasse(self.mesure)
                    or (self.cfg.mode == "optimiser" and self.mesure.cpu >= self.cfg.cpu_max_pct))

    # --- sémaphore -----------------------------------------------------------------------
    def _demarrer_veille(self) -> asyncio.Event:
        if self._evt is None:
            self._evt = asyncio.Event()
        if self.cfg.mode != "fixe" and (self._veille is None or self._veille.done()):
            if self.mesure is None:
                self.mesure = self.poste.mesurer()
            self._veille = asyncio.get_running_loop().create_task(self._veiller())
        return self._evt

    def veiller_maintenant(self) -> None:
        """Après un changement de réglage : mesure, pause ou reprise, et veille (re)lancée."""
        self.veiller_une_fois()
        self._demarrer_veille()

    def reveiller(self) -> None:
        if self._evt is not None:
            self._evt.set()

    # --- ordre d'attente (INV-ORDO-2) --------------------------------------------------------
    def _classement(self) -> list[tuple[ordonnancement.Candidat, str]]:
        candidats = [ordonnancement.Candidat(i, ordonnancement.humain(e), n)
                     for n, (i, e) in list(self.attente.items())]
        try:
            return ordonnancement.classer(self.m.vault, candidats)
        except Exception:  # INV-EXEC-6 : un vault illisible ne fige pas la file (ordre d'arrivée)
            log.exception("classement de la file")
            return [(c, langues.t("serveur.simultanes.ordre_arrivee")) for c in sorted(candidats, key=lambda c: c.numero)]

    def _en_tete(self, numero: int) -> bool:
        if len(self.attente) == 1:
            return True
        return self._classement()[0][0].numero == numero

    def rangs(self) -> dict[str, tuple[int, str]]:
        """Rang (1 = prochain) et motif de chaque tâche qui attend un créneau."""
        sortie: dict[str, tuple[int, str]] = {}
        for rang, (c, motif) in enumerate(self._classement() if self.attente else [], 1):
            if c.ident and c.ident not in sortie:
                sortie[c.ident] = (rang, motif)
        return sortie

    def pour(self, ident: str | None, envoi=None) -> "_Place":
        return _Place(self, ident, envoi)

    async def acquire(self, ident: str | None = None, envoi=None) -> None:
        evt = self._demarrer_veille()
        numero = next(self._numeros)
        self.attente[numero] = (ident, envoi)
        try:
            while not (self.peut_demarrer() and self._en_tete(numero)):
                evt.clear()
                await evt.wait()
        except BaseException:
            self.attente.pop(numero, None)
            self.reveiller()  # une tête de file arrêtée laisse sa place au suivant
            raise
        self.attente.pop(numero, None)
        self.pris += 1
        self.demarres += self.regule()
        self.reveiller()  # le suivant au classement réexamine sa place (créneaux encore libres)

    def release(self) -> None:
        self.pris -= 1
        self._purger()  # une pause dont le tour a fini ne retient plus la file (revue du 15/11)
        self.reveiller()

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, *_):
        self.release()

    def geler(self) -> None:
        """INV-MAJ-3 : mise à jour automatique en préparation ; distinct de `bloque` (INV-ALIGN-2) pour que
        la fin d'un déplacement de dossiers ne lève pas ce gel."""
        self.gele = True

    def degeler(self) -> None:
        self.gele = False
        self.reveiller()

    def bloquer(self) -> None:
        self.bloque = True

    def debloquer(self) -> None:
        self.bloque = False
        self.reveiller()

    # --- veille --------------------------------------------------------------------------
    async def _veiller(self) -> None:
        # En mode fixe la veille s'éteint une fois les pauses levées (aucune tâche de fond inutile).
        while not self.m.ferme and (self.cfg.mode != "fixe" or self.pauses):
            await asyncio.sleep(self.cfg.intervalle_s)
            try:
                self.veiller_une_fois()
            except Exception:  # INV-EXEC-6 : la veille ne meurt pas en silence
                log.exception("veille des agents simultanés")

    def veiller_une_fois(self) -> None:
        self.mesure, self.demarres = self.poste.mesurer(), 0
        self._purger()
        if not self.regule():
            for cle in reversed(list(self.pauses)):
                self.reprendre(cle)
        elif self.depasse(self.mesure):
            self._pauser_un()
        elif self.pauses:
            cle = next(reversed(self.pauses))  # ordre inverse des pauses
            if not self.depasse(self.mesure, self.pauses[cle].memoire):
                self.reprendre(cle)
        self.reveiller()

    def _purger(self) -> None:
        for cle, p in list(self.pauses.items()):
            if self.m.tours.get(cle) is not p.tour:
                self.pauses.pop(cle)  # tour fini ou arrêté pendant sa pause
                self._publier(p.tache)

    def _pauser_un(self) -> None:
        for cle, tour in self._a_pauser():
            if (pid := pid_de(tour.harnais)) is None:
                continue
            pids = self.poste.arbre(pid)
            memoire = self.poste.memoire_travail(pids)
            if self.poste.suspendre(pids):
                self.pauses[cle] = Pause(tour.tache, tour, pids, memoire, maintenant())
                log.info("tour %s en pause (RAM) : %d Mo", cle, memoire // 2 ** 20)
                self._publier(tour.tache)
            elif tour.persona:
                self.poste.reprendre(pids)
                tour.exempt_ram = True  # une revue ne se remet pas en file : on la laisse courir
                continue
            else:
                self.poste.reprendre(pids)  # ceux que la suspension partielle a figés
                asyncio.get_running_loop().create_task(self._repli(cle, tour))
            return

    def _a_pauser(self) -> list:
        """INV-ORDO-2 : du moins prioritaire au plus prioritaire ; à rang égal, du plus récent
        (`tours` garde l'ordre des démarrages ; la date, à la seconde, ne départage pas)."""
        tours = [(c, t) for c, t in list(self.m.tours.items())
                 if c not in self.pauses and not getattr(t, "exempt_ram", False) and not t.arrete
                 and not self.en_pause_manuelle(t.tache)]
        candidats = [ordonnancement.Candidat(t.tache, ordonnancement.humain(self.m.envois.get(t.tache))
                                             and not t.persona, n) for n, (_, t) in enumerate(tours)]
        try:
            ordre = [c.numero for c, _ in reversed(ordonnancement.classer(self.m.vault, candidats))]
        except Exception:  # INV-EXEC-6 : à défaut de classement, le plus récent d'abord
            log.exception("classement des pauses")
            ordre = list(reversed(range(len(tours))))
        return [tours[n] for n in ordre]

    async def _repli(self, cle: str, tour) -> None:
        """Suspension impossible : arrêt du tour (INV-EXEC-1) puis remise en file en tête, même
        session ; la file attend que la RAM le permette."""
        tour.arrete = True
        log.warning("tour %s arrêté et remis en file (suspension impossible)", cle)
        await asyncio.shield(tour.harnais.arreter())
        for _ in range(600):
            boucle = self.m.boucles.get(tour.tache)
            if self.m.tours.get(cle) is not tour and (boucle is None or boucle.done()):
                break
            await asyncio.sleep(0.05)
        try:
            reprise._resoumettre(self.m, tour.tache, MOTIF_REPLI, auto=False)
            self.m.files[tour.tache].rotate(1)  # le tour repris passe avant les messages en file
        except Exception as e:
            log.warning("remise en file de %s impossible : %s", tour.tache, e)

    def reprendre(self, cle: str, force: bool = False) -> bool:
        """Reprend un tour en pause ; `force` (« Reprendre maintenant ») l'exempte de toute
        nouvelle pause jusqu'à sa fin."""
        p = self.pauses.get(cle)
        if p is None:
            return False
        if not self.poste.reprendre(p.pids):
            log.warning("reprise incomplète du tour %s : nouvel essai à la mesure suivante", cle)
            return False  # la pause reste suivie : aucun processus laissé figé sans retour
        self.pauses.pop(cle)
        if force:
            p.tour.exempt_ram = True
        self._publier(p.tache)
        self.reveiller()
        return True

    def en_pause(self, tache: str) -> bool:
        return any(p.tache == tache for p in self.pauses.values()) or self.en_pause_manuelle(tache)

    # --- pause à la main (INV-TRAVAUX-2) -----------------------------------------------------
    def en_pause_manuelle(self, tache: str) -> bool:
        p = self.manuelles.get(tache)
        if p is not None and self.m.tours.get(tache) is not p.tour:
            self.manuelles.pop(tache)  # tour fini ou arrêté pendant la pause
            return False
        return p is not None

    def pauser_main(self, tache: str) -> None:
        """Suspend l'arbre de processus du tour de la tâche ; la régulation n'y touche plus."""
        tour = self.m.tours.get(tache)
        if tour is None or tour.arrete:
            raise Conflit(langues.t("serveur.simultanes.pas_de_seance"))
        if self.en_pause(tache):
            raise Conflit(langues.t("serveur.simultanes.deja_en_pause"))
        if (pid := pid_de(tour.harnais)) is None:
            raise Conflit(langues.t("serveur.simultanes.programme_introuvable"))
        pids = self.poste.arbre(pid)
        if not self.poste.figer(pids):
            raise Conflit(langues.t("serveur.simultanes.pause_impossible"))
        self.manuelles[tache] = Pause(tache, tour, pids, 0, maintenant())
        log.info("tour %s mis en pause à la main", tache)
        self._publier(tache)

    def reprendre_main(self, tache: str) -> None:
        if not self.en_pause_manuelle(tache):
            raise Conflit(langues.t("serveur.simultanes.pas_en_pause"))
        if not self.poste.degeler(self.manuelles[tache].pids):
            raise Conflit(langues.t("serveur.simultanes.reprise_echouee"))
        self.manuelles.pop(tache)
        self._publier(tache)

    def _publier(self, tache: str) -> None:
        self.m.publier("pause_ram", tache=tache, pause=self.en_pause(tache))
        self.m.publier("arbre")

    def public(self) -> dict:
        m = self.mesure or self.poste.mesurer()
        return {**asdict(self.cfg), "simultanes_max": self.m.config.moteur.simultanes_max,
                "mesure_disponible": m is not None,
                "ram": {"total": m.total, "occupee": m.occupee, "cpu": round(m.cpu, 1),
                        "seuil": self.seuil(m) if self.cfg.mode != "fixe" else None} if m else None,
                "actifs": self.pris, "limite": self.limite(),
                "pauses": [{"tache": p.tache, "depuis": p.depuis, "memoire": p.memoire}
                           for p in self.pauses.values()]}


class _Place:
    """`async with creneaux.pour(tache, envoi)` : créneau pris à son rang (INV-ORDO-2)."""

    def __init__(self, creneaux: Creneaux, ident: str | None, envoi):
        self.c, self.ident, self.envoi = creneaux, ident, envoi

    async def __aenter__(self):
        await self.c.acquire(self.ident, self.envoi)

    async def __aexit__(self, *_):
        self.c.release()
