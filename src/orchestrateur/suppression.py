"""Suppression définitive d'une tâche ou d'un projet, sur geste humain.

Rôle : décrire ce qu'une suppression emporterait (`apercu`), puis effacer la tâche ou le projet :
descendants effacés avec lui ou déplacés vers un autre emplacement, références nettoyées chez les
tâches restantes (`parent:`, liens, livrables), états du moteur qui la visent retirés, trace au journal
`<données>/journal/suppressions.jsonl`. D'un projet, seuls `contexte.md` et les fichiers de tâches
s'effacent ; tout autre fichier est rangé intact sous `Archives/supprimes/<date>/<chemin>`.
Frontières : écrit le vault par `fiches`, `Vault._deplacer` et l'`Aligneur` (fichiers ranges_, dossiers
de sous-projets déplacés, références réécrites) ; ne lance aucun tour ; le refus d'un agent (403) est
tenu par `api_suppression`.
Invariants portés : INV-SUPPR-1 (geste humain, tout ou rien, jamais d'effacement d'un fichier qui
n'est pas une tâche ou le contexte du projet, refus si un tour est en cours ou en file), INV-VAULT-2
(jamais d'écrasement), INV-ALIGN-2 (sous le verrou du moteur).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from . import arbre, fiches, langues, liens, references, transformations
from .vault import Conflit, Invalide, aujourdhui, nettoyer_lien

MODES = ("supprimer", "deplacer")
ARCHIVES = "Archives/supprimes"


@dataclass
class Plan:
    quoi: str  # "tache" | "projet"
    cible: str
    titre: str
    effacees: list[str] = field(default_factory=list)  # tâches effacées
    racines: list[str] = field(default_factory=list)  # tâches déplacées (leur descendance suit)
    vers: str | None = None
    vers_type: str | None = None  # "conteneur" | "tache"
    contextes: list[str] = field(default_factory=list)  # `contexte.md` effacés (chemins relatifs)
    deps: list[tuple[str, str]] = field(default_factory=list)  # ranges_ ou déplacés par l'Aligneur
    archives: int = 0
    fichiers: list[str] = field(default_factory=list)  # fichiers de tâches touchés (INV-ALIGN-2)
    calcul: tuple | None = None


class _Transaction:
    """INV-SUPPR-1 : octets d'origine de tout fichier touché ; `defaire` remet le vault tel quel."""

    def __init__(self):
        self.avant: dict[Path, bytes | None] = {}
        self.dossiers: list[Path] = []

    def garder(self, p: Path) -> None:
        if p not in self.avant:
            self.avant[p] = p.read_bytes() if p.is_file() else None

    def dossier(self, d: Path) -> None:
        manquants = [x for x in (d, *d.parents) if not x.exists()]
        self.dossiers += reversed(manquants)

    def defaire(self) -> None:
        for p, octets in self.avant.items():
            if octets is None:
                p.unlink(missing_ok=True)
        for p, octets in self.avant.items():
            if octets is not None:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(octets)
        for d in reversed(self.dossiers):
            try:
                d.rmdir()
            except OSError:
                pass


def _effacer(p: Path) -> None:
    p.unlink()


# --- lecture : emplacements, refus ------------------------------------------------------------
def _emplacements(v, exclus_c: set[str], exclus_t: set[str]) -> list[dict]:
    taches, conts = v.index()
    meres = {p for p in v._parents(taches).values() if p} - exclus_t
    return ([{"id": c.id, "type": "conteneur", "titre": c.titre} for c in conts.values()
             if c.id not in exclus_c and not any(c.id.startswith(x + "/") for x in exclus_c)]
            + sorted(({"id": k, "type": "tache", "titre": taches[k].titre} for k in meres),
                     key=lambda x: x["titre"].casefold()))


def _cible(v, vers: str, exclus_c: set[str], exclus_t: set[str]) -> tuple[str, str]:
    taches, conts = v.index()
    if vers in conts and vers not in exclus_c and not any(vers.startswith(x + "/") for x in exclus_c):
        return "conteneur", vers
    if vers in taches and vers not in exclus_t:
        return "tache", vers
    raise Invalide(langues.t("serveur.suppression.vers_invalide", vers=vers or "?"))


