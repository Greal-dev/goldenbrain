"""Réécriture des références à des chemins déplacés (dossiers ou fichiers) dans un texte.

Rôle : moteur autonome, réutilisable pour un dossier (lot 5) comme pour une note (lot 6) :
`reecrire` (fonction pure, un texte) et `planifier` (balayage du vault, lecture seule).
Frontières : aucune dépendance au reste du paquet ; `reecrire` n'accède jamais au disque
(l'existence des cibles vient d'un ensemble fourni) ; `planifier` lit, n'écrit rien.
Règles (docs/ARCHITECTURE.md, lot 5) : 1. chemin relatif à la racine, délimité, `/` ou `\\` ;
2. chemin absolu sous la racine du vault ; 3. liens relatifs `./` `../` recalculés depuis le
nouvel emplacement ; 4. wikilinks par simple nom jamais touchés. Dans le doute (préfixe de
nom ambigu, casse différente, cible hors vault), rien n'est réécrit et un avertissement est
émis : une réécriture fausse corrompt une note, une omission se corrige à la main.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import langues

EXTENSIONS = frozenset({".md", ".base", ".canvas", ".json", ".py", ".toml", ".yaml"})
DOSSIERS_EXCLUS = frozenset({".git", ".obsidian", ".claude"})
RACINES_EXCLUES = frozenset({"Archives"})
EXEMPLES_MAX = 3

# Séparateur d'un chemin écrit : `\\` (JSON, Python) avant `\` seul, ou `/`.
SEP = r"(?:\\\\|/|\\)"
# Un caractère qui prolonge un chemin à gauche : une occurrence ainsi précédée appartient à un
# AUTRE chemin (sous-dossier homonyme, URL, lien relatif) et n'est pas de la règle 1.
AVANT_CHEMIN = r"\w.\-~/\\@%+&$"
LIEN = re.compile(r"\[\[(?P<w>[^\[\]\r\n]+)\]\]|\]\((?P<m>[^()\r\n]*)\)")
RELATIF = re.compile(r"\.\.?/")
ALIAS = re.compile(r"(?P<p>[^#|]*?)(?P<r>\\?[#|].*)?", re.S)


type Deplacements = list[tuple[str, str]]


def normaliser(chemin: str) -> str:
    """Chemin relatif à la racine, séparateurs `/` ; refuse tout chemin qui en sortirait."""
    c = posixpath.normpath(chemin.replace("\\", "/").strip("/"))
    if c in ("", ".") or c == ".." or c.startswith("../") or ":" in c.split("/")[0]:
        raise ValueError(f"chemin relatif à la racine attendu : {chemin}")
    return c


def _regle(chemin: str, deplacements: Deplacements) -> tuple[str, str] | None:
    # Le `de` le plus long qui contient le chemin l'emporte (déplacements simultanés).
    choix = None
    for de, vers in deplacements:
        if (chemin == de or chemin.startswith(de + "/")) and (not choix or len(de) > len(choix[0])):
            choix = (de, vers)
    return choix


def nouveau_chemin(chemin: str, deplacements: Deplacements) -> str:
    """Emplacement d'un chemin (relatif à la racine, `/`) après les déplacements."""
    r = _regle(chemin, deplacements)
    return r[1] + chemin[len(r[0]):] if r else chemin


class Existants:
    """Chemins (fichiers et dossiers) présents dans le vault, relatifs à la racine, `/`."""

    def __init__(self, chemins):
        self.chemins = set(chemins)
        self._plis = {c.casefold() for c in self.chemins}
        self._noms: dict[str, list[str]] = defaultdict(list)
        for c in self.chemins:
            self._noms[posixpath.dirname(c)].append(posixpath.basename(c))
        self._prolong: dict[str, list[str]] = {}

    def __contains__(self, chemin: str) -> bool:
        return chemin in self.chemins

    def casse_differente(self, chemin: str) -> bool:
        return chemin not in self.chemins and chemin.casefold() in self._plis

    def prolongements(self, de: str) -> list[str]:
        """Suites possibles d'un nom voisin plus long : `Mon Projet` -> [` 2`] si `Mon Projet 2`."""
        if de not in self._prolong:
            base = posixpath.basename(de)
            suites = [n[len(base):] for n in self._noms[posixpath.dirname(de)]
                      if len(n) > len(base) and n.startswith(base)]
            # Un wikilink omet `.md` : `[[…/note 2]]` prolonge `note` comme `note 2.md`.
            self._prolong[de] = suites + [s[:-3] for s in suites if s.endswith(".md") and s[:-3]]
        return self._prolong[de]


def _motif_segment(seg: str) -> str:
    # Un espace peut être encodé `%20` dans une cible de lien Markdown.
    return "".join("(?: |%20)" if ch == " " else re.escape(ch) for ch in seg)


