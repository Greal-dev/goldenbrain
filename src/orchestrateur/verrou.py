"""Verrous : occupation des tâches par un agent, demi-verrou des gestes humains, verrou des
déplacements de dossiers.

Rôle : dire quelle tâche un agent travaille (`occupation`, seule définition), refuser un geste
humain sur une tâche occupée sauf confirmation (`demi_verrou`, 409 `Occupee`), décider si un tour
touche un dossier déplacé ou un fichier réécrit (409 nommé) et tenir ces tâches à l'arrêt pendant
l'application ; mélangé au `Moteur` (états, files, tours, revues, sémaphore, config).
Frontières : ne déplace rien ; le plan (dossiers, fichiers) vient d'`Aligneur.perimetre`.
Invariants portés : INV-VERROU-1, INV-ALIGN-2.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from . import langues
from .vault import Conflit, NonTrouve


class Occupee(Conflit):
    """INV-VERROU-1 : geste humain sur une tâche occupée, sans `forcer` (409 + `occupee`)."""

    def __init__(self, occupee: dict):
        self.occupee = occupee
        heure = occupee["depuis"][11:16]
        terminal = occupee.get("terminal")  # INV-NATIF-1
        titre = occupee["titre"]
        if terminal:
            msg = (langues.t("serveur.verrou.terminal_depuis", titre=titre, heure=heure) if heure
                   else langues.t("serveur.verrou.terminal", titre=titre))
        else:
            msg = (langues.t("serveur.verrou.agent_depuis", titre=titre, heure=heure) if heure
                   else langues.t("serveur.verrou.agent", titre=titre))
        super().__init__(msg)


def _taches_sous(noeuds: list[dict], cible: str, dedans: bool = False) -> list[str]:
    """Tâches du nœud `cible` et de toute sa descendance dans l'arbre rendu."""
    out: list[str] = []
    for n in noeuds:
        ici = dedans or n["id"] == cible
        if ici and n["type"] == "tache":
            out.append(n["id"])
        out += _taches_sous(n.get("enfants") or [], cible, ici)
    return out