def _libres(moteur, ids) -> None:
    # INV-SUPPR-1 : un tour en cours ou en file écrirait dans une fiche disparue.
    if occ := [o for i in ids if (o := moteur.occupation(i))]:
        raise Conflit(langues.t("serveur.suppression.tour_en_cours",
                                taches=", ".join(f"« {o['titre']} »" for o in occ)))


def _mode(mode: str | None, a_descendants: bool) -> str:
    if not a_descendants:
        return "supprimer"
    if mode not in MODES:
        raise Invalide(langues.t("serveur.suppression.mode_invalide"))
    return mode


# --- tâche ------------------------------------------------------------------------------------
def _defaut_tache(v, ident: str) -> str:
    return v._parents(v.index()[0])[ident] or v.tache(ident).conteneur


def plan_tache(moteur, ident: str, mode: str | None, vers: str | None) -> Plan:
    v = moteur.vault
    t = v.tache(ident)
    desc, enfants = v.descendance(ident), v.enfants(ident)
    p = Plan("tache", ident, t.titre)
    if _mode(mode, bool(enfants)) == "supprimer":
        p.effacees = desc
    else:
        p.vers_type, p.vers = _cible(v, vers or _defaut_tache(v, ident), set(), set(desc))  # ni elle ni sa descendance : pas de cycle
        p.effacees, p.racines = [ident], enfants
    _libres(moteur, desc)
    taches = v.index()[0]
    p.fichiers = [v._rel(taches[k].chemin) for k in desc]
    return p


# --- projet -----------------------------------------------------------------------------------
def _refuser_projet(v, aligneur, cid: str) -> None:
    cfg = v.cfg
    if cid in (cfg.arrivee, "_meta") or posixpath.dirname(cid) == cfg.casquettes or aligneur.protege(cid):
        raise Conflit(langues.t("serveur.suppression.pas_supprimable"))
    for _d, sous, fs in os.walk(v.racine / cid):
        if ".git" in sous or ".claude" in sous or ".git" in fs:
            raise Conflit(langues.t("serveur.suppression.contient_code", chemin=cid))


def _contenu(v, cid: str) -> tuple[list[str], list[str], list[str]]:
    """(sous-projets du dossier, tâches du projet et de ses sous-projets, tâches propres au projet)."""
    taches, conts = v.index()
    dedans = sorted(d for d in conts if d.startswith(cid + "/"))
    dans = {cid, *dedans}
    toutes = [k for k, t in taches.items() if t.conteneur in dans]
    return dedans, toutes, [k for k in toutes if taches[k].conteneur == cid]


def _hauts(dedans: list[str]) -> list[str]:
    return [d for d in dedans if not any(d.startswith(x + "/") for x in dedans)]


def _a_ranger(v, cid: str, gardes: set[str], connus: set[str]) -> list[str]:
    """Fichiers du dossier qui ne sont ni effacés, ni déplacés : rangés dans les archives."""
    out = []
    for d, _sous, fs in os.walk(v.racine / cid):
        for f in fs:
            rel = (Path(d) / f).relative_to(v.racine).as_posix()
            if rel not in connus and not any(rel.startswith(g + "/") for g in gardes):
                out.append(rel)
    return sorted(out)


def plan_projet(moteur, aligneur, cid: str, mode: str | None, vers: str | None) -> Plan:
    v = moteur.vault
    c = v.conteneur(cid)
    _refuser_projet(v, aligneur, cid)
    taches = v.index()[0]
    dedans, toutes, propres = _contenu(v, cid)
    hauts = _hauts(dedans)
    p = Plan("projet", cid, c.titre)
    dans = {cid, *dedans}
    p.contextes = [f"{d}/{v.cfg.contexte}" for d in sorted(dans) if (v.racine / d / v.cfg.contexte).is_file()]
    gardes: set[str] = set()
    if _mode(mode, bool(toutes or hauts)) == "supprimer":
        p.effacees = toutes
    else:
        p.vers_type, p.vers = _cible(v, vers or transformations._parent(v, arbre.structure(v), cid),
                                     dans, set(toutes))
        p.contextes = [x for x in p.contextes if x == f"{cid}/{v.cfg.contexte}"]
        parents = v._parents(taches)
        p.racines = [k for k in propres if parents[k] not in propres]
        dest = p.vers if p.vers_type == "conteneur" else taches[p.vers].conteneur
        for d in hauts:
            p.deps.append((d, f"{dest}/{arbre.nom_dossier(d)}"))
        gardes = set(hauts)
    _libres(moteur, toutes)
    connus = {v._rel(taches[k].chemin) for k in toutes} | set(p.contextes)
    jour = aujourdhui().isoformat()
    ranges_ = _a_ranger(v, cid, gardes, connus)
    p.deps += [(rel, f"{ARCHIVES}/{jour}/{rel}") for rel in ranges_]
    p.archives = len(ranges_)
    for _de, a in p.deps:
        if (v.racine / a).exists():  # INV-VAULT-2 : jamais d'écrasement
            raise Conflit(langues.t("serveur.suppression.destination_existe", chemin=a))
    p.fichiers = sorted(connus - set(p.contextes))
    return p


