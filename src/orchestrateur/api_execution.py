"""Routes de l'exécution par tâche ou regroupée : `/api/execution` et la fiche d'une sous-tâche.

Rôle : lire et poser le réglage d'un nœud (tâche ou conteneur) ; laisser la conversation de la
tâche mère écrire la fiche et le statut proposé d'une sous-tâche regroupée (`orch fiche`).
Frontières : la logique vit dans `regroupement.py`.
Invariants portés : INV-REGROUPE-1 (réglage hérité, décision motivée), INV-REGROUPE-2 (fiche d'une
sous-tâche écrite par la seule conversation de sa mère, en exécution regroupée).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import regroupement


class CorpsReglage(BaseModel):
    noeud: str
    reglage: str  # automatique | par_tache | regroupee | "" (hériter)


class CorpsFiche(BaseModel):
    de: str
    statut: str = ""
    fait: str = ""
    resultat: str = ""
    essai: str = ""
    situation: str = ""
    reste: str = ""
    prochain_pas: str = ""


def routes(moteur) -> APIRouter:
    r = APIRouter()

    @r.get("/api/execution")
    async def lire(noeud: str):
        return {"noeud": noeud, **regroupement.vue(moteur, noeud)}

    @r.put("/api/execution")
    async def regler(c: CorpsReglage):
        regroupement.regler(moteur, c.noeud, c.reglage)
        return {"noeud": c.noeud, **regroupement.vue(moteur, c.noeud)}

    @r.post("/api/taches/{ident}/fiche-regroupee")
    async def fiche(ident: str, c: CorpsFiche):
        champs = c.model_dump(exclude={"de", "statut"})
        return {"tache": ident, "statut": regroupement.ecrire_fiche(moteur, ident, c.de, c.statut, champs)}

    return r
