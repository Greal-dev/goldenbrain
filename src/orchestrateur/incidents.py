"""Incidents : pourquoi un tour a échoué ou s'est arrêté, ce que GoldenBrain a fait, quel geste reste.

Rôle : classer le motif brut d'un échec en cause lisible (quota, réseau, harnais non installé ou
introuvable, non connecté, durée maximale, arrêt manuel, redémarrage, autre), tenir les 200 derniers incidents dans
`etat/incidents.json`, les exposer (bandeau de la tâche, vue Incidents).
Frontières : n'agit sur rien ; les appelants (fin de tour, réseau, bascule, revues) disent ce
qu'ils ont fait. Aucune écriture vault.
Invariants portés : INV-INCIDENT-1 (tout échec ou arrêt d'un tour laisse un incident lisible).
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque

from . import echecs, fiches, langues
from .propositions import maintenant

log = logging.getLogger(__name__)
MAX = 200

# (cause, motif reconnu) : le premier qui correspond l'emporte ; libellé et geste : `_textes`.
CAUSES = (
    ("arret", re.compile(r"tour interrompu|arr[êe]t manuel", re.I)),
    ("redemarrage", re.compile(r"red[ée]marrage du serveur", re.I)),
    ("quota", echecs.QUOTA),
    ("absent", echecs.INTROUVABLE),
    ("reseau", echecs.RESEAU),
    ("introuvable", re.compile(r"harnais inconnu|not found", re.I)),
    ("connexion", re.compile(r"not logged in|log ?in|unauthori[sz]ed|\b401\b|authenticat|api key", re.I)),
    ("duree", re.compile(r"dur[ée]e maximale", re.I)),
)


def _textes(cause: str, h: str) -> tuple[str, str]:
    """(libellé, geste) d'une cause, dans la langue réglée ; `h` : nom de l'assistant IA."""
    t = langues.t
    match cause:
        case "arret":
            return t("serveur.incidents.arret"), t("serveur.incidents.arret_geste")
        case "redemarrage":
            return t("serveur.incidents.redemarrage"), t("serveur.incidents.redemarrage_geste")
        case "quota":
            return t("serveur.incidents.quota"), t("serveur.incidents.quota_geste")
        case "absent":
            return t("serveur.incidents.absent"), t("serveur.incidents.absent_geste", h=h)
        case "reseau":
            return t("serveur.incidents.reseau"), t("serveur.incidents.reseau_geste")
        case "introuvable":
            return t("serveur.incidents.introuvable"), t("serveur.incidents.introuvable_geste")
        case "connexion":
            return t("serveur.incidents.connexion"), t("serveur.incidents.connexion_geste")
        case "duree":
            return t("serveur.incidents.duree"), t("serveur.incidents.duree_geste")
    return t("serveur.incidents.autre"), t("serveur.incidents.autre_geste")


def classer(motif: str, harnais: str = "") -> tuple[str, str, str]:
    """(cause, libellé, geste proposé) d'un motif d'échec."""
    cause = next((c for c, motif_re in CAUSES if motif_re.search(motif or "")), "autre")
    libelle, geste = _textes(cause, harnais or langues.t("serveur.incidents.cet_assistant"))
    if cause == "quota" and (r := echecs.REPRISE.search(motif)):
        libelle = langues.t("serveur.incidents.quota_reprise", reprise=r[1])
    return cause, libelle, geste


class Incidents:
    def __init__(self, moteur):
        self.m = moteur
        self.fichier = moteur.config.donnees / "etat" / "incidents.json"
        try:
            lu = json.loads(self.fichier.read_text("utf-8"))
        except (OSError, ValueError):
            lu = []
        self.liste: deque[dict] = deque((x for x in lu if isinstance(x, dict)) if isinstance(lu, list)
                                        else (), maxlen=MAX)

    def noter(self, ident: str, harnais: str, motif: str, action: str, role: str = "tache") -> dict:
        """INV-INCIDENT-1 : quand, quel moteur, cause lisible, ce qui a été fait, geste proposé."""
        cause, libelle, geste = classer(motif, harnais)
        try:
            titre = self.m.vault.tache(ident).titre
        except Exception:  # noqa: BLE001 — une tâche disparue garde son incident
            titre = ident
        inc = {"date": maintenant(), "tache": ident, "titre": titre, "harnais": harnais or "?",
               "role": role, "cause": cause, "libelle": libelle,
               "motif": " ".join((motif or "").split())[:400], "action": action, "geste": geste}
        self.liste.append(inc)
        self._sauver()
        self.m.publier("incident", tache=ident)
        return inc

    def clore(self, ident: str) -> None:
        """Tour abouti : les incidents de la tâche quittent son bandeau (la vue Incidents les garde)."""
        ouverts = [i for i in self.liste if i["tache"] == ident and not i.get("clos")]
        for i in ouverts:
            i["clos"] = True
        if ouverts:
            self._sauver()
            self.m.publier("incident", tache=ident)

    def _sauver(self) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier, json.dumps(list(self.liste), ensure_ascii=False))
        except OSError as e:
            log.warning("incidents non persistés : %s", e)

    def dernier(self, ident: str) -> dict | None:
        """Incident encore ouvert de la tâche (bandeau de sa conversation)."""
        return next((i for i in reversed(self.liste) if i["tache"] == ident and not i.get("clos")), None)

    def public(self, limite: int = MAX) -> list[dict]:
        return list(reversed(self.liste))[:limite]
