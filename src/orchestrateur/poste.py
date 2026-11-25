"""Réservation du poste pendant une porte lourde (épreuves lourdes d'un agent).

Rôle : une tâche réserve le poste (`orch poste reserver`) ; tant qu'il est réservé, le tour d'une
autre tâche marquée `epreuves: lourdes` attend en file ; la réservation est rendue d'office à la
fin du tour de son titulaire, expire après `moteur.poste_delai_min` et survit au redémarrage.
Une demande refusée inscrit la tâche dans une file ordonnée (premier arrivé) ; la file vit en
mémoire et s'entretient par les demandes répétées de l'attendant (`orch poste reserver` attend).
Frontières : ne lance ni n'arrête aucun processus ; ne sait pas ce qu'est une épreuve — la tâche
se déclare (`epreuves: lourdes`, lu dans son frontmatter) ; les tours déjà commencés ne sont jamais
interrompus. Mélangé au `Moteur` (sémaphore, files, vault, config, publier).
Invariants portés : INV-POSTE-1, INV-EXECUTANT-1 (un message en attente ne part pas sur une tâche « Moi »).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import cached_property

from . import executant, fiches, instrumentation, langues
from .propositions import lire_liste, maintenant
from .vault import Conflit, NonTrouve

log = logging.getLogger(__name__)


def porte_vivante() -> bool:
    """Vrai si une porte d'interface tourne (verrou `scripts/verrou.py`, nom « check_ui », tenu par un autre processus)."""
    import sys
    import tempfile
    from pathlib import Path
    chemin = Path(tempfile.gettempdir()) / "goldenbrain-check_ui.verrou"
    if not chemin.exists():
        return False
    try:
        with open(chemin, "a+", encoding="utf-8") as f:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f, fcntl.LOCK_UN)
            except OSError:
                return True  # tenu par un autre processus
    except OSError:
        return True  # illisible : dans le doute, on ne retire rien
    return False


class Poste:
    """Réservation unique, persistée dans `<donnees>/etat/poste.json` (une entrée ou aucune)."""

    FILE_TTL_S = 15.0  # un attendant qui ne redemande plus (CLI tuée, tour fini) quitte la file
    ABANDON_S = 1200.0  # INV-POSTE-1 : sans porte vivante ni redemande depuis 20 min, la réservation tombe

    def __init__(self, fichier, delai_s: float, horloge=time.time, vivant=None):
        self.fichier, self.delai_s, self.horloge, self.vivant = fichier, delai_s, horloge, vivant
        self._file: list[dict] = []  # INV-POSTE-1 : {tache, motif, depuis, vu}, premier arrivé en tête
        brut = lire_liste(fichier)  # `lire_liste` tolère un fichier absent ou illisible
        self._res: dict | None = brut[0] if brut and isinstance(brut[0], dict) else None

    def _ecrire(self) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier, json.dumps([self._res] if self._res else []))
        except OSError as e:
            log.warning("réservation du poste non persistée : %s", e)

    def actuelle(self) -> dict | None:
        """Réservation en cours ; une réservation expirée est retirée ici (INV-POSTE-1)."""
        abandon = bool(self._res and self.vivant and self.horloge() - float(self._res.get("renouvele") or 0) > self.ABANDON_S
                       and not self.vivant())  # une porte oubliée ne tient pas le poste jusqu'au délai complet
        if self._res and (abandon or float(self._res.get("expire") or 0) <= self.horloge()):
            self._res = None
            self._ecrire()
        return dict(self._res) if self._res else None

    def _purger(self) -> None:
        """Retire de la file les attendants muets et le titulaire lui-même."""
        t = self.horloge()
        tit = (self._res or {}).get("tache")
        self._file = [e for e in self._file if t - e["vu"] <= self.FILE_TTL_S and e["tache"] != tit]

    def rang(self, tache: str) -> int | None:
        """Rang (1 = le prochain) de la tâche dans la file ; None si elle n'attend pas."""
        self.actuelle()
        self._purger()
        return next((i + 1 for i, e in enumerate(self._file) if e["tache"] == tache), None)

    def file(self) -> list[dict]:
        self.actuelle()
        self._purger()
        return [{"tache": e["tache"], "motif": e["motif"], "depuis": e["depuis"]} for e in self._file]

    def retirer(self, tache: str) -> bool:
        """Sort la tâche de la file (renonce, ou son tour est fini)."""
        avant = len(self._file)
        self._file = [e for e in self._file if e["tache"] != tache]
        return len(self._file) != avant

    def public(self) -> dict | None:
        """Réservation et file, pour `GET /etat` ; None quand le poste est libre."""
        return {**r, "file": self.file()} if (r := self.actuelle()) else None

    def demander(self, tache: str, motif: str = "") -> dict | None:
        """Prend le poste s'il est libre et si la tâche est la première en file ; sinon l'inscrit
        (ou rafraîchit son inscription) et rend None."""
        r = self.actuelle()
        self._purger()
        tete = self._file[0]["tache"] if self._file else None
        if (r and r["tache"] != tache) or (not r and tete not in (None, tache)):
            if (e := next((x for x in self._file if x["tache"] == tache), None)):
                e["vu"] = self.horloge()
            else:
                self._file.append({"tache": tache, "motif": (motif or "").strip()[:200],
                                   "depuis": maintenant(), "vu": self.horloge()})
            return None
        self.retirer(tache)
        self._res = {"tache": tache, "motif": (motif or "").strip()[:200], "depuis": maintenant(),
                     "expire": self.horloge() + self.delai_s, "renouvele": self.horloge()}  # redemander renouvelle le délai
        self._ecrire()
        return dict(self._res)

    def reserver(self, tache: str, motif: str = "") -> dict:
        if (res := self.demander(tache, motif)) is None:
            r = self.actuelle()
            rang = self.rang(tache)
            raise Conflit(langues.t("serveur.poste.deja_reserve", titulaire=r["tache"], heure=r["depuis"][11:16], tache=tache, rang=rang)
                          if r else langues.t("serveur.poste.promis", tache=tache, rang=rang))
        return res

    def liberer(self, tache: str | None = None) -> bool:
        """Rend le poste. `tache` : seul le titulaire le rend (409 sinon) ; sans `tache` (geste
        humain) toute réservation tombe. Rend faux s'il n'y avait rien à rendre."""
        if not (r := self.actuelle()):
            return False
        if tache and r["tache"] != tache:
            raise Conflit(langues.t("serveur.poste.reserve_par", titulaire=r["tache"], tache=tache))
        self._res = None
        self._ecrire()
        return True

    def rendre(self, ident: str) -> bool:
        """Fin de tour : rend d'office la réservation si `ident` en est le titulaire."""
        self.retirer(ident)  # un tour fini n'attend plus rien
        return bool((r := self.actuelle()) and r["tache"] == ident and self.liberer(ident))

    def bloque(self, ident: str, fm: dict) -> dict | None:
        """Réservation qui empêche cette tâche de démarrer : la sienne ne la bloque pas, et
        seule une tâche `epreuves: lourdes` est concernée."""
        lourde = str(fm.get("epreuves") or "").strip().lower() == "lourdes"
        r = self.actuelle()
        return r if lourde and r and r["tache"] != ident else None


