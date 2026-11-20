"""Routes du rapprochement avant création : tâches proches, compléter une tâche, mesure.

Rôle : brancher `rapprochement` sur l'API ; `creer` est le corps de POST /api/taches (garde de
rapprochement, puis création) ; `api.py` est plafonné à 500 lignes.
Frontières : aucune ressemblance calculée ici (module `rapprochement`) ; la création reste `Moteur.creer`.
Invariants portés : INV-RAPPROCHEMENT-1 (409 + `candidates` sur correspondance forte, sauf `forcer`),
INV-RAPPROCHEMENT-2 (un complément est une création évitée), INV-INTEG-2 (lien d'office vers l'intégration).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import langues, liens, rapprochement
from .vault import exiger_description


class CorpsComplement(BaseModel):
    texte: str
    titre: str = ""  # titre de la demande d'origine : relie le complément au refus qui l'a précédé
    de: str | None = None
    sauts: int = 0


def creer(moteur, tache, c, source: str | None):
    """POST /api/taches. `source` : tâche de l'agent appelant (en-tête de `orch`), jamais candidate."""
    mesure = rapprochement.Mesure(moteur.config.donnees)
    if not c.forcer:
        cands = rapprochement.proches(moteur.vault, c.titre, c.description, c.conteneur,
                                      exclure=(c.parent, source, c.de))
        if rapprochement.forte(cands):
            mesure.refus(c.titre, cands)
            return JSONResponse(status_code=409, content={
                "detail": langues.t("serveur.api_rapprochement.proche"), "candidates": cands})
    if c.de or source:  # créée par un agent (corps `de` ou en-tête de `orch`)
        c.description = exiger_description(c.description, "tâche")
    ident = moteur.creer(c.titre, c.description, c.conteneur, c.parent, c.lancer,
                         c.harnais, c.modele, c.echeance, c.priorite, c.mission)
    liens.relier_integration(moteur.vault, ident)  # INV-INTEG-2 : UI, `orch creer`, `orch deleguer`
    mesure.creation(c.titre)
    return tache(ident)


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api/rapprochement")
    vault = moteur.vault

    @r.get("/proches")
    async def lister(titre: str = "", description: str = "", conteneur: str | None = None):
        cands = rapprochement.proches(vault, titre, description, conteneur or None)
        return {"candidates": cands, "forte": rapprochement.forte(cands)}

    @r.get("/mesure")
    async def mesure():
        return rapprochement.Mesure(moteur.config.donnees).vue()

    @r.post("/taches/{ident}/completer", status_code=202)
    async def completer(ident: str, c: CorpsComplement):
        # Chemin existant des messages d'une tâche : relance le tour si elle est confiée à un agent.
        etat = moteur.soumettre(ident, f"[Complément demandé à la place d'une nouvelle tâche]\n{c.texte}",
                                c.de, c.sauts)
        rapprochement.Mesure(moteur.config.donnees).complement(ident, c.titre)  # INV-RAPPROCHEMENT-2
        return {"etat_execution": etat}

    return r
