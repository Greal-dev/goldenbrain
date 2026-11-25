"""Reprise d'office d'un tour interrompu sans geste humain : RAM, redémarrage, erreur d'API passagère.

Rôle : décider si un tour coupé par la régulation mémoire (INV-SIMULT-1), par un redémarrage du
serveur ou par une erreur d'API passagère repart de lui-même, dans sa conversation, avec la
consigne « reprends où tu en étais » ; tenir le compte des reprises d'un tour et signaler quand le
plafond est atteint ; différer la reprise après une erreur d'API ; noter l'étape (`etape`).
Frontières : aucun harnais lancé ici (tout passe par `reprise._resoumettre` donc `Moteur.soumettre`) ;
le statut de la tâche n'est touché qu'au plafond atteint ; aucune entrée dans Décisions.
Invariants portés : INV-REPRISE-1 (au plus MAX_REPRISES reprises d'office par tour, puis incident et
retour à l'humain ; un arrêt demandé par l'humain ne reprend jamais), INV-REPRISE-2 (étape notée).
"""

from __future__ import annotations

import asyncio
import logging

from . import echecs, etape, langues, reprise

log = logging.getLogger(__name__)
MAX_REPRISES = 3
DELAIS_API_S = (30.0, 120.0, 300.0)  # attente avant la 1re, 2e, 3e reprise après une erreur d'API
CAUSES_AUTO = ("ram", "serveur")  # causes d'arrêt qui ne sont pas un geste humain


class RepriseAuto:
    def __init__(self, moteur):
        self.m = moteur
        self.pendantes: dict[str, asyncio.Task | None] = {}  # tâche -> reprise différée (ou None)

    def compte(self, ident: str) -> int:
        rec = self.m.interrompus.get(ident) or self.m.actifs.get(ident) or {}
        return int(rec.get("reprises") or 0)

    def permis(self, ident: str) -> bool:
        try:
            ouverte = self.m.vault.ouverte(self.m.vault.tache(ident))
        except Exception:  # noqa: BLE001 — tâche disparue : rien à reprendre
            return False
        return ouverte and self.compte(ident) < MAX_REPRISES

    def attendue(self, ident: str) -> bool:
        """Vrai tant qu'une reprise d'office est en route (écran : « reprise automatique »)."""
        if ident in self.pendantes:
            return True
        file = [*self.m.files.get(ident, ()), *([self.m.attente[ident]] if ident in self.m.attente else [])]
        return self.m.etat_de(ident) in ("interrompu", "en_file") and any(e.reprise for e in file)

    def marquer(self, ident: str, tour) -> bool:
        """Arrêt d'un tour : note l'étape ; vrai si une reprise d'office suivra (statut inchangé)."""
        etape.noter(self.m, ident, tour.depuis)  # INV-REPRISE-2
        if tour.arret in CAUSES_AUTO and self.permis(ident):
            self.pendantes[ident] = None
            return True
        return False

    def reprendre(self, ident: str, motif: str) -> bool:
        """Resoumet d'office le tour interrompu ; faux (et signalement) au plafond atteint."""
        self.pendantes.pop(ident, None)
        if not self.permis(ident):
            self.signaler(ident, motif)
            return False
        reprise._resoumettre(self.m, ident, motif, auto=True)
        return True

    def signaler(self, ident: str, motif: str) -> None:
        """INV-REPRISE-1 : plafond atteint — un incident lisible et la tâche rendue à l'humain."""
        try:
            t = self.m.vault.tache(ident)
            if t.statut == "en-cours":
                self.m.vault.poser_statut(ident, self.m.vault.retour)
            self.m.etats[ident] = "interrompu"
            self.m.incidents.noter(ident, str(t.fm.get("harnais") or ""), motif,
                                   langues.t("serveur.reprise_auto.epuisee", n=MAX_REPRISES))
            self.m.publier("arbre")
        except Exception as e:  # noqa: BLE001
            log.warning("signalement de %s impossible : %s", ident, e)

    def api_passagere(self, ident: str, envoi, erreur: str, nom: str) -> bool:
        """Erreur d'API passagère : reprise différée (30 s, 2 min, 5 min), bornée. Vrai : prise en charge."""
        n = envoi.reprises
        if not echecs.est_passagere(erreur) or n >= MAX_REPRISES or envoi.role not in ("", "tache") \
                or ident in self.pendantes or not self.permis(ident):
            return False
        rec = {**reprise.enregistrement(ident, envoi), "reprises": n}
        self.m.interrompus[ident] = self.m.actifs[ident] = rec  # persistée : un redémarrage la reprend
        self.m._sauver_actifs()
        self.m.etats[ident] = "interrompu"
        delai = DELAIS_API_S[min(n, len(DELAIS_API_S) - 1)]
        self.m.incidents.noter(ident, nom, erreur, langues.t("serveur.reprise_auto.api_differee",
                                                              n=n + 1, max=MAX_REPRISES, delai=int(delai)))
        self.pendantes[ident] = asyncio.get_running_loop().create_task(self._apres(ident, delai))
        self.m.publier("arbre")
        return True

    async def _apres(self, ident: str, delai: float) -> None:
        try:
            await asyncio.sleep(delai)
            self.reprendre(ident, "erreur passagère de l'API")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("reprise différée de %s impossible : %s", ident, e)
            self.pendantes.pop(ident, None)

    def annuler(self, ident: str) -> None:
        """Arrêt demandé par l'humain : plus aucune reprise d'office (INV-REPRISE-1)."""
        t = self.pendantes.pop(ident, None)
        if t:
            t.cancel()
        if self.m.interrompus.pop(ident, None) is not None and ident not in self.m.tours:
            self.m.actifs.pop(ident, None)
            self.m._sauver_actifs()

    def consigne(self, ident: str) -> str:
        return etape.consigne(self.m, ident)
