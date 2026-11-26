"""Transformations assistées : promotion sur place avec découpage, réduction avec contraction.

Rôle : créer un projet vide sous un conteneur (`creer_conteneur`, « Nouveau groupe »), élever
une tâche en projet dans le dossier de son conteneur (mandat de découpage),
réduire un projet en une tâche (archivage, mandat de contraction), mémoriser les mandats en
attente (`etat/mandats.json`) et, en fin de tour, créer les tickets rendus dans `<decoupage>`.
Frontières : écrit dans le vault par `Vault` et `Aligneur` seulement (déplacements, archivage,
réécriture des références) ; ne lance aucun harnais : les mandats partent par `Moteur.soumettre`.
Invariants portés : INV-TRANSFO-1 (mandats sur geste humain, tickets créés par le moteur seul,
mandat persistant, jamais relancé), INV-VAULT-2 (jamais d'écrasement), INV-ALIGN-1 (archivage
tout ou rien, point git compris), INV-ALIGN-2 (réduction sous le verrou du moteur).
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from . import arbre, fiches, langues, references
from .vault import Conflit, Invalide, aujourdhui, casquette_normalisee, slugifier

log = logging.getLogger(__name__)


class _Libre(dict):
    def __missing__(self, cle: str) -> str:
        return "{" + cle + "}"


class Mandats:
    """INV-TRANSFO-1 : mandats en attente, `{tache: {"type", "projet", "cree"}}`, persistés."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        try:
            lu = json.loads(chemin.read_text("utf-8"))
        except (OSError, ValueError):
            lu = {}
        self.attente: dict[str, dict] = lu if isinstance(lu, dict) else {}

    def _sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.attente, ensure_ascii=False, indent=1))

    def poser(self, tache: str, type_: str, projet: str) -> None:
        self.attente[tache] = {"type": type_, "projet": projet, "cree": aujourdhui().isoformat()}
        self._sauver()

    def demarrer(self, tache: str) -> None:
        """Le message du mandat a atteint un tour."""
        if (m := self.attente.get(tache)) is not None and not m.get("tour"):
            m["tour"] = aujourdhui().isoformat()
            self._sauver()

    def sans_tour(self) -> list[str]:
        return [t for t, m in self.attente.items() if not m.get("tour")]

    def retirer(self, tache: str) -> None:
        if self.attente.pop(tache, None) is not None:
            self._sauver()


# --- découpage ---------------------------------------------------------------------------
def analyser_decoupage(texte: str) -> tuple[str, list[dict]] | None:
    """Dernier bloc `<decoupage>` : (résumé, [{"titre", "description"}]) ; None s'il manque.
    Analyse tolérante : description sur plusieurs lignes indentées jusqu'au prochain `- titre:`."""
    blocs = re.findall(r"<decoupage>(.*?)</decoupage>", texte or "", flags=re.S)
    if not blocs:
        return None
    resume, tickets, suite = "", [], False
    for ligne in blocs[-1].splitlines():
        nu = ligne.strip()
        if m := re.match(r"-\s*titre\s*:\s*(.*)$", nu):
            tickets.append({"titre": m.group(1).strip(), "description": ""})
            suite = False
        elif not ligne[:1].isspace() and (m := re.match(r"r[ée]sum[ée]\s*:\s*(.*)$", nu, re.I)):
            resume, suite = m.group(1).strip(), False
        elif tickets and (m := re.match(r"description\s*:\s*(.*)$", nu)):
            tickets[-1]["description"], suite = m.group(1).strip(), True
        elif suite and nu and ligne[:1].isspace():
            tickets[-1]["description"] += "\n" + nu
    return resume, [t for t in tickets if t["titre"]]


def _ecrire_resume(vault, conteneur: str, resume: str) -> None:
    ctx = vault.racine / conteneur / vault.cfg.contexte
    texte = fiches.lire(ctx)
    ligne = "Résumé : " + " ".join(resume.split())
    motif = re.compile(r"^Résumé : [^\r\n]*", flags=re.M)
    if motif.search(texte):
        texte = motif.sub(lambda _: ligne, texte, count=1)
    else:
        eol = fiches.fin_de_ligne(texte)
        texte = texte.rstrip("\r\n") + eol + eol + ligne + eol
    vault._index = None
    fiches.ecrire_atomique(ctx, texte)


