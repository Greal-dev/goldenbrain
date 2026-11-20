"""Mise à jour automatique : appliquer seul une mise à jour disponible, sans jamais couper un travail à risque.

Rôle : quand l'option est active et qu'une mise à jour attend sur la branche de diffusion, geler le
démarrage des tours (la file attend), laisser finir les tours en cours, ne « mettre en pause » (= les
laisser couper par le redémarrage, qui les reprend dans leur session, INV-EXEC-1) que ceux qui
dépassent le délai ET sont à un point de reprise sûr ; puis avance rapide (INV-MAJ-1), contrôle
d'importation, redémarrage unique, et bandeau après coup. Échec : retour à la version précédente,
incident visible, une tentative par version.
Frontières : aucune logique git (module `mise_a_jour`) ; le redémarrage est celui de `Version` ;
la reprise des tours et de la file est celle de `reprise` ; le réglage et l'état vivent dans
`<donnees>/etat/maj_auto.json` (config.py est à sa limite de taille, et le réglage change sans redémarrage).
Le canal (stable ou bêta, INV-MAJ-4) se règle ici aussi : même fichier, même absence de redémarrage.
Invariants portés : INV-MAJ-3, INV-MAJ-4.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable

from . import fiches, langues, mise_a_jour
from .vault import ErreurOrch, Invalide

log = logging.getLogger(__name__)
SONDE_S = 10
CALME_S = 120  # sans geste dans l'interface depuis ce délai : l'utilisateur n'interagit plus
REGLAGE = {"actif": False, "delai_min": 30, "fenetre_debut": "", "fenetre_fin": "", "canal": "stable"}


def _heure(valeur: str) -> dt.time | None:
    try:
        return dt.time.fromisoformat(valeur) if valeur else None
    except ValueError:
        raise Invalide(langues.t("serveur.maj_auto.heure_invalide", valeur=repr(valeur))) from None


def canal_enregistre(fichier: Path) -> str:
    """INV-MAJ-4 : canal réglé dans l'interface, lu aussi par `mettre-a-jour.cmd` ; « stable » à défaut."""
    try:
        canal = (json.loads(fichier.read_text(encoding="utf-8")).get("reglage") or {}).get("canal")
    except (OSError, ValueError, AttributeError):
        return "stable"
    return canal if canal in mise_a_jour.CANAUX else "stable"


def dans_fenetre(reglage: dict, maintenant: dt.datetime) -> bool:
    """Fenêtre horaire facultative ; `22:00`→`06:00` traverse minuit ; vide = toujours."""
    d, f = _heure(reglage["fenetre_debut"]), _heure(reglage["fenetre_fin"])
    if d is None or f is None or d == f:
        return True
    h = maintenant.time()
    return d <= h < f if d < f else (h >= d or h < f)


