"""Bases (étape a) : un dossier du vault vu comme une table — une note par ligne, les propriétés
de son frontmatter pour colonnes.

Rôle : lire les notes d'un dossier (non récursif), inférer le type de chaque colonne, filtrer,
trier, regrouper et agréger. Le calcul (`calculer`) est pur, séparé de la lecture (`lire`) : les
étapes suivantes (édition de cellules, relations par wikilinks, import) s'y greffent sans refonte ;
un type de colonne se déclare une fois au registre `TYPES` (reconnaissance, clé de tri, filtres,
agrégats).
Frontières : ne connaît pas HTTP (route : `api_bases.py`) ; reçoit un dossier déjà contrôlé par
`notes.chemin_sur` ; lit le frontmatter par `fiches.frontmatter`, n'écrit jamais rien.
Invariants portés : INV-BASES-1 (lecture seule, confinement au vault, plafond de lignes),
INV-VAULT-1 (frontmatter jamais reformaté : lu, jamais réécrit).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import fiches, langues, notes
from .vault import Invalide

PLAFOND = 5000  # INV-BASES-1 : au-delà, les premières notes par nom, `tronque` vrai
DATE = re.compile(r"\d{4}-\d{2}-\d{2}([T ][\d:.+-]+)?$")
LIEN = re.compile(r"\[\[[^\[\]\n]+\]\]$")
COMMUNS = ("compte", "distincts")


def vide(v) -> bool:
    return v is None or v == "" or v == []


def texte(v) -> str:
    """Forme textuelle d'une valeur : recherche « contient », égalité, clé de groupe."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(texte(x) for x in v)
    return str(v)


@dataclass(frozen=True)
class Type:
    nom: str
    reconnait: Callable[[object], bool]
    cle: Callable[[object], object]  # tri et comparaisons ≥ / ≤
    ops: frozenset[str]
    agregats: tuple[str, ...]


