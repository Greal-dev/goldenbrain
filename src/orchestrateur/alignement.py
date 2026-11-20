"""Alignement physique : les dossiers des conteneurs suivent l'arbre (lot 5).

Rôle : calculer le dossier attendu de chaque conteneur depuis sa place logique (lot 4),
lister les écarts, simuler un plan (déplacements + réécriture des références) et l'appliquer.
Frontières : lit l'arbre via `arbre.structure` (index en mémoire, aucun fichier relu pour
`ecarts`) ; la réécriture des références est déléguée à `references` ; aucune coordination
avec le moteur ici (l'API tient le verrou, INV-ALIGN-2).
Invariants portés : INV-ALIGN-1 (application tout ou rien, point git avant toute écriture),
INV-ALIGN-4 (point git octet pour octet, quelle que soit la config git du poste), INV-ALIGN-3 (dossiers jamais déplacés), INV-VAULT-2 (jamais d'écrasement).
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import logging
import os
import posixpath
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import arbre, fiches, langues, references
from .vault import Conflit, Invalide, NonTrouve

log = logging.getLogger(__name__)
# INV-ALIGN-3 : dossiers de premier niveau jamais déplacés (en plus de la racine, des
# casquettes et de `Projets`).
PROTEGES = ("_meta", "Archives", "Inbox", "Journal-Log", "Ressources")
DUREE_PLAN_S = 30 * 60
NOM_INTERDIT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


@dataclass
class Ecart:
    conteneur: str
    titre: str
    de: str
    vers: str
    conflit: str | None = None


def _egal(a: str, b: str) -> bool:
    return os.path.normcase(a) == os.path.normcase(b)


def _sous(chemin: str, dossier: str) -> bool:
    return os.path.normcase(chemin).startswith(os.path.normcase(dossier.rstrip("/") + "/"))


def _mot(motif: str) -> str:
    """Nom du geste, traduit pour le message ; `motif` reste la valeur française (message du point git)."""
    return {"alignement": langues.t("serveur.alignement.motif_alignement"),
            "déplacement": langues.t("serveur.alignement.motif_deplacement"),
            "archivage": langues.t("serveur.alignement.motif_archivage")}.get(motif, motif)


def _nom_invalide(seg: str) -> bool:
    return (not seg or seg in (".", "..") or seg != seg.strip() or seg.endswith(".")
            or bool(NOM_INTERDIT.search(seg)) or seg.split(".")[0].upper() in RESERVES)


class Aligneur:
    def __init__(self, vault, externes: list[str], exclure: list[str] | None = None):
        self.vault = vault
        self.cfg = vault.cfg
        self.racine: Path = vault.racine
        self.externes = externes
        self.exclure = list(self.cfg.exclure if exclure is None else exclure)
        self.plans: dict[str, tuple] = {}
        self._depots: dict[Path, tuple[tuple[int, int], bool]] = {}
        self._verrou = threading.Lock()

    # --- dossiers attendus -----------------------------------------------------------
    def _casquettes(self) -> dict[str, list[str]]:
        try:
            noms = sorted(d.name for d in (self.racine / self.cfg.casquettes).iterdir()
                          if d.is_dir())
        except OSError:
            noms = []
        par_code: dict[str, list[str]] = {}
        for n in noms:
            if m := re.match(r"(C\d+|META)-", n):
                par_code.setdefault(m.group(1), []).append(f"{self.cfg.casquettes}/{n}")
        return par_code

    def protege(self, rel: str) -> bool:
        """INV-ALIGN-3 : la racine, `Projets`, les casquettes et les dossiers réservés."""
        haut = [self.cfg.projets, self.cfg.casquettes, *PROTEGES]
        parent = posixpath.dirname(rel)
        return (rel in ("", ".") or any(_egal(rel, h) for h in haut)
                or _egal(parent, self.cfg.casquettes))

    def dossier(self, s, ident: str, cas: dict) -> str:
        """Dossier d'un nœud : un conteneur est son dossier ; une opération, le dossier où elle
        a été lue (INV-ARBRE-2), sinon celui de son parent + son nom ; une casquette, son
        dossier unique sous `vault.casquettes`, à défaut `Projets`."""
        n = s.noeuds[ident]
        if n.type == "conteneur":
            return n.id
        if n.type == "casquette":
            dossiers = cas.get(n.casquette, [])
            if len(dossiers) > 1:
                raise Conflit(langues.t("serveur.alignement.casquette_plusieurs_dossiers", casquette=n.casquette,
                                        dossiers=", ".join(dossiers)))
            return dossiers[0] if dossiers else self.cfg.projets
        if lus := s.dossiers_op.get(ident):
            if len(lus) > 1:
                raise Conflit(langues.t("serveur.alignement.operation_plusieurs_dossiers", titre=n.titre,
                                        dossiers=", ".join(sorted(lus))))
            return next(iter(lus))
        if _nom_invalide(n.segment):
            raise Conflit(langues.t("serveur.alignement.nom_inutilisable", nom=n.segment))
        return f"{self.dossier(s, n.parent, cas)}/{n.segment}"

    def _attendu(self, s, cid: str, cas: dict) -> tuple[str, str | None]:
        n = s.noeuds[cid]
        p = s.noeuds[n.parent]
        if self.protege(cid) or _sous(cid, self.cfg.arrivee) or cid in s.implicites:
            return cid, None  # INV-ARBRE-2 : placé par son dossier, aligné par construction
        if p.type == "casquette":
            # `parent: ""` dans un dossier d'opération ou de projet : il rejoint `<projets>`.
            haut = posixpath.dirname(posixpath.dirname(cid))
            dans_operation = _sous(cid, self.cfg.casquettes) and not _egal(haut, self.cfg.casquettes)
            if not _sous(cid, self.cfg.projets) and not dans_operation:
                return cid, None  # sans rattachement et déjà ailleurs : réputé à sa place
            return f"{self.cfg.projets}/{arbre.nom_dossier(cid)}", None
        try:
            return f"{self.dossier(s, p.id, cas)}/{arbre.nom_dossier(cid)}", None
        except Conflit as e:
            return cid, str(e)

    def attendus(self) -> dict[str, str]:
        s, cas = arbre.structure(self.vault), self._casquettes()
        return {cid: self._attendu(s, cid, cas)[0] for cid in self.vault.index()[1]}

    def _bruts(self) -> list[Ecart]:
        idx = self.vault.index()
        s, cas = arbre.structure(self.vault, idx), self._casquettes()
        liste = []
        for cid, c in idx[1].items():
            vers, conflit = self._attendu(s, cid, cas)
            if conflit or not _egal(vers, cid):
                liste.append(Ecart(cid, c.titre, cid, vers, conflit))
        return liste

    def ecarts(self) -> list[Ecart]:
        """Conteneurs non alignés, d'après l'index en mémoire (aucun fichier relu)."""
        liste = self._bruts()
        self._conflits(liste)
        return liste

    def _conflits(self, liste: list[Ecart]) -> None:
        for e in liste:
            if e.conflit:
                continue
            src, dst = self.racine / e.de, self.racine / e.vers
            autres = [x for x in liste if x is not e]
            if not _dans_racine(self.racine, src) or not _dans_racine(self.racine, dst):
                e.conflit = langues.t("serveur.alignement.hors_vault")
            elif self.protege(e.de):
                e.conflit = langues.t("serveur.alignement.protege")
            elif self._depot(src):
                e.conflit = langues.t("serveur.alignement.contient_code")
            elif dst.exists():
                e.conflit = langues.t("serveur.alignement.destination_existe", chemin=e.vers)
            elif _sous(e.vers, e.de):
                e.conflit = langues.t("serveur.alignement.destination_dans_soi")
            elif x := next((x for x in autres if _sous(x.de, e.de)), None):
                e.conflit = langues.t("serveur.alignement.parent_ecart", conteneur=x.conteneur)
            elif x := next((x for x in autres if _sous(e.vers, x.de) or _egal(e.vers, x.de)), None):
                e.conflit = langues.t("serveur.alignement.destination_dans_autre", conteneur=x.conteneur)
            elif x := next((x for x in autres if _egal(e.vers, x.vers)), None):
                e.conflit = langues.t("serveur.alignement.meme_destination", conteneur=x.conteneur)

    def _depot(self, src: Path) -> bool:
        """INV-ALIGN-3 : `.git` ou `.claude` directement dans `src`, mémorisé par (mtime, taille)
        du dossier : un ajout ou un retrait d'entrée change sa date."""
        try:
            st = src.stat()
        except OSError:
            return False
        cle = (st.st_mtime_ns, st.st_size)
        if (c := self._depots.get(src)) is None or c[0] != cle:
            c = self._depots[src] = (cle, (src / ".git").exists() or (src / ".claude").is_dir())
        return c[1]

    # --- plan --------------------------------------------------------------------------
    def plan(self, ids: list[str]) -> dict:
        """Simulation : n'écrit rien. Appelée hors de la boucle d'événements."""
        if not ids:
            raise Invalide(langues.t("serveur.alignement.aucun_conteneur"))
        tous = {e.conteneur: e for e in self._bruts()}
        conts = self.vault.index()[1]
        choisis = []
        for i in dict.fromkeys(ids):
            if i not in conts:
                raise NonTrouve(langues.t("serveur.alignement.conteneur_inconnu", ident=i))
            if i not in tous:
                raise Conflit(langues.t("serveur.alignement.deja_aligne", ident=i))
            choisis.append(tous[i])
        self._conflits(choisis)  # les conflits entre écarts ne valent qu'entre les choisis
        if bloques := [e for e in choisis if e.conflit]:
            raise Conflit("; ".join(f"{e.conteneur} : {e.conflit}" for e in bloques))
        return self.simuler([(e.de, e.vers) for e in choisis], [])

    def simuler(self, deps, avert: list[str], fiches_: dict | None = None,
                motif: str = "alignement") -> dict:
        """Plan d'un ensemble de déplacements (et, pour un geste d'arbre, des clés à poser après
        coup : `{chemin relatif d'avant: {clé: valeur ou None}}`) ; n'écrit rien."""
        fiches_ = fiches_ or {}
        for de, _ in deps:
            for dossier, sous, _f in os.walk(self.racine / de):
                if ".git" in sous or ".claude" in sous or ".git" in _f:
                    # INV-ALIGN-3 : un dépôt ou un `.claude` ne se déplace jamais.
                    raise Conflit(langues.t("serveur.alignement.contient_code_jamais", chemin=de))
        reecritures = references.planifier(self.racine, deps, self.exclure, avert)
        jeton = _empreinte(deps, reecritures, fiches_)
        maintenant = time.monotonic()
        self.plans = {j: v for j, v in self.plans.items() if maintenant - v[0] < DUREE_PLAN_S}
        fichiers = sorted({r.fichier for r in reecritures} | set(fiches_))
        self.plans[jeton] = (maintenant, deps, fiches_, motif, fichiers)
        return {"deplacements": [{"de": de, "vers": vers} for de, vers in deps],
                "reecritures": [{"fichier": r.fichier, "lignes": r.lignes,
                                 "exemples": [{"avant": a, "apres": b} for a, b in r.exemples]}
                                for r in reecritures],
                "fiches": [{"fichier": references.nouveau_chemin(f, deps), "cles": m}
                           for f, m in sorted(fiches_.items())],
                "externes": self._externes(deps), "avertissements": avert, "jeton": jeton}

    def _externes(self, deps) -> list[dict]:
        trouves = []
        for lieu in self.externes:
            for base in sorted(glob.glob(os.path.expanduser(lieu))):
                fichiers = [Path(base)] if os.path.isfile(base) else \
                    [Path(d) / f for d, _, fs in os.walk(base) for f in fs]
                a_lire = [str(f) for f in fichiers if f.suffix.lower() in references.EXTENSIONS
                          and not _dans_racine(self.racine, f)]
                for f, octets, _ in references.lire_candidats(a_lire, deps):
                    if octets is None:
                        continue
                    texte = octets.decode("utf-8", errors="replace")
                    if n := references.compter(texte, deps, self.racine):
                        trouves.append({"fichier": f, "occurrences": n})
        return trouves

    # --- application -------------------------------------------------------------------
    def perimetre(self, jeton: str) -> tuple[list[str], list[str]]:
        """INV-ALIGN-2 : (dossiers déplacés, fichiers réécrits par le plan), chemins d'avant."""
        entree = self.plans.get(jeton)
        if not entree or time.monotonic() - entree[0] >= DUREE_PLAN_S:
            raise Conflit(langues.t("serveur.alignement.plan_expire"))
        return [de for de, _ in entree[1]], list(entree[4])

    def appliquer(self, jeton: str, point_git: bool) -> dict:
        """INV-ALIGN-1 : tout ou rien. Appelée hors de la boucle, sous le verrou du moteur."""
        if not self._verrou.acquire(blocking=False):
            raise Conflit(langues.t("serveur.alignement.deja_en_cours"))
        try:
            return self._appliquer(jeton, point_git)
        finally:
            self._verrou.release()

    def _appliquer(self, jeton: str, point_git: bool) -> dict:
        # (a) jeton et conflits : le plan est recalculé, il doit être identique.
        entree = self.plans.get(jeton)
        if not entree or time.monotonic() - entree[0] >= DUREE_PLAN_S:
            raise Conflit(langues.t("serveur.alignement.plan_expire"))
        deps, fiches_, motif = entree[1:4]
        for de, vers in deps:
            if not (self.racine / de).is_dir():
                raise Conflit(langues.t("serveur.alignement.vault_change_absent", chemin=de))
            if (self.racine / vers).exists():
                raise Conflit(langues.t("serveur.alignement.vault_change_present", chemin=vers))
        existants_fichiers = references.inventaire(self.racine, self.exclure)
        reecritures = references.planifier(self.racine, deps, self.exclure, [],
                                           existants_fichiers)
        if _empreinte(deps, reecritures, fiches_) != jeton:
            raise Conflit(langues.t("serveur.alignement.vault_change"))

        def poser_cles():  # INV-ARBRE-1 : clés posées après le déplacement, tout ou rien
            arbre.executer(self.vault, {self.racine / references.nouveau_chemin(f, deps): m
                                        for f, m in fiches_.items()})
        r = self.executer(deps, reecritures, existants_fichiers[0], point_git, motif,
                          poser_cles if fiches_ else None)
        del r["resultat"]
        self.plans.pop(jeton, None)
        return r

    def executer(self, deps, reecritures, existants, point_git: bool, motif: str = "alignement",
                 puis=None) -> dict:
        """INV-ALIGN-1, étapes (b) à (d) : point git, déplacements, réécritures, puis `puis()`
        (dernière écriture du geste, défaite avec le reste si elle échoue). Partagé avec la
        réduction d'un projet (lot 7)."""
        # Contenus calculés AVANT toute écriture : une erreur de calcul ne laisse rien à défaire.
        textes = []
        for r in reecritures:
            octets = (self.racine / r.fichier).read_bytes()
            nouveau, _ = references.reecrire(octets.decode("utf-8"), r.fichier, deps,
                                             self.racine, existants=existants)
            textes.append((references.nouveau_chemin(r.fichier, deps), octets, nouveau))
        # (b) point de restauration : son échec abandonne tout, rien n'est encore touché.
        commit = self._point_git(motif) if point_git else None
        resultat = None
        crees: list[Path] = []
        faits: list[tuple[Path, Path]] = []
        ecrits: list[tuple[Path, bytes]] = []
        self.vault._index = None
        try:
            # (c) déplacements : parents créés d'abord, jamais d'écrasement (INV-VAULT-2).
            for de, vers in deps:
                src, dst = self.racine / de, self.racine / vers
                for d in reversed(dst.parents):
                    if _dans_racine(self.racine, d) and not d.exists():
                        d.mkdir()
                        crees.append(d)
                if dst.exists():
                    raise FileExistsError(langues.t("serveur.alignement.destination_existe", chemin=vers))
                os.rename(src, dst)
                faits.append((src, dst))
            # (d) réécritures atomiques.
            for rel, octets, nouveau in textes:
                p = self.racine / rel
                ecrits.append((p, octets))
                ecrire(p, nouveau)
            if puis:
                resultat = puis()
        except Exception as e:
            self._defaire(ecrits, faits, crees)
            if isinstance(e, PermissionError):
                raise Conflit(langues.t("serveur.alignement.annule_verrouille", motif=_mot(motif),
                                        fichier=e.filename or e)) from e
            raise Conflit(langues.t("serveur.alignement.annule", motif=_mot(motif), erreur=e)) from e
        finally:
            self.vault._index = None
            self.vault._structure = None
        for de, _ in deps:
            self._retirer_vides(self.racine / de)
        return {"deplacements": len(deps), "fichiers_reecrits": len(textes), "commit": commit,
                "resultat": resultat}

    def _defaire(self, ecrits, faits, crees) -> None:
        erreurs = []
        for p, octets in reversed(ecrits):
            try:
                p.write_bytes(octets)
            except OSError as e:
                erreurs.append(f"{p} : {e}")
        for src, dst in reversed(faits):
            try:
                os.rename(dst, src)
            except OSError as e:
                erreurs.append(f"{dst} -> {src} : {e}")
        for d in reversed(crees):
            try:
                d.rmdir()
            except OSError:
                pass
        if erreurs:
            log.error("retour arrière incomplet : %s", erreurs)
            raise Conflit(langues.t("serveur.alignement.retour_incomplet", erreurs="; ".join(erreurs)))

    def _retirer_vides(self, ancien: Path) -> None:
        """Parents laissés vides : retirés jusqu'au premier dossier protégé ou non vide."""
        d = ancien.parent
        while _dans_racine(self.racine, d) and d != self.racine:
            rel = d.relative_to(self.racine).as_posix()
            if self.protege(rel):
                return
            try:
                d.rmdir()  # n'échoue pas en silence sur un dossier non vide : il reste
            except OSError:
                return
            d = d.parent

    def _point_git(self, motif: str = "alignement") -> str:
        if not shutil.which("git"):
            raise Conflit(langues.t("serveur.alignement.git_introuvable"))
        haut = _git(self.racine, "rev-parse", "--show-toplevel")
        if haut.returncode or not _egal(str(Path(haut.stdout.strip()).resolve()),
                                        str(self.racine)):
            raise Conflit(langues.t("serveur.alignement.pas_git"))
        date = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        for args in (("add", "-A", "--", "."),
                     ("commit", "--allow-empty", "-m", f"GoldenBrain : avant {motif} {date}")):
            r = _git(self.racine, *args)
            if r.returncode:
                raise Conflit(langues.t("serveur.alignement.git_echec", detail=(r.stderr or r.stdout).strip()[:300]))
        return _git(self.racine, "rev-parse", "HEAD").stdout.strip()


