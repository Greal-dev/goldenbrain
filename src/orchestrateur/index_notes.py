"""Index des notes en mémoire (lot 6) : recherche plein texte, résolution, liens entrants.

Rôle : savoir quels fichiers existent (pour résoudre les liens), retrouver une note par mots,
lister ses liens entrants. Distinct de `Vault.index` (tâches), qu'il n'alourdit pas.
Frontières : lecture seule ; appelé hors de la boucle d'événements (`asyncio.to_thread`) ;
n'écrit rien ; ne relit que les fichiers dont (mtime_ns, taille) a changé.
Invariants portés : INV-NOTE-1 (aucun lien symbolique ni jonction suivi au balayage ; dossiers
exclus ignorés), INV-NOTE-4 (mentions non liées), INV-GRAPHE-1 (`generation` avance à chaque
changement de l'index : le graphe en cache se périme).
"""

from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import fiches
from .notes import cibles, cle_nom, exclu, iso, liens_bruts, meta_rapide, nom_de, resoudre

TAILLE_INDEXEE = 2_000_000  # au-delà, seul le début d'une note est indexé (mémoire bornée)
COMBINANTS = re.compile("[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]")
TERMES = re.compile(r'"([^"]+)"|(\S+)')
# Tags du frontmatter, lus sur le texte normalisé (minuscules, sans accents) : liste en ligne ou bloc.
TAGS = re.compile(r"^tags:[ \t]*(?:\[([^\]\n]*)\]|\n((?:[ \t]*- [^\n]*\n)+))", re.M)
MENTION_MIN = 4  # un titre plus court (« IA », « Note ») se trouverait partout


def normaliser(texte: str) -> str:
    """Sans casse ni accents ; garde les sauts de ligne (numéros de ligne des extraits)."""
    return COMBINANTS.sub("", unicodedata.normalize("NFKD", texte.casefold()))


def _tags(texte: str) -> tuple[str, ...]:
    tete = texte.removeprefix(fiches.BOM)
    fin = tete.find("\n---", 3) if tete.startswith("---") else -1
    if fin < 0 or not (m := TAGS.search(tete, 0, fin + 1)):
        return ()
    if m.group(1) is not None:
        brut = m.group(1).split(",")
    else:
        brut = [x.strip().removeprefix("-") for x in m.group(2).splitlines()]
    return tuple(t for x in brut if (t := x.strip().strip("\"'#")))


@dataclass(slots=True)
class Entree:
    cle: tuple[int, int]          # (mtime_ns, taille)
    titre: str
    type: str
    entete: str                   # titre et nom normalisés
    texte: str                    # contenu normalisé
    liens: tuple[str, ...]        # cibles des liens sortants