def _nombre(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# Ordre = priorité d'inférence : le premier type qui reconnaît toutes les valeurs présentes l'emporte.
TYPES: dict[str, Type] = {t.nom: t for t in (
    Type("case", lambda v: isinstance(v, bool), lambda v: v, frozenset({"="}), (*COMMUNS, "cochees")),
    Type("nombre", _nombre, float, frozenset({"=", ">=", "<="}), (*COMMUNS, "somme", "moyenne", "min", "max")),
    Type("date", lambda v: isinstance(v, str) and bool(DATE.match(v)), lambda v: v[:10],
         frozenset({"=", ">=", "<=", "contient"}), (*COMMUNS, "min", "max")),
    Type("lien", lambda v: isinstance(v, str) and bool(LIEN.match(v)), lambda v: v.casefold(),
         frozenset({"=", "contient"}), COMMUNS),
    Type("liste", lambda v: isinstance(v, list), lambda v: texte(v).casefold(),
         frozenset({"a", "contient"}), COMMUNS),
    Type("texte", lambda v: True, lambda v: texte(v).casefold(), frozenset({"=", "contient"}), COMMUNS),
)}


def inferer(valeurs: list) -> str:
    presentes = [v for v in valeurs if not vide(v)]
    return next(t.nom for t in TYPES.values() if all(t.reconnait(v) for v in presentes))


# --- lecture --------------------------------------------------------------------------------------
def lire(dossier: Path, rel: str, motifs: list[str], plafond: int = PLAFOND) -> tuple[list[dict], int]:
    """(lignes, nombre de notes du dossier). Non récursif ; caché, exclu ou lien symbolique : ignoré
    (INV-NOTE-1). Lecture seule (INV-BASES-1)."""
    noms = sorted(e.name for e in os.scandir(dossier)
                  if e.name.lower().endswith(".md") and not e.name.startswith(".")
                  and e.is_file(follow_symlinks=False)
                  and not notes.exclu(f"{rel}/{e.name}" if rel else e.name, motifs))
    lignes = []
    for nom in noms[:plafond]:
        try:
            fm = fiches.frontmatter(fiches.lire(dossier / nom))
        except OSError:
            continue  # disparue entre le parcours et la lecture
        titre = fm.get("titre") or fm.get("title") or nom[:-3]
        lignes.append({"chemin": f"{rel}/{nom}" if rel else nom, "titre": texte(titre), "valeurs": fm})
    return lignes, len(noms)


# --- calcul pur -----------------------------------------------------------------------------------
def colonnes(lignes: list[dict]) -> list[dict]:
    noms: dict[str, None] = {}
    for l in lignes:
        noms.update(dict.fromkeys(map(str, l["valeurs"])))
    sortie = []
    for nom in noms:
        typ = inferer([l["valeurs"].get(nom) for l in lignes])
        c = {"nom": nom, "type": typ, "agregats": list(TYPES[typ].agregats)}
        if typ == "liste":  # choix du filtre « valeur de liste »
            elems = {texte(x) for l in lignes for x in (l["valeurs"].get(nom) or [])}
            c["valeurs"] = sorted(elems, key=str.casefold)[:200]
        sortie.append(c)
    return sortie


def _valeur(ligne: dict, col: str):
    v = ligne["valeurs"].get(col)
    return ligne["titre"] if v is None and col == "titre" else v


def _types(cols: list[dict]) -> dict[str, Type]:
    return {**{"titre": TYPES["texte"]}, **{c["nom"]: TYPES[c["type"]] for c in cols}}


def _passe(v, typ: Type, op: str, cible) -> bool:
    if vide(v):
        return False
    if op == "contient":
        return str(cible).casefold() in texte(v).casefold()
    if op == "a":
        return any(texte(x).casefold() == str(cible).casefold() for x in v)
    if typ.nom == "case":
        return v is (cible in (True, "true", "oui", "1", 1))
    try:
        a, b = typ.cle(v), typ.cle(cible)
    except (TypeError, ValueError):
        raise Invalide(langues.t("serveur.bases.valeur_invalide", valeur=cible)) from None
    return a == b if op == "=" else a >= b if op == ">=" else a <= b


def filtrer(lignes: list[dict], cols: list[dict], filtres: list[dict]) -> list[dict]:
    types = _types(cols)
    for f in filtres:
        col, op = f.get("colonne"), f.get("op")
        typ = types.get(col)
        if typ is None or op not in typ.ops:
            raise Invalide(langues.t("serveur.bases.filtre_invalide", colonne=col, op=op))
        lignes = [l for l in lignes if _passe(_valeur(l, col), typ, op, f.get("valeur"))]
    return lignes


def trier(lignes: list[dict], cols: list[dict], tri: str) -> list[dict]:
    """`tri` : « colonne » croissant, « -colonne » décroissant ; valeurs absentes toujours en fin."""
    col, decroissant = tri.removeprefix("-"), tri.startswith("-")
    typ = _types(cols).get(col)
    if not tri or typ is None:
        return lignes
    presentes = [l for l in lignes if not vide(_valeur(l, col))]
    presentes.sort(key=lambda l: typ.cle(_valeur(l, col)), reverse=decroissant)
    return presentes + [l for l in lignes if vide(_valeur(l, col))]


def agreger(lignes: list[dict], cols: list[dict]) -> dict[str, dict]:
    sortie = {}
    for c in cols:
        vals = [v for l in lignes if not vide(v := l["valeurs"].get(c["nom"]))]
        elems = [x for v in vals for x in v] if c["type"] == "liste" else vals
        a = {"compte": len(vals), "distincts": len({texte(x).casefold() for x in elems})}
        if c["type"] == "case":
            a["cochees"] = sum(v is True for v in vals)
        if c["type"] == "nombre":
            a |= {"somme": sum(vals), "moyenne": sum(vals) / len(vals) if vals else None}
        if c["type"] in ("nombre", "date"):
            cle = TYPES[c["type"]].cle
            a |= {"min": min(vals, key=cle, default=None), "max": max(vals, key=cle, default=None)}
        sortie[c["nom"]] = a
    return sortie


def regrouper(lignes: list[dict], cols: list[dict], groupe: str) -> list[dict]:
    """Groupes dans l'ordre de leur valeur (absente en dernier) ; `lignes` = indices dans `lignes`."""
    typ = _types(cols).get(groupe)
    if typ is None:
        raise Invalide(langues.t("serveur.bases.colonne_inconnue", colonne=groupe))
    par: dict[str | None, dict] = {}
    for i, l in enumerate(lignes):
        v = _valeur(l, groupe)
        k = None if vide(v) else texte(v)
        par.setdefault(k, {"valeur": v if k is not None else None, "lignes": [], "_cle": v})["lignes"].append(i)
    ordre = sorted((g for k, g in par.items() if k is not None), key=lambda g: typ.cle(g["_cle"]))
    ordre += [par[None]] if None in par else []
    for g in ordre:
        del g["_cle"]
        g["agregats"] = agreger([lignes[i] for i in g["lignes"]], cols)
    return ordre


def calculer(lignes: list[dict], filtres: list[dict] | None = None, tri: str = "",
             groupe: str = "") -> dict:
    """Table servie : colonnes typées (sur toutes les lignes lues), lignes filtrées et triées,
    agrégats par colonne et, si `groupe`, par groupe."""
    cols = colonnes(lignes)
    garde = trier(filtrer(lignes, cols, filtres or []), cols, tri)
    return {"colonnes": cols, "lignes": garde, "filtrees": len(garde), "agregats": agreger(garde, cols),
            "groupes": regrouper(garde, cols, groupe) if groupe else None}


def table(dossier: Path, rel: str, motifs: list[str], filtres: list[dict] | None = None,
          tri: str = "", groupe: str = "", plafond: int = PLAFOND) -> dict:
    lignes, total = lire(dossier, rel, motifs, plafond)
    return {"dossier": rel, "total": total, "tronque": total > plafond, "plafond": plafond,
            **calculer(lignes, filtres, tri, groupe)}