class MixinPoste:
    INTERVALLE_POSTE_S = 1.0

    @cached_property
    def poste(self) -> Poste:
        return Poste(self.config.donnees / "etat" / "poste.json",
                     max(1, self.config.moteur.poste_delai_min) * 60, vivant=porte_vivante)

    def _fm(self, ident: str) -> dict:
        try:
            return self.vault.tache(ident).fm
        except NonTrouve:
            return {}  # le tour échouera lisiblement plus loin

    def attente_poste(self, ident: str) -> dict | None:
        """INV-POSTE-1 : « en attente du poste (réservé par <tâche>) » pour une tâche en file."""
        if self.etat_de(ident) != "en_file" or not (r := self.poste.bloque(ident, self._fm(ident))):
            return None
        try:
            titre = self.vault.tache(r["tache"]).titre
        except NonTrouve:
            titre = r["tache"]
        return {"par": r["tache"], "titre": titre, "motif": r["motif"]}

    def _noter_attente(self, ident: str, envoi, t: list) -> None:
        """Une ligne `attente` au journal de mesure au moment du lancement : file (depuis la mise en
        file du message), prérequis, poste, réseau, créneau — en secondes (instrumentation.py)."""
        fin = instrumentation.horloge()
        self.mesures.ajouter({"type": "attente", "date": maintenant(), "tache": ident,
                              "file_s": round(fin - envoi.t_file, 1), "prerequis_s": round(t[1] - t[0], 1),
                              "poste_s": round(t[2] - t[1], 1), "reseau_s": round(t[3] - t[2], 1),
                              "creneau_s": round(fin - t[3], 1), "role": envoi.role})

    async def _tour_au_poste(self, ident: str, envoi) -> None:
        # INV-POSTE-1 : attend la libération sans tenir de créneau (`_sem`) ; rend d'office la
        # réservation du titulaire quand son tour se termine, quelle qu'en soit l'issue.
        h = instrumentation.horloge
        t = [h()]
        await self._attendre_prerequis(ident)  # INV-ORDO-1, sans créneau
        t.append(h())
        attendu = False
        while self.poste.bloque(ident, self._fm(ident)):
            attendu = True
            await asyncio.sleep(self.INTERVALLE_POSTE_S)
        if attendu:
            self.publier("arbre")
        t.append(h())
        await self.reseau.attendre_depart(ident, envoi)  # INV-RESEAU-1 : sans créneau
        t.append(h())
        if executant.humain(self.vault.tache(ident)):
            return  # INV-EXECUTANT-1 : passée à « Moi » pendant l'attente, le message ne part pas
        if lieu := self.executeurs.placer(ident, envoi):
            # INV-DISTANT-2 : un tour placé sur un exécuteur n'occupe pas de créneau du chef.
            await self.executeurs.attendre_place(lieu)
            self._noter_attente(ident, envoi, t)
            self.executeurs.lieux[ident] = lieu
            try:
                await self._tour(ident, envoi)
            finally:
                self.executeurs.lieux.pop(ident, None)
                self.poste.rendre(ident)
            return
        async with self._sem.pour(ident, envoi):  # INV-ORDO-2 : créneau pris à son rang
            self._noter_attente(ident, envoi, t)
            try:
                await self._tour(ident, envoi)
            finally:
                if self.poste.rendre(ident):
                    self.publier("poste")
