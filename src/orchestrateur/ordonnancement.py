"""Ordonnancement de la file : prérequis entre tâches et classement des tours éligibles.

Rôle : dire ce qu'une tâche attend (prérequis non terminés), retenir son tour tant qu'elle attend,
et classer les tours éligibles par une seule fonction (`classer`) : message d'un humain, priorité
posée, chemin critique (tâches débloquées transitivement), échéance, ancienneté. Le même
classement choisit le tour qui prend un créneau libre et l'agent mis en pause quand la RAM manque.
Frontières : aucune écriture vault ; ne lance aucun tour ; ne décide pas combien de tours tournent
(c'est `simultanes`).
Invariants portés : INV-ORDO-1 (un tour dont un prérequis n'est pas terminé ne démarre pas ; il
part de lui-même quand le dernier se termine), INV-ORDO-2 (classement unique, déterministe et
motivé, pour le démarrage comme pour la pause).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from . import langues, liens, temps
from .vault import Tache, Vault

SANS_ECHEANCE = "9999-12-31"


@dataclass(frozen=True)
class Candidat:
    ident: str | None  # None : tour sans tâche (revue d'un persona)
    humain: bool
    numero: int  # ordre d'arrivée (attente) ou de démarrage (pause)


def humain(envoi) -> bool:
    """Message tapé par un humain : ni d'une autre tâche, ni propagé, ni mandat, ni reprise."""
    return envoi is not None and not (envoi.de or envoi.source or envoi.mandat
                                      or getattr(envoi, "reprise", False))


def bloquants(vault: Vault, taches: dict[str, Tache], ident: str) -> list[str]:
    """Prérequis encore ouverts (« terminée ou validée » = statut hors des statuts ouverts)."""
    t = taches.get(ident)
    if t is None:
        return []
    return [p for p in liens.prerequis(taches)[0].get(ident, [])
            if taches[p].statut in vault.cfg.statuts_ouverts]


def debloque(vault: Vault, taches: dict[str, Tache], requis_par: dict, ident: str) -> int:
    """Chemin critique : tâches ouvertes qui attendent celle-ci, directement ou non."""
    vus, pile = set(), list(requis_par.get(ident, []))
    while pile:
        if (k := pile.pop()) not in vus:
            vus.add(k)
            pile += requis_par.get(k, [])
    return sum(1 for k in vus if taches[k].statut in vault.cfg.statuts_ouverts)


def _criteres(vault: Vault, taches: dict, requis_par: dict, c: Candidat) -> tuple:
    t = taches.get(c.ident) if c.ident else None
    prio = temps.rang(temps.priorite_de(t.fm)) if t else 3
    deb = debloque(vault, taches, requis_par, c.ident) if t else 0
    ech = temps.echeance_de(t.fm) if t else None
    return (not c.humain, prio, -deb, ech.isoformat() if ech else SANS_ECHEANCE, c.numero)


def _motif(cle: tuple) -> str:
    sans_humain, prio, moins_deb, ech, _ = cle
    if not sans_humain:
        return langues.t("serveur.ordonnancement.humain")
    if prio == 0:
        return langues.t("serveur.ordonnancement.priorite_haute")
    if moins_deb:
        return (langues.t("serveur.ordonnancement.debloque.un", n=1) if moins_deb == -1
                else langues.t("serveur.ordonnancement.debloque.plusieurs", n=-moins_deb))
    if ech != SANS_ECHEANCE:
        return langues.t("serveur.ordonnancement.echeance", date=ech)
    if prio == 1:
        return langues.t("serveur.ordonnancement.priorite_moyenne")
    if prio == 2:
        return langues.t("serveur.ordonnancement.priorite_basse")
    return langues.t("serveur.ordonnancement.arrivee")


def classer(vault: Vault, candidats: list[Candidat]) -> list[tuple[Candidat, str]]:
    """INV-ORDO-2 : du plus prioritaire au moins prioritaire, chacun avec son motif."""
    taches = vault.index()[0]
    requis_par = liens.prerequis(taches)[1]
    cles = sorted((_criteres(vault, taches, requis_par, c), c) for c in candidats)
    return [(c, _motif(cle)) for cle, c in cles]


def rang_lisible(rang: int) -> str:
    return "1ᵉʳ" if rang == 1 else f"{rang}ᵉ"


class MixinOrdonnancement:
    """Partie du moteur : attente des prérequis et vue publique de la file."""

    INTERVALLE_PREREQUIS_S = 3.0  # ponytail: relecture périodique (index en cache) ; un réveil
    # sur fin de tour suffirait, mais une fiche fermée à la main dans Obsidian ne publie rien.

    def attente_prerequis(self, ident: str) -> list[dict]:
        """INV-ORDO-1 : « En attente de : <titres> » ; vide si la tâche peut démarrer."""
        taches = self.vault.index()[0]
        return [{"id": p, "titre": taches[p].titre} for p in bloquants(self.vault, taches, ident)]

    async def _attendre_prerequis(self, ident: str) -> None:
        # INV-ORDO-1 : retenu sans créneau ni tour ; repart seul quand le dernier prérequis finit.
        attendu = False
        while self.attente_prerequis(ident):
            if not attendu:
                attendu = True
                self.publier("arbre")
            await asyncio.sleep(self.INTERVALLE_PREREQUIS_S)
        if attendu:
            self.publier("arbre")

    def file_publique(self) -> dict:
        """Tâches en file : rang et motif (INV-ORDO-2) ou prérequis attendus (INV-ORDO-1)."""
        rangs = self._sem.rangs()
        file = []
        for ident in [i for i, e in list(self.etats.items()) if e == "en_file"]:
            try:
                titre = self.vault.tache(ident).titre
            except Exception:  # tâche disparue du vault entre-temps
                continue
            rang, motif = rangs.get(ident, (None, ""))
            file.append({"tache": ident, "titre": titre, "rang": rang, "motif": motif,
                         "attend": [p["titre"] for p in self.attente_prerequis(ident)],
                         "depuis": self.en_file_depuis.get(ident, "")})
        file.sort(key=lambda f: (f["rang"] is None, f["rang"] or 0, f["depuis"]))
        return {"en_file": sum(len(f) for f in self.files.values()), "file": file}

    def rang_file(self, ident: str) -> dict | None:
        if (r := self._sem.rangs().get(ident)) is None:
            return None
        return {"rang": r[0], "libelle": rang_lisible(r[0]), "motif": r[1]}