def conclure(moteur, ident: str, final: str, fiche: dict) -> str | int | None:
    """Fin d'un tour réussi : traite le mandat en attente auquel ce tour répond. Un tour répond
    dès que le message du mandat lui a été remis (il n'est plus en file)."""
    mandat = moteur.mandats.attente.get(ident)
    if not mandat or any(e.mandat for e in moteur.files[ident]):
        return None
    if mandat["type"] != "decoupage":  # contraction : la fiche ordinaire suffit
        moteur.mandats.retirer(ident)
        return None
    lu = analyser_decoupage(final)
    if not lu or len(lu[1]) < 2:
        fiche["situation"] = (f"{fiche.get('situation') or ''} — Découpage insuffisant : aucun "
                              "ticket créé (au moins deux attendus).").lstrip(" —")
        # Une seconde chance : l'interface propose « Relancer » (un message ordinaire). Le mandat
        # reste donc en attente pour le tour suivant, puis s'efface s'il échoue encore.
        if mandat.get("essais", 0) >= 1:
            moteur.mandats.retirer(ident)
        else:
            mandat["essais"] = mandat.get("essais", 0) + 1
            moteur.mandats._sauver()
        return "insuffisant"
    resume, tickets = lu
    v = moteur.vault
    conteneur = v.tache(ident).conteneur
    pris = {t.titre.casefold() for t in v.index()[0].values() if t.conteneur == conteneur}
    crees = 0
    for k in tickets:
        if k["titre"].casefold() in pris:
            continue  # titre déjà pris dans le projet : pas de doublon
        # INV-TRANSFO-1 : le moteur crée les tickets, jamais l'agent.
        v.creer(k["titre"], conteneur, None, k["description"])
        pris.add(k["titre"].casefold())
        crees += 1
    if resume:
        _ecrire_resume(v, conteneur, resume)
    moteur.mandats.retirer(ident)
    return crees


# --- promotion ---------------------------------------------------------------------------
def _couvert(rel: str, motifs: list[str]) -> bool:
    segs = rel.split("/")
    return any(len(m.split("/")) == len(segs)
               and all(fnmatch.fnmatchcase(s, x) for s, x in zip(segs, m.split("/")))
               for m in motifs)


def _defaire(vault, rel: str) -> None:
    # Échec : on retire ce qu'on a créé ; un dossier non vide (tiers) n'est jamais effacé.
    vault._index = None
    dossier = vault.racine / rel
    (dossier / vault.cfg.contexte).unlink(missing_ok=True)
    for d in (dossier / "taches", dossier):
        try:
            d.rmdir()
        except OSError:
            pass


def creer_conteneur(vault, dans: str, nom: str) -> str:
    """Projet vide (`contexte.md` + `taches/`) né dans le dossier du conteneur `dans`, dont il
    hérite la casquette ; tout ou rien. Rend le rel du nouveau conteneur."""
    if not (nom := (nom or "").strip()):
        raise Invalide(langues.t("serveur.transformations.nom_vide"))
    c = vault.conteneur(dans)
    rel = posixpath.join(c.id, slugifier(nom, minuscules=False))
    if not _couvert(f"{rel}/taches/x.md", vault.cfg.taches):
        raise Conflit(langues.t("serveur.transformations.projet_invisible", chemin=f"{rel}/taches"))
    dossier = vault.racine / rel
    if dossier.exists():
        raise Conflit(langues.t("serveur.transformations.dossier_existe", chemin=rel))
    (dossier / "taches").mkdir(parents=True)
    try:
        jour = aujourdhui()
        fm = {"type": "contexte", "nom": nom, "projet": rel.rsplit("/", 1)[-1],
              "casquette": c.casquette if c.casquette != "?" else None,
              "created": jour, "updated": jour}
        lignes = [f"{k}: {fiches.valeur_yaml(v)}" for k, v in fm.items() if v is not None]
        vault._index = None
        # Aucune clé `parent:` : le parent implicite (lot 5) le range sous le conteneur d'origine.
        fiches.ecrire_atomique(dossier / vault.cfg.contexte,
                               "---\n" + "\n".join(lignes) + f"\n---\n\n# {nom}\n")
    except Exception:
        _defaire(vault, rel)
        raise
    return rel


