"""Routes des réflexes de l'agent et du traçage des documents d'une tâche.

Rôle : `GET /api/accueil/reflexes` (état par assistant, aperçu du changement), `POST …/appliquer`
(installer, mettre à jour ou retirer le bloc : geste de l'utilisateur), `POST …/plus-tard` (ne plus proposer
cette version) ; `POST /api/taches/{id}/traces` (une ligne datée dans la section « Traces » de la fiche, avec
les documents cités en liens).
Frontières : la rédaction et l'écriture du bloc sont dans `reflexes.py` ; les routes `/api/accueil/reflexes`
sont réservées au poste (INV-ACCUEIL-1) ; le traçage n'écrit que par `Vault.consigner` (INV-VAULT-1).
Invariants portés : INV-REFLEXES-1, INV-TRACE-1.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import fiches, langues, reflexes
from .vault import Vault

ROUTE = "/api/accueil/reflexes"
SECTION = "Traces"  # nom de structure stable (comme « Feux verts ») : ne dépend pas de la langue réglée


class CorpsAppliquer(BaseModel):
    harnais: str
    action: str = "installer"


class CorpsPlusTard(BaseModel):
    harnais: str


class CorpsTrace(BaseModel):
    texte: str = Field(min_length=1, max_length=2000)
    documents: list[str] = Field(default_factory=list, max_length=20)


def lien(vault: Vault, chemin: str) -> str:
    """INV-TRACE-1 : un document du vault devient un lien `[[…]]` (graphe, notes liées) ; un fichier
    hors du vault reste un chemin cité, jamais lu."""
    p = Path(chemin).expanduser()
    try:
        rel = p.resolve().relative_to(vault.racine).as_posix()
    except (ValueError, OSError):
        return f"`{chemin.replace('`', '')}`"
    return f"[[{rel[:-3] if rel.endswith('.md') else rel}]]"


def routes(config) -> APIRouter:
    r = APIRouter()
    etat = config.donnees / "etat" / "reflexes.json"

    def releve() -> dict:
        lignes = reflexes.releve(langues.courante(), reflexes.lire_reportes(etat))
        for x in lignes:
            if x["etat"] != "a_jour":
                x["apercu"] = reflexes.apercu(Path(x["fichier"]), "installer", langues.courante())
        return {"version": reflexes.VERSION, "assistants": lignes, "propose": any(x["propose"] for x in lignes)}

    def harnais(h: str) -> Path:
        if h not in reflexes.CIBLES:
            raise HTTPException(400, langues.t("serveur.reflexes.inconnu", harnais=h))
        return reflexes.fichier(h)

    @r.get(ROUTE)
    async def lire():
        return releve()

    @r.post(ROUTE + "/appliquer")
    async def appliquer(c: CorpsAppliquer):
        # INV-REFLEXES-1 : la route n'est appelée que par le bouton de l'utilisateur, après l'aperçu.
        if c.action not in ("installer", "retirer"):
            raise HTTPException(400, langues.t("serveur.reflexes.action", action=c.action))
        try:
            reflexes.appliquer(harnais(c.harnais), c.action, langues.courante())
        except (OSError, ValueError) as e:
            raise HTTPException(409, str(e)) from None
        return releve()

    @r.post(ROUTE + "/plus-tard")
    async def plus_tard(c: CorpsPlusTard):
        harnais(c.harnais)
        reportes = {**reflexes.lire_reportes(etat), c.harnais: reflexes.VERSION}
        etat.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(etat, json.dumps({"plus_tard": reportes}))
        return releve()

    return r


def routes_traces(vault: Vault, publier, tache) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.post("/taches/{ident}/traces")
    async def tracer(ident: str, c: CorpsTrace):
        quand = datetime.now().strftime("%Y-%m-%d %H:%M")
        docs = ", ".join(lien(vault, d) for d in c.documents if d.strip())
        vault.consigner(ident, SECTION, f"- {quand} — {c.texte}" + (f" — {docs}" if docs else ""))
        publier("arbre")
        return tache(ident)

    return r