class MixinVerrou:
    def _init_verrou(self) -> None:
        self.exclusif_actif = False  # INV-ALIGN-2 : un déplacement de dossiers est en cours
        self.verrouillees: set[str] = set()  # INV-ALIGN-2 : tâches dont aucun tour ne démarre
        self._libere = asyncio.Event()
        self._libere.set()

    def occupe(self) -> bool:
        """Un tour tourne, attend en file, une revue est en suspens ou une tâche est ouverte au
        terminal (n'importe où)."""
        return (bool(self.tours) or any(self.files.values()) or bool(self.natif.ouverts)
                or any(e in ("en_cours", "en_file") for e in self.etats.values())
                or any(not t.done() for t in self.revues._fond))

    def occupation(self, ident: str) -> dict | None:
        """INV-VERROU-1 : seule définition de « un agent travaille sur cette tâche » — un tour
        (de la tâche ou d'un persona sur elle) tourne ou attend, ou une revue d'elle est en
        suspens. Rend {tache, titre, depuis, moteur}, sinon None. INV-NATIF-1 : une tâche ouverte
        dans l'interface native de son harnais est occupée par l'utilisateur (`terminal: True`)."""
        if natif := self.natif.ouvert(ident):
            try:
                titre = self.vault.tache(ident).titre
            except NonTrouve:
                titre = ident
            return {"tache": ident, "titre": titre, "depuis": natif["depuis"],
                    "moteur": natif["moteur"], "terminal": True}
        tour = next((t for t in list(self.tours.values()) if t.tache == ident), None)
        revue = next((a for a in self.revues.avis.get(ident, []) if a.get("verdict") == "en_cours"),
                     None)
        cycle = self.revues.cycles.get(ident)
        if not (tour or revue or self.etat_de(ident) in ("en_cours", "en_file")
                or self.files.get(ident) or (cycle is not None and not cycle.done())):
            return None
        try:
            t = self.vault.tache(ident)
            titre, fm = t.titre, t.fm
        except NonTrouve:
            titre, fm = ident, {}
        nom = str(fm.get("harnais") or self.config.moteur.harnais_defaut)
        nom = getattr(tour.harnais, "nom", nom) if tour else nom
        modele = "" if tour and tour.persona else str(fm.get("modele") or "")
        return {"tache": ident, "titre": titre,
                "depuis": (tour.depuis if tour else self.en_file_depuis.get(ident)
                           or (revue or {}).get("date", "")),
                "moteur": "/".join(x for x in (nom, modele) if x)}

    def occupees(self) -> dict[str, dict]:
        """Toutes les tâches occupées (candidats : clés des états d'exécution)."""
        candidats = ({t.tache for t in list(self.tours.values())} | set(self.files)
                     | set(self.etats) | set(self.revues.cycles) | set(self.revues.avis)
                     | set(self.natif.ouverts) | set(self.portees()))  # INV-REGROUPE-3
        return {i: o for i in candidats if (o := self.occupation(i))}

    def occupees_sous(self, noeud_id: str) -> list[dict]:
        """Occupations du nœud (tâche, conteneur, opération, casquette) et de sa descendance
        dans l'arbre (liens `parent:` compris)."""
        if not (toutes := self.occupees()):
            return []  # rien d'occupé : l'arbre n'est pas construit
        ids = _taches_sous(self.vault.arbre(True), noeud_id) or [noeud_id]
        return [toutes[i] for i in dict.fromkeys(ids) if i in toutes]

    def demi_verrou(self, noeud_id: str, forcer: bool, seule: bool = False) -> None:
        """INV-VERROU-1 : refuse (409 `Occupee`) un geste humain sur un nœud occupé — la tâche
        `seule`, sinon le nœud et sa descendance — sauf `forcer`. N'outrepasse jamais
        `exclusif` (INV-ALIGN-2), appelé après."""
        if forcer:
            return
        if seule:
            occ = [o] if (o := self.occupation(noeud_id)) else []
        else:
            occ = self.occupees_sous(noeud_id)
        if occ:
            raise Occupee(occ[0])

    def verrouillee(self, ident: str) -> bool:
        return ident in self.verrouillees

    async def _attendre_verrou(self, ident: str) -> None:
        # INV-ALIGN-2 : un tour sur une tâche d'un dossier en déplacement attend la fin du geste.
        while self.verrouillee(ident):
            await self._libere.wait()

    def _touchees(self, dossiers: list[str], fichiers: list[str]) -> list:
        """Tâches situées dans un des dossiers ou dont le fichier figure parmi les fichiers
        (chemins relatifs à la racine du vault)."""
        racine = self.vault.racine
        ds, fs = [racine / d for d in dossiers], [racine / f for f in fichiers]
        return [t for t in self.vault.index()[0].values()
                if any(t.chemin == f for f in fs) or any(t.chemin.is_relative_to(d) for d in ds)]

    @asynccontextmanager
    async def exclusif(self, dossiers: list[str] | None = None, fichiers: list[str] | None = None):
        """INV-ALIGN-2. Sans argument (mise à jour du dépôt) : refuse si un tour est actif ou en
        file n'importe où, puis bloque tout démarrage de tour (`Creneaux.bloquer`). Avec `dossiers` et
        `fichiers` (déplacement) : refuse, en nommant les tâches, si un tour tourne ou attend sur
        une tâche de ces dossiers ou sur un fichier réécrit ; jusqu'à la sortie, aucun tour ne
        démarre sur ces tâches, les autres continuent."""
        if self.exclusif_actif:
            raise Conflit(langues.t("serveur.verrou.deplacement_en_cours"))
        if dossiers is None and fichiers is None:
            if self.occupe():
                raise Conflit(langues.t("serveur.verrou.travail_en_cours"))
            touchees: list = []
        else:
            touchees = self._touchees(dossiers or [], fichiers or [])
            if bloquantes := [t for t in touchees if self.occupation(t.id) is not None]:
                noms = ", ".join(f"« {t.titre} » ({t.id})" for t in bloquantes)
                raise Conflit(langues.t("serveur.verrou.deplacement_refuse", taches=noms))
        self.exclusif_actif = True
        self.verrouillees = {t.id for t in touchees}
        self._libere.clear()
        pris = 0
        try:
            if dossiers is None and fichiers is None:
                self._sem.bloquer()  # rien d'actif : aucun tour ne démarre jusqu'à la sortie
                pris = 1
            yield
        finally:
            if pris:
                self._sem.debloquer()
            self.exclusif_actif = False
            self.verrouillees = set()
            self._libere.set()