# --- aperçu -----------------------------------------------------------------------------------
def apercu(moteur, aligneur, tache: str | None, conteneur: str | None) -> dict:
    """Ce que le dialogue annonce : descendants, emplacements possibles, emplacement par défaut."""
    v = moteur.vault
    if tache:
        t, desc = v.tache(tache), v.descendance(tache)
        return {"quoi": "tache", "titre": t.titre, "sous_taches": len(desc) - 1,
                "defaut": _defaut_tache(v, tache), "emplacements": _emplacements(v, set(), set(desc))}
    if not conteneur:
        raise Invalide(langues.t("serveur.transformations.conteneur_requis"))
    c = v.conteneur(conteneur)
    _refuser_projet(v, aligneur, conteneur)
    dedans, toutes, _ = _contenu(v, conteneur)
    taches = v.index()[0]
    connus = {v._rel(taches[k].chemin) for k in toutes}
    connus |= {f"{d}/{v.cfg.contexte}" for d in (conteneur, *dedans)}
    hauts = set(_hauts(dedans))
    return {"quoi": "projet", "titre": c.titre, "taches": len(toutes), "sous_projets": len(dedans),
            "autres": len(_a_ranger(v, conteneur, set(), connus)),
            "autres_deplacer": len(_a_ranger(v, conteneur, hauts, connus)),
            "defaut": transformations._parent(v, arbre.structure(v), conteneur),
            "emplacements": _emplacements(v, {conteneur, *dedans}, set(toutes))}


# --- écriture ---------------------------------------------------------------------------------
def _nettoyer(v, ids: set[str], tx: _Transaction) -> None:
    """Références des tâches restantes vers une tâche effacée : `parent:`, liens, livrables."""
    for t in list(v.index()[0].values()):
        texte = fiches.lire(t.chemin)
        if not any(i in texte for i in ids):
            continue
        maj: dict = {"parent": None} if t.parent_brut in ids else {}
        for cle in liens.TYPES:
            deja = liens.ids(t.fm, cle)
            if (reste := [x for x in deja if x not in ids]) != deja:
                maj[cle] = reste or None  # INV-VAULT-1 : clé retirée quand la liste devient vide
        lignes = fiches.lire_lignes(texte, "livrables")
        gardees = [x for x in lignes if not (x["lien"].startswith("[[") and nettoyer_lien(x["lien"]) in ids)]
        nouveau = fiches.ecrire_lignes(texte, gardees, "livrables") if len(gardees) != len(lignes) else texte
        if maj:
            nouveau = fiches.modifier_cles(nouveau, {**maj, "updated": aujourdhui()})
        if nouveau != texte:
            tx.garder(t.chemin)
            fiches.ecrire_atomique(t.chemin, nouveau)
    v._index = None


def _deplacer(v, p: Plan, tx: _Transaction) -> None:
    taches = v.index()[0]
    dest = p.vers if p.vers_type == "conteneur" else taches[p.vers].conteneur
    ids = list(dict.fromkeys(x for r in p.racines for x in v.descendance(r)))
    dossier = v.racine / v.conteneur(dest).id / "taches"
    tx.dossier(dossier)
    for k in ids:
        tx.garder(taches[k].chemin)
        tx.garder(dossier / taches[k].chemin.name)
    parent = None if p.vers_type == "conteneur" else p.vers
    v._deplacer(ids, dest, {r: {"parent": parent} for r in p.racines})
    v._index = None


