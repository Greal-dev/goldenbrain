"""Réveil automatique d'une tâche dont le tour a échoué faute de quota.

Rôle : programmer la relance du message échoué (heure de reprise du harnais + 2 min, sinon toutes
les 30 min, au plus 8 relances), la persister, l'annuler (arrêt, « Reprendre maintenant », tour
réussi), la reprendre au démarrage ; retenir la file d'une tâche bloquée et la relâcher au geste humain ; écrire au journal l'échec d'un tour (message du système).
Frontières : mélangé au `Moteur` (files, vault, publication) ; ne lance aucun harnais lui-même, il
soumet le message par `soumettre`.
Invariants portés : INV-EXEC-8, INV-EXEC-10, INV-EXEC-11 (file d'une tâche bloquée retenue jusqu'au
geste humain), INV-INCIDENT-1 (incident de fin de tour).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging

from dataclasses import replace

from . import echecs, fiches, langues
from .propositions import maintenant
from .vault import ErreurOrch

log = logging.getLogger(__name__)
MARGE_S = 120        # INV-EXEC-10 : délai après l'heure de reprise annoncée
INTERVALLE_S = 1800  # sans heure de reprise : un nouvel essai toutes les 30 minutes
ESSAIS_MAX = 8


class MixinReveil:
    def _init_reveils(self) -> None:
        self.fichier_reveils = self.config.donnees / "etat" / "reveils.json"
        self.minuteries: dict = {}
        try:
            lu = json.loads(self.fichier_reveils.read_text("utf-8"))
        except (OSError, ValueError):
            lu = {}
        self.reveils: dict[str, dict] = lu if isinstance(lu, dict) else {}
        self.retenus: set[str] = set()  # INV-EXEC-11 : tâches bloquées dont la file attend un geste humain

    def _sauver_reveils(self) -> None:
        try:
            self.fichier_reveils.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier_reveils, json.dumps(self.reveils, ensure_ascii=False))
        except OSError as e:
            log.warning("réveils non persistés : %s", e)

    def _journaliser_echec(self, ident: str, motif: str, message: str) -> None:
        # Ligne propre au moteur (jamais émise par un harnais) : la conversation relue la montre.
        try:
            with self._journal(ident) as journal:
                journal.write(json.dumps({"type": "orch_echec", "texte": message, "motif": motif,
                                          "date": maintenant()}, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("journal d'échec impossible : %s", ident)

    def pause_de(self, ident: str) -> str:
        r = self.reveils.get(ident)
        if not r or r.get("lance"):
            return ""
        return langues.t("serveur.reveil.pause", harnais=r["harnais"],
                         heure=f"{dt.datetime.fromisoformat(r['a']):%H:%M}")

    def pauses(self) -> dict[str, str]:
        return {i: p for i in self.reveils if (p := self.pause_de(i))}

    def demarrer_reveils(self) -> None:
        """Au démarrage du serveur (boucle active) : les réveils persistés reprennent leur cours."""
        for ident, r in self.reveils.items():
            if not r.get("lance"):
                self._minuter(ident)

    def fermer_reveils(self) -> None:
        for t in self.minuteries.values():  # l'état reste sur disque pour le redémarrage
            t.cancel()

    def _minuter(self, ident: str) -> None:
        if ancienne := self.minuteries.pop(ident, None):
            ancienne.cancel()
        self.minuteries[ident] = asyncio.get_running_loop().create_task(self._attendre(ident))

    async def _attendre(self, ident: str) -> None:
        r = self.reveils[ident]
        await asyncio.sleep(max(0.0, (dt.datetime.fromisoformat(r["a"]) - dt.datetime.now())
                                .total_seconds()))
        self._relancer(ident)

    def _relancer(self, ident: str) -> None:
        r = self.reveils.get(ident)
        if not r:
            return
        try:
            # Un tour réussi depuis l'échec (message de l'utilisateur) a effacé `echec_tour` : plus rien à relancer.
            if not self.vault.tache(ident).fm.get("echec_tour"):
                return self.annuler_reveil(ident)
            r["lance"] = True
            self._sauver_reveils()
            self.soumettre(ident, r["texte"], sauts=r["sauts"], mandat=r["mandat"], source=r["source"])
        except ErreurOrch as e:  # tâche disparue, plafond de sauts : on abandonne, sans boucle
            log.info("réveil de %s abandonné : %s", ident, e)
            self.annuler_reveil(ident)
        self.publier("pause", tache=ident)

    def annuler_reveil(self, ident: str) -> None:
        if t := self.minuteries.pop(ident, None):
            t.cancel()
        if self.reveils.pop(ident, None) is not None:
            self._sauver_reveils()
            self.publier("pause", tache=ident)

    def reprendre_maintenant(self, ident: str) -> None:
        if ident not in self.reveils or self.reveils[ident].get("lance"):
            return
        if t := self.minuteries.pop(ident, None):
            t.cancel()
        self._relancer(ident)

    def _reveil_fin(self, ident: str, envoi, erreur: str | None, nom: str, arrete: bool) -> None:
        """Fin d'un tour : programme le réveil sur un quota épuisé, l'efface sinon (INV-EXEC-10)."""
        prec = self.reveils.get(ident)
        if not erreur and not arrete:
            self.incidents.clore(ident)  # INV-INCIDENT-1 : tour abouti, bandeau levé
        if arrete:  # INV-INCIDENT-1 : un arrêt se voit aussi (manuel, ou serveur arrêté)
            self.incidents.noter(ident, nom, "redémarrage du serveur" if self.ferme else "tour interrompu",
                                 langues.t("serveur.reveil.repris_demarrage") if self.ferme
                                 else langues.t("serveur.reveil.rendu_humain"), envoi.role or "tache")
        if arrete or not erreur or not echecs.est_quota(erreur) or envoi.role not in ("", "tache") \
                or not self.config.economie.quota_attente:  # INV-QUOTA-1 : attente réglable
            if erreur and not arrete:
                # INV-EXEC-11 : une routine n'est pas retenue — sa prochaine échéance est le nouvel essai
                t = self.vault.index()[0].get(ident)
                garde = envoi.role in ("", "tache") and not (t and t.fm.get("nature") == "routine")
                if garde:
                    self.retenir(ident, envoi)
                self.incidents.noter(ident, nom, erreur, langues.t("serveur.reveil.bloquee_gardee") if garde
                                     else langues.t("serveur.reveil.bloquee_rien"), envoi.role or "tache")
            return self.annuler_reveil(ident)
        essais = prec["essais"] + 1 if prec and prec.get("lance") else 0
        if essais >= ESSAIS_MAX:
            self.annuler_reveil(ident)
            self.incidents.noter(ident, nom, erreur, langues.t("serveur.reveil.abandon", n=ESSAIS_MAX))
            return self._journaliser_echec(
                ident, erreur, langues.t("serveur.reveil.quota_toujours", n=ESSAIS_MAX))
        now = dt.datetime.now()
        reprise = echecs.heure_reprise(erreur, now)
        a = reprise + dt.timedelta(seconds=MARGE_S) if reprise \
            else now + dt.timedelta(seconds=INTERVALLE_S)
        self.reveils[ident] = {"a": a.isoformat(timespec="milliseconds"), "essais": essais,
                               "lance": False, "harnais": nom, "texte": envoi.texte,
                               "sauts": envoi.sauts, "mandat": envoi.mandat, "source": envoi.source}
        self._sauver_reveils()
        self._minuter(ident)
        self.incidents.noter(ident, nom, erreur, langues.t("serveur.reveil.attente_reprise", heure=f"{a:%H:%M}"))
        self.publier("pause", tache=ident)

    # --- rétention d'une tâche bloquée (INV-EXEC-11) -----------------------------------------
    def retenir(self, ident: str, envoi) -> None:
        """Échec durable, rien relancé : le message échoué repasse en tête et la file attend un geste
        humain ; sans cela, chaque message arrivé pendant le blocage échouerait à son tour, perdu."""
        self.retenus.add(ident)
        self.files[ident].appendleft(replace(envoi, harnais=None, modele=None, reprise=False, progres=False))
        self._sauver_actifs()  # INV-EXEC-9 : la file retenue survit au redémarrage

    def liberer(self, ident: str) -> None:
        """Geste humain (moteur, statut, message) : la file retenue repart ; tâche close, elle tombe."""
        if ident in self.retenus:
            self.retenus.discard(ident)
            try:
                ouverte = self.vault.ouverte(self.vault.tache(ident))
            except ErreurOrch:
                ouverte = False
            if not ouverte:
                self.files[ident].clear()
                self._sauver_actifs()
            elif self.files[ident]:
                self.etats[ident] = "en_file"
                self._lancer_boucle(ident)
        self.publier("arbre")

    def _lancer_boucle(self, ident: str) -> None:
        """INV-EXEC-2 : une seule boucle par tâche ; aucune pour une tâche retenue (INV-EXEC-11)."""
        boucle = self.boucles.get(ident)
        if ident not in self.retenus and (not boucle or boucle.done()) \
                and not self.natif.ouvert(ident):  # INV-NATIF-1
            self.boucles[ident] = asyncio.get_running_loop().create_task(self._boucle(ident))