class IndexNotes:
    def __init__(self, racine: Path, motifs: list[str], ttl_s: float = 5):
        self.racine = Path(racine).resolve()
        self.motifs = list(motifs)
        self.ttl_s = ttl_s
        self.notes: dict[str, Entree] = {}
        self.autres: dict[str, int] = {}            # fichiers non-md : chemin -> taille
        self.chemins: dict[str, str] = {}           # minuscules -> chemin (notes et fichiers)
        self.par_nom: dict[str, set[str]] = {}      # cle_nom -> chemins
        self.cites: dict[str, set[str]] = {}        # cle_nom d'une cible -> notes qui la citent
        self.relus = 0                              # notes relues depuis le disque (mesure)
        self.generation = 0                         # INV-GRAPHE-1 : avance à chaque changement
        self.balaye: float | None = None
        # Ordre de prise : `_balayage` puis `_verrou`. Le balayage disque se fait hors de
        # `_verrou` : un listage n'attend jamais un rafraîchissement, seulement la construction.
        self._verrou = threading.RLock()
        self._balayage = threading.Lock()
        self._en_fond = False

    # --- tenue de l'index -------------------------------------------------------------------
    def _perime(self) -> bool:
        return self.balaye is None or time.monotonic() - self.balaye >= self.ttl_s

    def perimer(self) -> None:
        """Après un déplacement de dossiers : le prochain accès rebalaye (incrémental)."""
        self.balaye = None

    def assurer(self) -> None:
        """Balayage incrémental si l'index n'existe pas ou date de plus de `ttl_s`."""
        if self._perime():
            self.rafraichir(si_perime=True)

    def demarrer(self) -> None:
        """Construction initiale en fond, dès le démarrage du serveur."""
        self._en_fond = True
        threading.Thread(target=self._fond, daemon=True, name="index-notes").start()

    def assurer_sans_attendre(self) -> None:
        """N'attend que la construction initiale ; un index périmé se rafraîchit en fond."""
        if self.balaye is None:
            self.rafraichir(si_perime=True)
        elif self._perime() and not self._en_fond:
            self._en_fond = True
            threading.Thread(target=self._fond, daemon=True, name="index-notes").start()

    def _fond(self) -> None:
        try:
            self.rafraichir(si_perime=True)
        finally:
            self._en_fond = False

    def rafraichir(self, si_perime: bool = False) -> None:
        with self._balayage:
            if si_perime and not self._perime():
                return  # un autre fil vient de le faire pendant l'attente
            notes, autres = self._balayer()
            with self._verrou:
                for rel in [r for r in self.notes if r not in notes]:
                    self._retirer(rel)
                for rel in [r for r in self.autres if r not in autres]:
                    self._retirer_fichier(rel)
                for rel, taille in autres.items():
                    if rel not in self.autres:
                        self._inscrire(rel)
                    self.autres[rel] = taille
                changes = [r for r, cle in notes.items()
                           if (e := self.notes.get(r)) is None or e.cle != cle]
            # Lectures en parallèle : l'antivirus inspecte chaque ouverture (≈ 7 ms à froid).
            with ThreadPoolExecutor(16) as pool:
                for rel, lu in zip(changes, pool.map(self._charger, changes)):
                    with self._verrou:
                        self._indexer(rel, lu)
            self.balaye = time.monotonic()

    def maj(self, rel: str) -> None:
        """Après une écriture de GoldenBrain : l'index suit tout de suite, sans balayage."""
        if self.balaye is None:
            self.rafraichir(si_perime=True)
            return
        lu = self._charger(rel) if (self.racine / rel).is_file() else None
        with self._verrou:
            if lu is not None or rel in self.notes:
                self._indexer(rel, lu)

    def _balayer(self) -> tuple[dict[str, tuple[int, int]], dict[str, int]]:
        notes, autres = {}, {}
        pile = [(self.racine, "")]
        while pile:
            dossier, prefixe = pile.pop()
            try:
                entrees = list(os.scandir(dossier))
            except OSError:
                continue
            for e in entrees:
                rel = prefixe + e.name
                # INV-NOTE-1 : jamais de lien symbolique ni de jonction suivi, ni de dossier exclu.
                if e.is_symlink() or e.is_junction() or exclu(rel, self.motifs):
                    continue
                if e.is_dir():
                    pile.append((Path(e.path), rel + "/"))
                elif e.is_file():
                    st = e.stat()
                    if e.name.lower().endswith(".md"):
                        notes[rel] = (st.st_mtime_ns, st.st_size)
                    else:
                        autres[rel] = st.st_size
        return notes, autres

    def _inscrire(self, rel: str) -> None:
        self.chemins[rel.lower()] = rel
        self.par_nom.setdefault(cle_nom(rel), set()).add(rel)

    def _retirer_fichier(self, rel: str) -> None:
        self.autres.pop(rel, None)
        self.chemins.pop(rel.lower(), None)
        self.par_nom.get(cle_nom(rel), set()).discard(rel)

    def _retirer(self, rel: str) -> None:
        self.generation += 1
        e = self.notes.pop(rel, None)
        self.chemins.pop(rel.lower(), None)
        self.par_nom.get(cle_nom(rel), set()).discard(rel)
        for cible in e.liens if e else ():
            self.cites.get(cle_nom(cible), set()).discard(rel)

    def _charger(self, rel: str) -> tuple[os.stat_result, str] | None:
        p = self.racine / rel
        try:
            return p.stat(), fiches.lire(p)[:TAILLE_INDEXEE]
        except OSError:
            return None

    def _indexer(self, rel: str, lu: tuple[os.stat_result, str] | None) -> None:
        if lu is None:
            self._retirer(rel)
            return
        st, texte = lu
        self.relus += 1
        self._retirer(rel)
        nom = nom_de(rel)
        titre, type_ = meta_rapide(texte, nom)
        liens = tuple(cibles(texte))
        self.notes[rel] = Entree((st.st_mtime_ns, st.st_size), titre, type_,
                                 normaliser(f"{titre}\n{nom}"), normaliser(texte), liens)
        self._inscrire(rel)
        for cible in liens:
            if cible:
                self.cites.setdefault(cle_nom(cible), set()).add(rel)

    # --- lecture ----------------------------------------------------------------------------
    def resoudre(self, cible: str, depuis: str | None) -> str | None:
        with self._verrou:
            return resoudre(cible, depuis, self.chemins, self.par_nom)

    def _vers(self, cible: str, depuis: str) -> str | None:
        return resoudre(cible, depuis, self.chemins, self.par_nom)

    def _extrait(self, src: str, rel: str) -> str:
        """Ligne du lien dans la source, relue à la demande (l'index ne garde que les cibles)."""
        try:
            texte = fiches.lire(self.racine / src)
        except OSError:
            return ""
        return next((x[6] for x in liens_bruts(texte) if self._vers(x[2], src) == rel), "")

    def citant(self, rel: str) -> set[str]:
        """Notes dont un lien porte le nom de `rel` (candidates à un renommage)."""
        with self._verrou:
            return set(self.cites.get(cle_nom(rel), ()))

    def ref(self, rel: str) -> dict | None:
        e = self.notes.get(rel)
        if e is None:
            return None
        return {"chemin": rel, "nom": nom_de(rel), "titre": e.titre, "type": e.type,
                "maj": iso(e.cle[0])}

    def entrants(self, rel: str) -> list[dict]:
        with self._verrou:
            sortie = []
            for src in sorted(self.cites.get(cle_nom(rel), ())):
                if src == rel:
                    continue
                e = self.notes[src]
                if any(cle_nom(c) == cle_nom(rel) and self._vers(c, src) == rel for c in e.liens):
                    sortie.append({"chemin": src, "titre": e.titre, "extrait": self._extrait(src, rel)})
            return sortie

    def mentions(self, rel: str, limite: int = 30) -> list[dict]:
        """INV-NOTE-4 : notes qui écrivent le titre de `rel` (mot entier, sans casse ni accents)
        sans le lier ; jamais la note elle-même ni une note qui la lie déjà."""
        with self._verrou:
            e = self.notes.get(rel)
            if e is None:
                return []
            termes = {normaliser(e.titre).strip()}
            if nom_de(rel) != "contexte":  # « contexte » est le nom de toutes les fiches de projet
                termes.add(normaliser(nom_de(rel)).strip())
            termes = {t for t in termes if len(t) >= MENTION_MIN}
            motifs = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)") for t in termes]
            liees = {s for s in self.cites.get(cle_nom(rel), ())
                     if any(self._vers(c, s) == rel for c in self.notes[s].liens)}
            trouves = []
            for src, s in self.notes.items():
                if src == rel or src in liees or not any(t in s.texte for t in termes):
                    continue
                if m := next((m for p in motifs if (m := p.search(s.texte))), None):
                    trouves.append((src, s.titre, s.texte.count("\n", 0, m.start()) + 1))
        trouves.sort()
        sortie = []
        for src, titre, n in trouves[:limite]:
            try:  # texte d'origine relu pour l'affichage seulement
                brut = fiches.lire(self.racine / src).removeprefix(fiches.BOM).split("\n")
            except OSError:
                continue
            sortie.append({"chemin": src, "titre": titre,
                           "extrait": brut[n - 1].strip()[:200] if n <= len(brut) else ""})
        return sortie

    def pour_graphe(self) -> list[tuple[str, str, str, int, tuple[str, ...], tuple[str, ...]]]:
        """(chemin, titre, type, mtime_ns, tags, cibles de notes résolues) de chaque note."""
        with self._verrou:
            sortie = []
            for rel, e in self.notes.items():
                cibles_ = {c for x in e.liens if x and (c := self._vers(x, rel)) and c in self.notes
                           and c != rel}
                sortie.append((rel, e.titre, e.type, e.cle[0], _tags(e.texte), tuple(sorted(cibles_))))
            return sortie

    def compter(self) -> dict[str, int]:
        """Nombre de notes par dossier, récursif (clé "" = tout le vault)."""
        with self._verrou:
            compte: dict[str, int] = {}
            for rel in self.notes:
                parts = rel.split("/")[:-1]
                for i in range(len(parts) + 1):
                    k = "/".join(parts[:i])
                    compte[k] = compte.get(k, 0) + 1
            return compte

    def chercher(self, q: str, limite: int = 30, dossier: str = "") -> list[dict]:
        termes = [normaliser(a or b).strip() for a, b in TERMES.findall(q)]
        termes = [t for t in termes if t]
        if not termes:
            return []
        prefixe = dossier + "/" if dossier else ""
        trouves = []
        with self._verrou:
            for rel, e in self.notes.items():
                if not rel.startswith(prefixe):
                    continue
                chemin = normaliser(rel)
                score = 0
                for t in termes:
                    corps = min(e.texte.count(t), 5)
                    poids = 10 * (t in e.entete) + 3 * (t in chemin) + corps
                    if not poids:
                        break
                    score += poids
                else:
                    trouves.append((-score, rel, e))
        trouves.sort(key=lambda x: (x[0], x[1]))
        return [{"chemin": rel, "titre": e.titre, "extraits": self._extraits(rel, e, termes),
                 "score": -s} for s, rel, e in trouves[:limite]]

    def _extraits(self, rel: str, e: Entree, termes: list[str]) -> list[dict]:
        lignes: list[int] = []
        for t in termes:
            debut = 0
            while len(lignes) < 3 and (i := e.texte.find(t, debut)) >= 0:
                n = e.texte.count("\n", 0, i) + 1
                if n not in lignes:
                    lignes.append(n)
                debut = e.texte.find("\n", i) + 1 or len(e.texte)
        if not lignes:
            return []
        try:  # le texte d'origine (accents, casse) est relu pour l'affichage seulement
            brut = fiches.lire(self.racine / rel).removeprefix(fiches.BOM).split("\n")
        except OSError:
            return []
        return [{"ligne": n, "texte": brut[n - 1].strip()[:200]}
                for n in sorted(lignes) if n <= len(brut)]