def _coeur(v, p: Plan, tx: _Transaction) -> None:
    v._index = None
    if p.racines:
        _deplacer(v, p, tx)
    taches = v.index()[0]
    chemins = [taches[k].chemin for k in p.effacees] + [v.racine / rel for rel in p.contextes]
    v._index = None
    for chemin in chemins:
        tx.garder(chemin)
        _effacer(chemin)
    _nettoyer(v, set(p.effacees), tx)


def executer(moteur, aligneur, p: Plan) -> None:
    """INV-SUPPR-1 : tout ou rien. Hors de la boucle, sous le verrou du moteur (INV-ALIGN-2)."""
    v, tx = moteur.vault, _Transaction()

    def coeur():
        try:
            _coeur(v, p, tx)
        except Exception:
            tx.defaire()  # avant le retour arrière de l'Aligneur : ordre inverse des écritures
            raise
    try:
        if not p.deps:
            coeur()
        elif not aligneur._verrou.acquire(blocking=False):
            raise Conflit(langues.t("serveur.transformations.alignement_en_cours"))
        else:
            try:
                existants, reecritures = p.calcul or _calcul(aligneur, p)
                aligneur.executer(p.deps, reecritures, existants, False, "suppression", puis=coeur)
            finally:
                aligneur._verrou.release()
    except Conflit:
        raise
    except Exception as e:
        raise Conflit(langues.t("serveur.suppression.annulee", erreur=e)) from e
    finally:
        v._index = None
        v._structure = None
    if p.quoi == "projet":
        for d, _s, _f in os.walk(v.racine / p.cible, topdown=False):
            try:
                Path(d).rmdir()  # dossiers vidés seulement : un dossier non vide reste
            except OSError:
                pass


def _calcul(aligneur, p: Plan) -> tuple:
    existants, a_lire = references.inventaire(aligneur.racine, aligneur.exclure)
    return existants, references.planifier(aligneur.racine, p.deps, aligneur.exclure, [], (existants, a_lire))


def _oublier(moteur, ids: set[str]) -> None:
    """États du moteur qui visent une tâche effacée : file, mandat, routine, propositions en attente."""
    routines = getattr(moteur, "routines", None)  # posé par l'application (api.creer_app)
    for i in ids:
        moteur.files.pop(i, None)
        moteur.etats.pop(i, None)
        moteur.mandats.retirer(i)
        if routines and routines.etat.pop(i, None) is not None:
            routines._sauver()  # INV-ROUTINE-1 : le programme d'une routine effacée est retiré
    props = moteur.propositions
    for q in props.liste:
        vise = {q.get("tache"), *(q.get("taches") or [])} | {nettoyer_lien(str(q.get("valeur") or "").split(":")[-1])}
        if q.get("etat") == "en_attente" and vise & ids:
            q["etat"] = "refusee"
    props.sauver()


def _tracer(moteur, p: Plan) -> None:
    dossier = moteur.config.donnees / "journal"
    dossier.mkdir(parents=True, exist_ok=True)
    ligne = {"quand": dt.datetime.now().isoformat(timespec="seconds"), "qui": "moi", "quoi": p.quoi,
             "cible": p.cible, "titre": p.titre, "effacees": p.effacees, "deplacees": p.racines,
             "vers": p.vers, "contextes": p.contextes, "ranges": p.archives}
    with (dossier / "suppressions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


async def supprimer(moteur, aligneur, p_fn) -> dict:
    """`p_fn()` rend le plan (lu hors de la boucle) ; le geste se fait sous `exclusif`."""
    p = await asyncio.to_thread(p_fn)
    if p.deps:
        p.calcul = await asyncio.to_thread(_calcul, aligneur, p)
    reecrits = [r.fichier for r in p.calcul[1]] if p.calcul else []
    dossiers = [p.cible] if p.quoi == "projet" else []
    async with moteur.exclusif(dossiers, p.fichiers + reecrits):
        await asyncio.to_thread(executer, moteur, aligneur, p)
    _oublier(moteur, set(p.effacees))
    _tracer(moteur, p)
    moteur.publier("arbre")
    return {"supprimees": len(p.effacees), "deplacees": len(p.racines), "vers": p.vers,
            "ranges": p.archives, "archives": f"{ARCHIVES}/{aujourdhui().isoformat()}" if p.archives else None}
