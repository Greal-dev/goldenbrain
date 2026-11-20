"""Jardinage : revue de cohérence périodique, confiée à une tâche permanente.

Rôle : calculer l'échéance (quotidienne, hebdomadaire ou à la demande), soumettre la revue à
la tâche permanente (créée à la première revue), mémoriser `etat/jardinage.json`.
Frontières : agit par le moteur (`creer`, `soumettre`) ; n'écrit dans le vault que par lui.
Invariants portés : INV-JARD-1 (au plus une revue automatique par période, pas de rattrapage
multiple, rien si la revue est déjà en cours ou en file), INV-JARD-2 (le jardinier ne fait que
proposer : ses propositions attendent toujours le geste humain, au plus `plafond` par passage).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from collections.abc import Callable

from . import fiches, langues
from .config import JOURS
from .vault import Invalide, NonTrouve

log = logging.getLogger(__name__)
RECENTES_MAX = 40  # tâches récentes citées au message : de quoi cibler sans gonfler le tour
PERIODES = {"quotidien": dt.timedelta(days=1), "hebdomadaire": dt.timedelta(days=7)}


class Jardinier:
    def __init__(self, moteur, horloge: Callable[[], dt.datetime] = dt.datetime.now):
        self.moteur = moteur
        self.cfg = moteur.config.jardinage
        self.chemin = moteur.config.donnees / "etat" / "jardinage.json"
        self.horloge = horloge  # injectable : les tests avancent le temps sans attendre
        self.etat = self._lire()
        moteur.jardinier = self  # le moteur lui demande d'admettre chaque proposition (INV-JARD-2)

    def _lire(self) -> dict:
        # Un fichier d'état absent ou corrompu ne doit jamais empêcher le serveur de démarrer.
        try:
            etat = json.loads(self.chemin.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        return etat if isinstance(etat, dict) else {}

    def _sauver(self) -> None:
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.chemin, json.dumps(self.etat, ensure_ascii=False))
        except OSError as e:
            log.warning("état du jardinage non persisté : %s", e)

    def _derniere(self) -> dt.datetime | None:
        try:
            return dt.datetime.fromisoformat(str(self.etat.get("derniere")))
        except ValueError:
            return None

    def echeance(self, maintenant: dt.datetime) -> dt.datetime | None:
        """Dernière échéance atteinte (≤ maintenant) ; None à la demande."""
        if self.cfg.rythme not in PERIODES:
            return None
        h, m = map(int, self.cfg.heure.split(":"))
        e = maintenant.replace(hour=h, minute=m, second=0, microsecond=0)
        if self.cfg.rythme == "hebdomadaire":
            e -= dt.timedelta(days=(e.weekday() - JOURS.index(self.cfg.jour)) % 7)
        return e - PERIODES[self.cfg.rythme] if e > maintenant else e

    def due(self, maintenant: dt.datetime) -> bool:
        # INV-JARD-1 : on compare à la SEULE dernière échéance ; plusieurs échéances manquées
        # (serveur éteint) ne donnent qu'une revue.
        e = self.echeance(maintenant)
        derniere = self._derniere()
        return e is not None and (derniere is None or derniere < e)

    def prochaine(self) -> dt.datetime | None:
        maintenant = self.horloge()
        if (e := self.echeance(maintenant)) is None:
            return None
        return e if self.due(maintenant) else e + PERIODES[self.cfg.rythme]

    def admettre(self, de: str) -> bool:
        """INV-JARD-2 : True si `de` est la tâche du jardinier ; lève `Invalide` au-delà du plafond."""
        if not de or de != self.etat.get("tache"):
            return False
        posees = int(self.etat.get("posees") or 0)
        if posees >= self.cfg.plafond:
            raise Invalide(langues.t("serveur.jardinage.plafond", plafond=self.cfg.plafond))
        self.etat = {**self.etat, "posees": posees + 1}
        self._sauver()
        return True

    def recentes(self) -> list[str]:
        """Tâches ouvertes modifiées depuis `recentes_jours`, les plus récentes d'abord."""
        limite = (self.horloge() - dt.timedelta(days=self.cfg.recentes_jours)).date().isoformat()
        vues = []
        for k, t in self.moteur.vault.index()[0].items():
            d = str(t.fm.get("updated") or t.fm.get("created") or "")[:10]
            if d >= limite and k != self.etat.get("tache") and self.moteur.vault.ouverte(t) and not t.pilotage:
                vues.append((d, k, t.titre))
        return [f"- {k} — {titre} ({d})" for d, k, titre in sorted(vues, reverse=True)[:RECENTES_MAX]]

    def _message(self) -> str:
        base = (self.cfg.message.strip() or self.cfg.titre).replace("{plafond}", str(self.cfg.plafond))
        recentes = self.recentes()
        return base + (f"\n\nTâches récentes ({self.cfg.recentes_jours} jours) :\n" + "\n".join(recentes)
                       if recentes else "")

    def lancer(self) -> str:
        """Soumet une revue maintenant ; crée la tâche permanente si elle n'existe pas (plus)."""
        ident = str(self.etat.get("tache") or "")
        try:
            self.moteur.vault.tache(ident)
        except NonTrouve:
            ident = self.moteur.creer(self.cfg.titre)  # sans conteneur : `vault.arrivee`
            # Mémorisée aussitôt : une soumission en échec ne doit pas recréer une tâche par minute.
            self.etat = {**self.etat, "tache": ident}
            self._sauver()
        self.moteur.soumettre(ident, self._message(), role="jardinage")
        self.etat = {"tache": ident, "derniere": self.horloge().isoformat(timespec="seconds"), "posees": 0}
        self._sauver()
        return ident

    def verifier(self) -> str | None:
        if not self.moteur.config.interface.actif("jardinage"):  # INV-INTERFACE-1
            return None
        if not self.due(self.horloge()):
            return None
        ident = self.etat.get("tache")
        if ident and self.moteur.etat_de(ident) in ("en_cours", "en_file"):
            return None  # INV-JARD-1 : la revue précédente n'est pas finie
        return self.lancer()

    async def boucle(self) -> None:
        if self.cfg.rythme not in PERIODES:
            return  # à la demande : aucune revue automatique, pas même au démarrage
        while True:
            try:
                self.verifier()
            except Exception:  # le planificateur survit à un échec ponctuel
                log.exception("revue de jardinage non lancée")
            await asyncio.sleep(60)

    def public(self) -> dict:
        prochaine = self.prochaine()
        return {"rythme": self.cfg.rythme,
                "prochaine": prochaine.isoformat(timespec="seconds") if prochaine else None,
                "derniere": self.etat.get("derniere"), "tache": self.etat.get("tache")}