def creer_projet(vault, ident: str, nom: str) -> str:
    """Projet né à la place de la tâche, dans le dossier de son conteneur ; tout ou rien."""
    t = vault.tache(ident)
    nom = (nom or "").strip() or t.titre
    taches = vault.index()[0]
    noms = [taches[k].chemin.name for k in vault.descendance(ident)]
    if len(set(noms)) != len(noms):  # collision vérifiée avant de créer quoi que ce soit
        raise Conflit(langues.t("serveur.transformations.meme_nom_fichier", chemin=posixpath.join(
            t.conteneur, slugifier(nom, minuscules=False))))
    rel = creer_conteneur(vault, t.conteneur, nom)
    try:
        ctx = vault.racine / rel / vault.cfg.contexte
        fiches.ecrire_atomique(ctx, fiches.lire(ctx) + f"\nIssu de la tâche [[{ident}]]\n")
        sans_parent = {k: {"parent": None} for k in [ident, *vault.enfants(ident)]}
        vault._deplacer(vault.descendance(ident), rel, sans_parent)
    except Exception:
        _defaire(vault, rel)
        raise
    return rel


def promouvoir(moteur, ident: str, nom: str | None = None, decouper: bool = True) -> str:
    v = moteur.vault
    nom = (nom or "").strip() or v.tache(ident).titre
    rel = creer_projet(v, ident, nom)
    moteur.publier("arbre")
    if decouper:
        existants = [f"« {t.titre} »" for t in v.index()[0].values()
                     if t.conteneur == rel and t.id != ident]
        texte = moteur.config.transformations.mandat_decoupage.format_map(_Libre(
            projet=nom, tickets_existants=", ".join(existants) or "aucun"))
        # INV-TRANSFO-1 : persistant avant d'être soumis ; un redémarrage ne le perd pas.
        moteur.mandats.poser(ident, "decoupage", nom)
        moteur.soumettre(ident, texte.strip(), mandat=True)
    return rel


# --- réduction ---------------------------------------------------------------------------
@dataclass
class Reduction:
    conteneur: str
    nom: str
    parent: str
    vers: str
    corps: str
    absorbees: str


def _parent(vault, s, cid: str) -> str:
    """Conteneur parent (implicite ou explicite), sinon celui de la casquette, sinon l'arrivée."""
    p = s.noeuds[cid].parent
    while p and s.noeuds[p].type == "operation":
        p = s.noeuds[p].parent
    if p and s.noeuds[p].type == "conteneur":
        return p
    cas = s.noeuds[cid].casquette
    return next((d for d in vault.index()[1] if posixpath.dirname(d) == vault.cfg.casquettes
                 and casquette_normalisee(arbre.nom_dossier(d)) == cas), vault.cfg.arrivee)


def _section(t, f: dict) -> str:
    session = str(t.fm.get("session") or "")
    harnais = str(t.fm.get("harnais") or "")
    lignes = [f"### {t.titre} ({t.statut or '?'})", f"- Fait : {f['fait']}",
              f"- Situation : {f['situation']}", f"- Reste à faire : {f['reste']}",
              f"- Prochain pas : {f['prochain_pas']}",
              *(f"- [{'x' if x['fait'] else ' '}] {x['texte']}" for x in f["sous_taches"]),
              f"- Harnais et session : {harnais or 'défaut'} {session or 'aucune session'}"]
    return "\n".join(lignes)