def _formes_racine(racine: str) -> list[str]:
    """Écritures d'un chemin absolu de la racine : `C:\\…`, `C:/…`, `/c/…`, `~/…`."""
    p = Path(racine).as_posix().rstrip("/")
    formes = []
    if m := re.fullmatch(r"([A-Za-z]):/(.*)", p):
        reste = [s for s in m.group(2).split("/") if s]
        formes += [m.group(1) + ":" + "".join(SEP + re.escape(s) for s in reste),
                   "/" + m.group(1) + "".join(SEP + re.escape(s) for s in reste)]
    else:
        formes.append("".join(SEP + re.escape(s) for s in p.split("/") if s))
    try:
        sous_maison = Path(racine).resolve().relative_to(Path.home().resolve()).parts
        formes.append("~" + "".join(SEP + re.escape(s) for s in sous_maison))
    except (ValueError, OSError):
        pass
    return formes


@lru_cache(maxsize=32)
def _compiler(deplacements: tuple[tuple[str, str], ...], racine: str):
    variantes = []  # (de écrit, de réel, vers écrit) : un `de` fichier `.md` vaut aussi sans `.md`
    for de, vers in deplacements:
        variantes.append((de, de, vers))
        if de.endswith(".md") and vers.endswith(".md"):
            variantes.append((de[:-3], de, vers[:-3]))
    variantes.sort(key=lambda v: -len(v[0]))
    alternatives = "|".join(f"(?P<d{i}>" + SEP.join(_motif_segment(s) for s in v[0].split("/"))
                            + ")" for i, v in enumerate(variantes))
    absolu = "|".join(_formes_racine(racine))
    corps = (rf"(?:(?<!\w)(?P<abs>(?i:{absolu}))(?P<asep>{SEP})|(?<![{AVANT_CHEMIN}]))"
             rf"(?:{alternatives})(?![\w\-]|\.\w)")
    return re.compile(corps), re.compile(corps, re.I), variantes


def _separateur(texte: str) -> str:
    m = re.search(SEP, texte)
    return m.group(0) if m else "/"


def _chemins(texte: str, regles, existants, occ, avert, ou: str, encoder: bool) -> str:
    """Règles 1 et 2 sur un fragment de texte (hors lien relatif)."""
    motif, _, variantes = regles

    def remplacer(m: re.Match) -> str:
        i = next(int(k[1:]) for k, v in m.groupdict().items() if k[0] == "d" and v is not None)
        ecrit, de, vers = variantes[i]
        trouve = m.group(f"d{i}")
        if m.group("abs") is None and "/" not in ecrit:
            return m.group(0)  # règle 4 : un nom seul n'est pas un chemin
        suite = texte[m.end():]
        if existants is not None and any(suite.startswith(x) for x in existants.prolongements(ecrit)):
            avert.append(langues.t("serveur.references.autre_dossier", ou=ou, texte=f"{trouve}{suite[:20]}"))
            return m.group(0)
        sep = _separateur(trouve) if "/" in ecrit else (m.group("asep") or "/")
        nouveau = vers.replace("/", sep)
        if encoder or "%20" in trouve:
            nouveau = nouveau.replace(" ", "%20")
        occ.append((trouve, nouveau))
        return m.group(0)[:m.start(f"d{i}") - m.start()] + nouveau

    return motif.sub(remplacer, texte)


def _relatif(chemin: str, source: str, deplacements: Deplacements, existants, avert, ou: str,
             wiki: bool) -> str | None:
    """Règle 3 : nouveau texte du lien relatif `chemin`, ou None s'il ne change pas."""
    brut = chemin if wiki else chemin.replace("%20", " ")
    cible = posixpath.normpath(posixpath.join(posixpath.dirname(source), brut))
    if cible in (".", "..") or cible.startswith("../"):
        return None  # sort du vault : rien à recalculer
    reelle = cible
    if existants is not None and cible not in existants:
        if wiki and not posixpath.splitext(cible)[1] and cible + ".md" in existants:
            reelle = cible + ".md"
        else:
            if existants.casse_differente(cible) or existants.casse_differente(cible + ".md"):
                avert.append(langues.t("serveur.references.casse_lien", ou=ou, lien=chemin))
            return None  # lien cassé : laissé tel quel
    r_source, r_cible = _regle(source, deplacements), _regle(reelle, deplacements)
    if r_source == r_cible:
        return None  # ni l'un ni l'autre ne bouge, ou les deux bougent ensemble
    # Chemins ancrés sur `/` : relpath ne doit rien emprunter au dossier courant du processus.
    apres = posixpath.relpath("/" + nouveau_chemin(reelle, deplacements),
                              "/" + posixpath.dirname(nouveau_chemin(source, deplacements)))
    if reelle != cible:
        apres = apres[:-3]
    if not apres.startswith("../"):
        apres = "./" + apres  # sans préfixe, Obsidian lirait un chemin depuis la racine
    if brut.endswith("/"):
        apres += "/"
    return apres if wiki else apres.replace(" ", "%20")


