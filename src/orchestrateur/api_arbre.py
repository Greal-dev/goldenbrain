"""Routes `/api/arbre` et `/api/alignement` : arbre, gestes, plan et application des déplacements.

Rôle : traduire HTTP en appels à `arbre`, `geste` et `Aligneur`, hors de la boucle d'événements
pour tout ce qui lit le disque. Extrait d'`api.py` (plafond de 500 lignes), à l'identique.
Frontières : aucune logique d'arbre ni de déplacement ici.
Invariants portés : INV-INTEG-1 (pastille d'intégration posée sur l'arbre, cache seul), INV-ARBRE-2 (un projet ou une opération passe par le plan), INV-ALIGN-2
(application sous `Moteur.exclusif(dossiers, fichiers)`), INV-VERROU-1 (demi-verrou des gestes).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from . import arbre as gestes
from . import api_integration, api_main, etat_main, geste, integration, langues, liens
from .vault import Invalide


class CorpsProposition(BaseModel):
    type: str
    tache: str
    valeur: str
    de: str | None = None
    motif: str | None = None
    taches: list[str] | None = None  # « rattacher » : le lot, en plus de `tache` (INV-RATTACHER-1)


class CorpsGeste(BaseModel):
    noeud: str
    sous: str | None = None
    forcer: bool = False  # INV-VERROU-1


class CorpsPlanAlignement(BaseModel):
    conteneurs: list[str]


class CorpsAppliquer(BaseModel):
    jeton: str
    point_git: bool = True


def lancer_apres(commande: str, dossier: Path) -> None:
    """Commande `alignement.apres` en tâche de fond, sans attendre ni shell."""
    try:
        subprocess.Popen(commande if os.name == "nt" else shlex.split(commande), cwd=dossier)
    except OSError as e:
        logging.getLogger(__name__).warning("alignement.apres en échec : %s", e)


def routes(config, moteur, aligneur, index_notes) -> APIRouter:
    r, vault = APIRouter(), moteur.vault
    suivi = integration.Suivi(integration.charger(config.chemin))
    r.include_router(api_integration.routes(config, suivi))  # INV-INTEG-1
    r.include_router(api_main.routes(moteur))  # INV-MAIN-5

    def reprise_auto(ns: list[dict]) -> None:  # INV-REPRISE-1 : l'écran dit « reprise automatique dans la file »
        for n in ns:
            if n["type"] == "tache":
                n["reprise_auto"] = moteur.reprise_auto.attendue(n["id"])
            reprise_auto(n["enfants"])

    def arbre_(toutes: int) -> dict:
        taches = vault.index()[0]
        noeuds = liens.annoter(vault.arbre(bool(toutes), moteur.etat_de), taches)
        reprise_auto(noeuds)
        etat_main.annoter(moteur, noeuds)  # INV-MAIN-1 : une seule lecture d'état par nœud
        suivi.annoter(noeuds, taches)  # cache seul : ne bloque jamais l'arbre
        return {"noeuds": moteur.routines.annoter(noeuds) if hasattr(moteur, "routines") else noeuds}  # INV-ROUTINE-5

    r.chauffer = lambda: asyncio.to_thread(arbre_, 0)  # INV-FROID-1 : l'arbre tel que servi, chaud avant la première requête

    @r.get("/api/arbre")
    async def arbre(toutes: int = 0):
        return arbre_(toutes)

    @r.post("/api/arbre/deplacer")
    async def arbre_deplacer(c: CorpsGeste, toutes: int = 0):
        if not c.sous:
            raise Invalide(langues.t("serveur.api_arbre.cible_requise"))
        moteur.demi_verrou(c.noeud, c.forcer)  # INV-VERROU-1 : le nœud et sa descendance
        gestes.deplacer(vault, c.noeud, c.sous, taches_seules=True)
        moteur.publier("arbre")
        return await arbre(toutes)

    @r.post("/api/arbre/monter")
    async def arbre_monter(c: CorpsGeste, toutes: int = 0):
        moteur.demi_verrou(c.noeud, c.forcer)  # INV-VERROU-1
        gestes.monter(vault, c.noeud, taches_seules=True)
        moteur.publier("arbre")
        return await arbre(toutes)

    @r.post("/api/arbre/plan")  # INV-ARBRE-2 : projet ou opération, appliqué par l'alignement
    async def arbre_plan(c: CorpsGeste):
        # INV-VERROU-1 : refus avant le plan ; l'application reste sous INV-ALIGN-2 (dur).
        moteur.demi_verrou(c.noeud, c.forcer)
        return await asyncio.to_thread(geste.planifier, aligneur, c.noeud, c.sous)

    @r.get("/api/alignement")
    async def alignement():
        # Index et `stat` des dossiers : hors de la boucle d'événements.
        return [asdict(e) for e in await asyncio.to_thread(aligneur.ecarts)]

    @r.post("/api/alignement/plan")
    async def alignement_plan(c: CorpsPlanAlignement):
        # Balayage complet du vault : hors de la boucle d'événements.
        return await asyncio.to_thread(aligneur.plan, c.conteneurs)

    async def appliquer(jeton: str, point_git: bool = True) -> dict:
        # INV-ALIGN-2 : refus nommé si un tour touche un dossier déplacé ou un fichier réécrit.
        dossiers, fichiers = aligneur.perimetre(jeton)
        async with moteur.exclusif(dossiers, fichiers):
            res = await asyncio.to_thread(aligneur.appliquer, jeton, point_git)
        moteur.publier("arbre")
        index_notes.perimer()  # la recherche suit les dossiers déplacés sans délai
        if config.alignement.apres:
            lancer_apres(config.alignement.apres, vault.racine)
        # Index périmé par l'alignement : sa reconstruction lit le disque, hors de la boucle.
        return {**res, "arbre": await asyncio.to_thread(arbre_, 0)}

    @r.post("/api/alignement/appliquer")
    async def alignement_appliquer(c: CorpsAppliquer):
        return await appliquer(c.jeton, c.point_git)

    r.appliquer = appliquer  # l'acceptation d'une proposition « opération » passe par là
    return r