def preparer(moteur, aligneur, cid: str) -> Reduction:
    """Contrôles (409) et lectures, AVANT tout archivage. Hors de la boucle d'événements."""
    v = moteur.vault
    cfg = v.cfg
    taches, conts = v.index()
    c = v.conteneur(cid)
    if not c.contexte:
        raise Conflit(langues.t("serveur.transformations.rien_a_reduire", dossier=cid, fiche=cfg.contexte))
    if cid in (cfg.arrivee, "_meta") or posixpath.dirname(cid) == cfg.casquettes \
            or aligneur.protege(cid):
        raise Conflit(langues.t("serveur.transformations.pas_reductible"))
    s = arbre.structure(v)
    dedans = {d for d in conts if d.startswith(cid + "/")}
    sous = dedans | {d for d in s.sous_arbre(cid) if s.noeuds[d].type == "conteneur"} - {cid}
    if any(v.ouverte(t) for t in taches.values() if t.conteneur in sous):
        raise Conflit(langues.t("serveur.transformations.sous_projet_ouvert"))
    absorbees = [t for t in taches.values() if t.conteneur == cid or t.conteneur in dedans]
    if actives := [t for t in absorbees if moteur.etat_de(t.id) in ("en_cours", "en_file")]:
        noms = ", ".join(f"« {t.titre} » ({t.id})" for t in actives)
        raise Conflit(langues.t("serveur.transformations.seance_en_cours", taches=noms))
    for _d, sous_d, fs in os.walk(v.racine / cid):
        if ".git" in sous_d or ".claude" in sous_d or ".git" in fs:
            raise Conflit(langues.t("serveur.transformations.contient_code", chemin=cid))
    # Fiches relues AVANT l'archivage : ce sont elles que la contraction reprend.
    lues = [(t, fiches.lire_fiche(fiches.lire(t.chemin))) for t in absorbees]
    ouvertes = [_section(t, f) for t, f in lues if v.ouverte(t)]
    fermees = [f"- {t.titre} ({t.statut or '?'})" for t, _ in lues if not v.ouverte(t)]
    corps = fiches.decouper(fiches.lire(v.racine / cid / cfg.contexte))[3].strip()
    corps = re.sub(r"\A# [^\n]*\n*", "", corps)  # le titre de la tâche le remplace
    liste = [f"- {t.titre} ({t.statut or '?'}) — {f['situation'] or f['fait'] or 'sans fiche'}"
             + (f" ; session {t.fm.get('harnais') or 'défaut'} {t.fm['session']}"
                if t.fm.get("session") else "") for t, f in lues]
    corps = (corps + "\n\n" if corps else "") + "## Tâches absorbées\n" + "\n".join(liste)
    base = f"Archives/{arbre.nom_dossier(cid)}-ARCHIVE-{aujourdhui().isoformat()}"
    vers, n = base, 2
    while (v.racine / vers).exists():
        vers, n = f"{base}-{n}", n + 1
    return Reduction(cid, c.titre, _parent(v, s, cid), vers, corps,
                     "\n\n".join(ouvertes + (["Tâches fermées :\n" + "\n".join(fermees)]
                                             if fermees else [])) or "aucune")


def calculer(aligneur, r: Reduction) -> tuple:
    """Inventaire du vault et références à réécrire pour l'archivage : (deps, inventaire,
    réécritures). Hors de la boucle d'événements (lit tout le vault)."""
    deps = [(r.conteneur, r.vers)]
    inventaire = references.inventaire(aligneur.racine, aligneur.exclure)
    return deps, inventaire, references.planifier(aligneur.racine, deps, aligneur.exclure, [],
                                                  inventaire)


def archiver(moteur, aligneur, r: Reduction, point_git: bool, calcul: tuple | None = None) -> str:
    """INV-ALIGN-1 : point git, archivage, réécriture des références, création de la tâche,
    tout ou rien. Appelée hors de la boucle, sous le verrou du moteur (INV-ALIGN-2)."""
    if not aligneur._verrou.acquire(blocking=False):
        raise Conflit(langues.t("serveur.transformations.alignement_en_cours"))
    try:
        deps, (existants, _a_lire), reecritures = calcul or calculer(aligneur, r)
        fait = aligneur.executer(deps, reecritures, existants, point_git, "archivage",
                                 puis=lambda: moteur.vault.creer(r.nom, r.parent, None, r.corps))
        return fait["resultat"]
    finally:
        aligneur._verrou.release()


async def reduire(moteur, aligneur, cid: str, point_git: bool = True) -> dict:
    if not cid:
        raise Invalide(langues.t("serveur.transformations.conteneur_requis"))
    r = await asyncio.to_thread(preparer, moteur, aligneur, cid)
    calcul = await asyncio.to_thread(calculer, aligneur, r)
    # INV-ALIGN-2 : refus nommé si un tour touche le projet ou un fichier réécrit ; aucun tour
    # de ces tâches ne démarre pendant l'archivage.
    async with moteur.exclusif([r.conteneur], [x.fichier for x in calcul[2]]):
        ident = await asyncio.to_thread(archiver, moteur, aligneur, r, point_git, calcul)
    moteur.publier("arbre")
    texte = moteur.config.transformations.mandat_contraction.format_map(_Libre(
        projet=r.nom, archive=r.vers, taches_absorbees=r.absorbees))
    moteur.mandats.poser(ident, "contraction", r.nom)  # INV-TRANSFO-1
    moteur.soumettre(ident, texte.strip(), mandat=True)
    return {"tache": ident, "archive": r.vers}