def reecrire(texte: str, chemin_du_fichier_avant: str, deplacements: Deplacements,
             racine: str | Path, *, existants: Existants | set | None = None,
             avertissements: list[str] | None = None) -> tuple[str, list[tuple[str, str]]]:
    """Texte réécrit et occurrences `(avant, après)` remplacées.

    `deplacements` : couples `(de, vers)` relatifs à la racine (dossiers ou fichiers),
    simultanés. `existants` : chemins présents (sans lui, toute cible relative est réputée
    exister). `avertissements` : liste complétée des occurrences douteuses laissées intactes.
    """
    deps = tuple(sorted((normaliser(de), normaliser(vers)) for de, vers in deplacements))
    if not deps:
        return texte, []
    if existants is not None and not isinstance(existants, Existants):
        existants = Existants(existants)
    avert = avertissements if avertissements is not None else []
    source = normaliser(chemin_du_fichier_avant)
    regles = _compiler(deps, str(racine))
    occ: list[tuple[str, str]] = []
    morceaux, pos = [], 0
    for m in LIEN.finditer(texte):
        morceaux.append(_chemins(texte[pos:m.start()], regles, existants, occ, avert, source,
                                 False))
        pos = m.end()
        wiki = m.group("w") is not None
        interieur = m.group("w") if wiki else m.group("m")
        if wiki:
            a = ALIAS.fullmatch(interieur)
            chemin, reste = a.group("p"), a.group("r") or ""
        elif interieur.startswith("<"):
            fin = interieur.find(">")
            chemin, reste = (interieur[1:fin], interieur[fin:]) if fin > 0 else (interieur, "")
        else:
            chemin, _, reste = interieur.partition(" ")
            reste = (" " + reste) if _ else ""
            if "#" in chemin:
                chemin, ancre = chemin.split("#", 1)
                reste = "#" + ancre + reste
        tete = "<" if not wiki and interieur.startswith("<") else ""
        if RELATIF.match(chemin):
            nouveau = _relatif(chemin, source, deps, existants, avert, source, wiki)
            if nouveau is not None:
                if tete:
                    nouveau = nouveau.replace("%20", " ")
                occ.append((chemin, nouveau))
                chemin = nouveau
        else:
            chemin = _chemins(chemin, regles, existants, occ, avert, source,
                              encoder=not wiki and not tete)
        morceaux.append(("[[" if wiki else "](") + tete + chemin + reste + ("]]" if wiki else ")"))
    morceaux.append(_chemins(texte[pos:], regles, existants, occ, avert, source, False))
    nouveau_texte = "".join(morceaux)
    _casse(texte, regles, source, avert)
    return nouveau_texte, occ


def _casse(texte: str, regles, ou: str, avert: list[str]) -> None:
    # Une occurrence qui ne diffère d'un `de` que par la casse est douteuse : signalée.
    _, sans_casse, variantes = regles
    for m in sans_casse.finditer(texte):
        i = next(int(k[1:]) for k, v in m.groupdict().items() if k[0] == "d" and v is not None)
        if m.group("abs") is None and "/" not in variantes[i][0]:
            continue  # règle 4 : un nom seul n'est pas un chemin
        trouve = re.sub(SEP, "/", m.group(f"d{i}")).replace("%20", " ")
        if trouve != variantes[i][0]:
            avert.append(langues.t("serveur.references.casse_differe", ou=ou, texte=m.group(f"d{i}"), attendu=variantes[i][0]))


def compter(texte: str, deplacements: Deplacements, racine: str | Path) -> int:
    """Occurrences des règles 1 et 2 dans un texte hors vault (jamais réécrit)."""
    deps = tuple(sorted((normaliser(de), normaliser(vers)) for de, vers in deplacements))
    occ: list = []
    _chemins(texte, _compiler(deps, str(racine)), None, occ, [], "", False)
    return len(occ)


@dataclass
class Reecriture:
    fichier: str  # relatif à la racine, emplacement AVANT déplacement
    lignes: int
    exemples: list[tuple[str, str]]
    occurrences: list[tuple[str, str]]
    mtime_ns: int
    taille: int
    avertissements: list[str] = field(default_factory=list)


def _exclu(rel: str, exclure) -> bool:
    return any(fnmatch.fnmatch(rel, m) for m in exclure)


