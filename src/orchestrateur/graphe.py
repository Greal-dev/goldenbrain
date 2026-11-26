"""Graphe du second cerveau : notes, tâches et conteneurs, reliés par leurs liens.

Rôle : assembler, à partir de l'index des notes et de l'index des tâches, les nœuds (note,
tâche, conteneur) et les arêtes (wikilien, liens de tâches, appartenance) ; servir le graphe
local (voisinage d'un nœud) et le graphe global filtré.
Frontières : lecture seule ; n'écrit rien, ne balaie pas le disque (l'index le fait) ; appelé
hors de la boucle d'événements.
Invariants portés : INV-GRAPHE-1 (calcul côté serveur, en cache, périmé dès que l'index des
notes ou celui des tâches change), INV-GRAPHE-2 (au plus `limite` nœuds servis, jamais plus de
PLAFOND : les plus reliés sont gardés, `total` et `tronque` le disent).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import liens as liens_taches
from .etiquettes import de as etiquettes_de
from .vault import casquette_normalisee

PLAFOND = 2000
GENRES = ("note", "tache", "conteneur")


@dataclass(slots=True)
class Noeud:
    id: str              # chemin de la note ; « <dossier>/ » pour un conteneur sans contexte.md
    titre: str
    genre: str           # note | tache | conteneur
    type: str            # `type:` du frontmatter
    projet: str          # conteneur d'appartenance ("" hors conteneur)
    casquette: str
    tags: tuple[str, ...]
    maj: int             # mtime_ns ; 0 pour un conteneur sans fichier
    tache: str | None = None
    voisins: set[int] = field(default_factory=set)


@dataclass(slots=True)
class Donnees:
    noeuds: list[Noeud]
    rang: dict[str, int]
    aretes: list[tuple[int, int, str]]


class Graphe:
    def __init__(self, index, vault, contexte: str = "contexte.md"):
        self.index = index
        self.vault = vault
        self.contexte = contexte
        self.calculs = 0  # mesure : nombre de constructions (le cache doit les rendre rares)
        self._cle: tuple | None = None
        self._donnees: Donnees | None = None
        self._verrou = threading.Lock()

    # --- construction (INV-GRAPHE-1) --------------------------------------------------------
    def donnees(self) -> Donnees:
        with self._verrou:
            idx = self.vault.index()
            # Le contenu des tâches est celui de leurs fichiers, que suit `generation` ; l'index des
            # tâches, lui, est refait à chaque échéance : seul compte l'ensemble des nœuds qu'il porte.
            cle = (self.index.generation, frozenset(idx[0]), frozenset(idx[1]))
            if cle != self._cle:
                self._donnees = self._construire(idx)
                self._cle = cle
                self.calculs += 1
            return self._donnees

    def _rel(self, p: Path) -> str | None:
        try:
            return Path(p).resolve().relative_to(self.index.racine).as_posix()
        except (OSError, ValueError):
            return None

    def _construire(self, idx) -> Donnees:
        taches, conts = idx
        notes = self.index.pour_graphe()
        par_chemin = {n[0]: n for n in notes}
        tache_de = {r: t for t in taches.values() if (r := self._rel(t.chemin))}
        ids_conts = sorted(conts, key=len, reverse=True)  # préfixe le plus long d'abord

        def projet_de(rel: str) -> str:
            return next((c for c in ids_conts if rel.startswith(c + "/")), "")

        noeuds: list[Noeud] = []
        rang: dict[str, int] = {}

        def ajouter(n: Noeud) -> int:
            rang[n.id] = len(noeuds)
            noeuds.append(n)
            return rang[n.id]

        noeud_cont: dict[str, int] = {}
        for cid, c in conts.items():
            ctx = f"{cid}/{self.contexte}"
            n = par_chemin.get(ctx)
            noeud_cont[cid] = ajouter(Noeud(ctx if n else cid + "/", c.titre, "conteneur",
                                            n[2] if n else "", cid, c.casquette or "",
                                            n[4] if n else (), n[3] if n else 0))
        for rel, titre, type_, maj, tags, _ in notes:
            if rel in rang:
                continue
            t = tache_de.get(rel)
            projet = t.conteneur if t else projet_de(rel)
            cas = (casquette_normalisee(t.fm.get("casquette")) if t else None) or (
                conts[projet].casquette if projet in conts else "") or ""
            # INV-ETIQUETTE-3 : les étiquettes d'une tâche se filtrent et se comptent comme des tags dans le graphe
            ajouter(Noeud(rel, t.titre if t else titre, "tache" if t else "note", type_, projet,
                          cas, (*tags, *etiquettes_de(t.fm)) if t else tags, maj, t.id if t else None))

        vues: set[tuple[int, int]] = set()
        aretes: list[tuple[int, int, str]] = []

        def relier(a: int | None, b: int | None, genre: str) -> None:
            if a is None or b is None or a == b or (min(a, b), max(a, b)) in vues:
                return
            vues.add((min(a, b), max(a, b)))
            aretes.append((a, b, genre))
            noeuds[a].voisins.add(b)
            noeuds[b].voisins.add(a)

        # Liens de tâches d'abord : ils l'emportent sur le wikilien du frontmatter qui les porte.
        rel_tache = {t.id: r for r, t in tache_de.items()}
        for r, t in tache_de.items():
            for cle in liens_taches.TYPES:
                for cible in liens_taches.ids(t.fm, cle):
                    relier(rang.get(r), rang.get(rel_tache.get(cible, "")), cle)
        for rel, *_, cibles in notes:
            for c in cibles:
                relier(rang.get(rel), rang.get(c), "lien")
        for n in list(noeuds):
            i = rang[n.id]
            if n.genre == "conteneur":
                parent = projet_de(n.projet)  # conteneur englobant
                relier(i, noeud_cont.get(parent), "appartient")
            elif n.projet in noeud_cont:
                relier(i, noeud_cont[n.projet], "appartient")
        return Donnees(noeuds, rang, aretes)

    # --- lecture ----------------------------------------------------------------------------
    def local(self, centre: str, profondeur: int = 1, limite: int = PLAFOND) -> dict:
        """Voisinage d'un nœud (chemin de note, ou identifiant de tâche), profondeur 1 ou 2."""
        d = self.donnees()
        i = d.rang.get(centre)
        if i is None:
            i = next((k for k, n in enumerate(d.noeuds) if n.tache == centre), None)
        if i is None:
            return {"noeuds": [], "liens": [], "total": 0, "tronque": False, "centre": None}
        profondeur = min(max(profondeur, 1), 2)
        dist = {i: 0}
        file = deque([i])
        while file:
            k = file.popleft()
            if dist[k] < profondeur:
                for v in d.noeuds[k].voisins:
                    if v not in dist:
                        dist[v] = dist[k] + 1
                        file.append(v)
        # Au-delà du plafond : les plus proches, puis les plus reliés.
        garde = sorted(dist, key=lambda k: (dist[k], -len(d.noeuds[k].voisins), d.noeuds[k].id))
        sortie = self._servir(d, garde, limite)
        sortie["centre"] = d.noeuds[i].id
        return sortie

    def global_(self, casquette: str = "", projet: str = "", genre: str = "", type_: str = "",
                tag: str = "", jours: int = 0, limite: int = PLAFOND) -> dict:
        d = self.donnees()
        seuil = (time.time() - jours * 86400) * 1e9 if jours > 0 else None
        genres = {g for g in genre.split(",") if g in GENRES}
        tag = tag.casefold()

        def garde(n: Noeud) -> bool:
            return ((not casquette or n.casquette == casquette)
                    and (not projet or n.projet == projet or n.projet.startswith(projet + "/"))
                    and (not genres or n.genre in genres)
                    and (not type_ or n.type == type_)
                    and (not tag or tag in n.tags)
                    and (seuil is None or n.maj >= seuil))

        retenus = [k for k, n in enumerate(d.noeuds) if garde(n)]
        retenus.sort(key=lambda k: (-len(d.noeuds[k].voisins), d.noeuds[k].id))
        return self._servir(d, retenus, limite)

    def facettes(self) -> dict:
        d = self.donnees()
        tags: dict[str, int] = {}
        for n in d.noeuds:
            for t in n.tags:
                tags[t] = tags.get(t, 0) + 1
        conts = [n for n in d.noeuds if n.genre == "conteneur"]
        return {"casquettes": sorted({n.casquette for n in d.noeuds if n.casquette}),
                "projets": sorted(({"id": n.projet, "titre": n.titre} for n in conts),
                                  key=lambda x: x["id"].casefold()),
                "types": sorted({n.type for n in d.noeuds if n.type}),
                "tags": sorted(tags, key=lambda t: (-tags[t], t))[:100],
                "total": len(d.noeuds), "aretes": len(d.aretes)}

    @staticmethod
    def _servir(d: Donnees, ordre: list[int], limite: int) -> dict:
        # INV-GRAPHE-2 : jamais plus de PLAFOND nœuds envoyés au navigateur.
        limite = min(max(limite, 1), PLAFOND)
        garde = ordre[:limite]
        pos = {k: j for j, k in enumerate(garde)}
        noeuds = [{"id": n.id, "titre": n.titre, "genre": n.genre, "type": n.type,
                   "projet": n.projet, "casquette": n.casquette, "tache": n.tache,
                   "degre": len(n.voisins)} for n in (d.noeuds[k] for k in garde)]
        liens = [[pos[a], pos[b], g] for a, b, g in d.aretes if a in pos and b in pos]
        return {"noeuds": noeuds, "liens": liens, "total": len(ordre),
                "tronque": len(ordre) > len(garde)}