def ecrire(p: Path, texte: str) -> None:
    fiches.ecrire_atomique(p, texte)  # INV-VAULT-2 : temporaire puis os.replace


# INV-ALIGN-4 : sous Git for Windows (core.autocrlf=true), `add` stockait LF et le retour
# rendait CRLF : 373 fichiers sur 1 298 différents (recette du 15/11, A1). Ces -c priment sur
# toute config système, globale ou du dépôt, pour cette commande seulement : rien n'est modifié.
GIT_NEUTRE = ("-c", "core.autocrlf=false", "-c", "core.eol=lf", "-c", "core.safecrlf=false")


def _git(racine: Path, *args: str) -> subprocess.CompletedProcess:
    # Liste d'arguments, jamais de shell ; identité du dépôt (aucun -c user.*).
    return subprocess.run(["git", *GIT_NEUTRE, *args], cwd=racine, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def _dans_racine(racine: Path, p: Path) -> bool:
    try:
        Path(os.path.abspath(p)).relative_to(racine)
        return True
    except ValueError:
        return False


def _empreinte(deps, reecritures, fiches_=None) -> str:
    donnees = [deps, sorted((r.fichier, r.mtime_ns, r.taille) for r in reecritures),
               sorted((fiches_ or {}).items())]
    return hashlib.sha256(json.dumps(donnees).encode()).hexdigest()[:32]