def inventaire(racine: str | Path, exclure=()) -> tuple[Existants, list[str]]:
    """Une passe sur le vault : chemins existants, et fichiers texte à examiner."""
    chemins, a_lire = [], []
    pile = [(str(racine), "")]
    while pile:
        dossier, rel_d = pile.pop()
        try:
            entrees = list(os.scandir(dossier))
        except OSError:
            continue
        haut = rel_d.split("/")[0]
        examine = not (set(rel_d.split("/")) & DOSSIERS_EXCLUS) and haut not in RACINES_EXCLUES
        for e in entrees:
            rel = f"{rel_d}/{e.name}" if rel_d else e.name
            # L'entrée du dossier dit déjà « lien ? dossier ? » : aucun appel système par fichier.
            if e.is_dir():
                if e.name != ".git" and not e.is_symlink():
                    chemins.append(rel)
                    pile.append((e.path, rel))
                continue
            chemins.append(rel)
            if examine and os.path.splitext(e.name)[1].lower() in EXTENSIONS \
                    and not _exclu(rel, exclure) and not e.is_symlink():
                a_lire.append(rel)
    return Existants(chemins), sorted(a_lire)


def _cles(deplacements) -> set[bytes] | None:
    """Noms déplacés en octets minuscules (et `%20`) ; None si l'un n'est pas ASCII."""
    cles = set()
    for de, _ in deplacements:
        nom = posixpath.basename(de).removesuffix(".md")
        if not nom.isascii():
            return None  # minuscules d'octets ≠ casse Unicode : pas de pré-filtre sûr
        cles |= {nom.lower().encode(), nom.lower().replace(" ", "%20").encode()}
    return cles


def lire_candidats(chemins: list[str], deplacements, toujours=frozenset(), fils: int = 16):
    """`(chemin, octets, stat)` des fichiers qui peuvent citer un déplacé, lus en parallèle
    (`(chemin, None, OSError)` si illisible). Un fichier hors de `toujours` qui ne contient,
    en octets et sans casse, le nom d'aucun déplacé n'est ni décodé ni analysé : tout chemin
    réécrit, absolu ou relatif, nomme le dossier ou le fichier déplacé qu'il traverse."""
    cles = _cles(deplacements)

    def lire(c: str):
        try:
            with open(c, "rb") as f:
                octets, st = f.read(), os.fstat(f.fileno())
        except OSError as e:
            return c, None, e
        if cles is not None and c not in toujours:
            bas = octets.lower()
            if not any(k in bas for k in cles):
                return None
        return c, octets, st

    # Fils : l'antivirus inspecte chaque ouverture (≈ 7 ms à froid sous Windows).
    with ThreadPoolExecutor(fils) as pool:
        yield from filter(None, pool.map(lire, chemins))


def planifier(racine: str | Path, deplacements: Deplacements, exclure=(),
              avertissements: list[str] | None = None,
              inventaire_: tuple[Existants, list[str]] | None = None) -> list[Reecriture]:
    """Balaye le vault une fois et calcule les réécritures, sans rien écrire."""
    racine = Path(racine)
    deps = [(normaliser(de), normaliser(vers)) for de, vers in deplacements]
    avert = avertissements if avertissements is not None else []
    existants, a_lire = inventaire_ or inventaire(racine, exclure)
    noms = {posixpath.basename(de).removesuffix(".md").casefold() for de, _ in deps}
    noms |= {n.replace(" ", "%20") for n in noms}  # cible de lien Markdown encodée
    resultat = []
    absolus = {os.path.join(str(racine), rel): rel for rel in a_lire}
    deplaces = frozenset(a for a, rel in absolus.items() if _regle(rel, deps) is not None)
    for a, octets, st in lire_candidats(list(absolus), deps, deplaces):
        rel = absolus[a]
        if octets is None:
            avert.append(langues.t("serveur.references.illisible", chemin=rel, raison=st))
            continue
        deplace = a in deplaces
        try:
            texte = octets.decode("utf-8")
        except UnicodeDecodeError:
            pli = octets.decode("latin-1").casefold()
            if deplace or any(n in pli for n in noms):
                avert.append(langues.t("serveur.references.non_decodable", chemin=rel))
            continue
        pli = texte.casefold()
        if not deplace and not any(n in pli for n in noms):
            continue  # ni déplacé ni citant un nom déplacé : aucune référence possible
        propres: list[str] = []
        nouveau, occ = reecrire(texte, rel, deps, racine, existants=existants,
                                avertissements=propres)
        avert.extend(propres)
        if nouveau == texte:
            continue
        changees = [(a.strip(), b.strip()) for a, b in
                    zip(texte.splitlines(), nouveau.splitlines()) if a != b]
        resultat.append(Reecriture(rel, len(changees), [(a[:200], b[:200]) for a, b in
                                                        changees[:EXEMPLES_MAX]],
                                   occ, st.st_mtime_ns, st.st_size, propres))
    return resultat