class MajAuto:
    def __init__(self, moteur, version, depot, config_maj, controle: Callable[..., Awaitable[dict]],
                 invalider: Callable[[], None], fichier: Path, maintenant=dt.datetime.now,
                 sonde_s: float = SONDE_S, calme_s: float = CALME_S):
        self.m, self.version, self.depot, self.cfg = moteur, version, depot, config_maj
        self.controle, self.invalider, self.fichier = controle, invalider, fichier
        self.maintenant, self.sonde_s, self.calme_s = maintenant, sonde_s, calme_s
        self.reglage = dict(REGLAGE)
        self.etat: dict = {}  # tentee, bandeau, incident, redemarrage (persistés)
        self.phase = "veille"  # veille → gel → applique → redemarre (processus quitté)
        self.attendus: list[str] = []  # tours dont la fin (ou la pause sûre) est attendue
        self.verifier_import = lambda: mise_a_jour.verifier_import(depot)
        self._activite = 0.0
        self._tache: asyncio.Task | None = None
        self._lire()

    # --- persistance -----------------------------------------------------------------------
    def _lire(self) -> None:
        try:
            brut = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(brut, dict):
            self.reglage.update({k: v for k, v in (brut.get("reglage") or {}).items() if k in REGLAGE})
            self.etat = brut.get("etat") if isinstance(brut.get("etat"), dict) else {}

    def _ecrire(self) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.fichier, json.dumps({"reglage": self.reglage, "etat": self.etat},
                                                         ensure_ascii=False, indent=1))

    def regler(self, c: dict) -> dict:
        """Valide tout puis applique (en cas d'erreur rien ne change)."""
        nouveau = {**self.reglage, **{k: v for k, v in c.items() if k in REGLAGE and v is not None}}
        if not isinstance(nouveau["actif"], bool):
            raise Invalide(langues.t("serveur.maj_auto.actif_invalide"))
        if not isinstance(nouveau["delai_min"], int) or not 1 <= nouveau["delai_min"] <= 1440:
            raise Invalide(langues.t("serveur.maj_auto.delai_invalide"))
        _heure(nouveau["fenetre_debut"]), _heure(nouveau["fenetre_fin"])
        if bool(nouveau["fenetre_debut"]) != bool(nouveau["fenetre_fin"]):
            raise Invalide(langues.t("serveur.maj_auto.fenetre_invalide"))
        if nouveau["canal"] not in mise_a_jour.CANAUX:
            raise Invalide(langues.t("serveur.maj_auto.canal_invalide", canaux=", ".join(mise_a_jour.CANAUX)))
        change = nouveau["canal"] != self.reglage["canal"]
        self.reglage = nouveau
        self._ecrire()
        if change:
            self.invalider()  # INV-MAJ-4 : le prochain contrôle porte sur la branche du nouveau canal
        return self.vue()

    def suivie(self):
        """INV-MAJ-4 : (configuration du canal choisi, branches de diffusion entre lesquelles basculer)."""
        return mise_a_jour.suivie(self.cfg, self.reglage["canal"])

    # --- état public -----------------------------------------------------------------------
    def vue(self) -> dict:
        return {"reglage": self.reglage, "phase": self.phase, "cible": self.etat.get("cible", ""),
                "attendus": len(self.attendus), "gel": self.m._sem.gele,
                "dans_fenetre": dans_fenetre(self.reglage, self.maintenant()),
                "bandeau": self.etat.get("bandeau"), "incident": self.etat.get("incident")}

    def activite(self) -> None:
        self._activite = time.monotonic()

    def _calme(self) -> bool:
        return time.monotonic() - self._activite >= self.calme_s

    def fermer_bandeau(self) -> None:
        self.etat.pop("bandeau", None)
        self.etat.pop("incident", None)
        self._ecrire()

    # --- démarrage et arrêt ----------------------------------------------------------------
    def demarrer(self) -> None:
        """Après la reprise des tours : si le processus vient d'un redémarrage de mise à jour, le dire."""
        r = self.etat.pop("redemarrage", None)
        (self.depot / mise_a_jour.FICHIER_RETOUR).unlink(missing_ok=True)  # arrivé vivant : pas de retour
        if r:
            ouvertes = [i for i in r.get("reprises", []) if self._ouverte(i)]
            self.etat["bandeau"] = {"version": r.get("version", ""), "a": r.get("a", ""), "reprises": len(ouvertes)}
            self._ecrire()
        self._tache = asyncio.get_running_loop().create_task(self._boucle())

    def fermer(self) -> None:
        if self._tache:
            self._tache.cancel()

    def _ouverte(self, ident: str) -> bool:
        try:
            return self.m.vault.ouverte(self.m.vault.tache(ident))
        except Exception:  # tâche disparue
            return False

    async def _boucle(self) -> None:
        while not self.m.ferme:
            await asyncio.sleep(self.sonde_s)
            try:
                await self.pas()
            except Exception:  # INV-EXEC-6 : une veille qui échoue se journalise, elle ne s'arrête pas
                log.exception("mise à jour automatique")

    # --- séquence --------------------------------------------------------------------------
    def _degeler(self) -> None:
        self.m._sem.degeler()
        self.phase, self.attendus = "veille", []

    async def pas(self) -> None:
        """Un pas de la séquence ; idempotent, appelé toutes les `sonde_s` secondes."""
        if self.phase in ("applique", "redemarre") or self.version.code_sortie:
            return  # INV-MAJ-3 : un seul redémarrage
        if not self.reglage["actif"]:
            if self.phase == "gel":
                self._degeler()
            return
        if self.phase == "veille":
            e = await self.controle(False)
            if not e.get("depot") or e.get("retard", 0) <= 0 or e.get("distante") == self.etat.get("tentee"):
                return  # rien à faire, ou version déjà tentée sans succès : jamais de boucle
            if not (dans_fenetre(self.reglage, self.maintenant()) and self._calme()):
                return  # reporté : hors fenêtre, ou l'utilisateur est à l'écran
            self.etat["cible"] = e["distante"]
            self.m._sem.geler()  # plus aucun nouveau tour ; la file attend
            self.phase = "gel"
            log.warning("mise à jour automatique : %s disponible, démarrage des tours gelé", e["distante"])
        reste = [i for i in list(self.m.tours) if not (await self.pausable(i))[0]]
        self.attendus = reste
        if reste or not self._calme():
            return  # les tours finissent d'eux-mêmes ; le redémarrage attend aussi que l'écran soit calme
        await self._appliquer()

    async def pausable(self, ident: str) -> tuple[bool, str]:
        """Un tour peut être laissé couper par le redémarrage (puis repris) s'il a dépassé le délai et
        est à un point de reprise sûr. Doute = non : on attend sa fin, jamais d'interruption brutale."""
        tour, envoi = self.m.tours.get(ident), self.m.envois.get(ident)
        try:
            age = (dt.datetime.now() - dt.datetime.fromisoformat(tour.depuis)).total_seconds()
        except (AttributeError, ValueError):
            return False, "durée inconnue"
        if age < self.reglage["delai_min"] * 60:
            return False, "dans le délai"
        if envoi is not None and envoi.reprise and not envoi.progres:
            return False, "déjà repris sans avoir progressé"
        try:
            if not self.m.vault.tache(ident).fm.get("session"):
                return False, "pas de session à reprendre"
        except Exception:
            return False, "tâche illisible"
        if self.m._sem.en_pause(ident):
            return True, "en pause faute de mémoire"
        vigie = self.m.vigie
        v = vigie.vue(ident) if vigie else None
        if not v or not v["silencieux"]:
            return False, "agent actif (écriture ou échange récent)"
        d = v["diagnostic"] or await vigie.diagnostiquer(ident)
        if not d.get("disponible"):
            return False, "processus inobservable"
        if d.get("bloquant") or d.get("enfants"):
            return False, "commande en cours"
        return True, "silencieux, sans processus actif"

    async def _appliquer(self) -> None:
        self.phase = "applique"
        e = await self.controle(False)
        ancienne, cible = e.get("locale", ""), e.get("distante", "")
        self.etat["tentee"] = cible  # avant d'agir : un plantage ne rejoue pas la même version
        self._ecrire()
        try:
            res = await asyncio.to_thread(mise_a_jour.appliquer, self.depot, *self.suivie())
            self.invalider()
            if not res["appliquee"]:
                return self._abandon("")
            try:
                await asyncio.to_thread(self.verifier_import)
            except ErreurOrch as ex:
                await asyncio.to_thread(mise_a_jour.revenir, self.depot, ancienne)
                return self._abandon(langues.t("serveur.maj_auto.import_echec", erreur=ex),
                                     langues.t("serveur.maj_auto.import_geste"))
        except ErreurOrch as ex:
            return self._abandon(str(ex), langues.t("serveur.maj_auto.refus_geste"))
        ids = list(dict.fromkeys([*self.m.tours, *self.m.files, *self.m.attente]))
        self.etat["redemarrage"] = {"version": res["locale"], "a": self.maintenant().strftime("%H:%M"), "reprises": ids}
        (self.depot / mise_a_jour.FICHIER_RETOUR).write_text(ancienne, encoding="utf-8")  # lu par lancer.sh
        self._ecrire()
        self.phase = "redemarre"
        log.warning("mise à jour automatique : %s appliquée, redémarrage (%d tâche(s) à reprendre)", res["locale"], len(ids))
        self.version.redemarrer()  # INV-VERSION-1 : arrêt normal, sortie 3 ; reprise INV-EXEC-1 / INV-EXEC-9

    def _abandon(self, cause: str, geste: str = "") -> None:
        if cause:
            self.etat["incident"] = {"cause": cause, "geste": geste, "version": self.etat.get("tentee", ""),
                                     "a": self.maintenant().strftime("%H:%M")}
            log.warning("mise à jour automatique abandonnée : %s", cause)
        self._ecrire()
        self._degeler()
