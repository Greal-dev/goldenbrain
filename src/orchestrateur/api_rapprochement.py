"""Routes du rapprochement avant création : tâches proches, compléter une tâche, mesure.

Rôle : brancher `rapprochement` sur l'API ; `creer` est le corps de POST /api/taches (garde de
rapprochement, puis création) ; `api.py` est plafonné à 500 lignes.
Frontières : aucune ressemblance calculée ici (module `rapprochement`) ; la création reste `Moteur.creer`.
Invariants portés : INV-RAPPROCHEMENT-1 (409 + `candidates` sur correspondance forte, sauf `forcer`),
INV-RAPPROCHEMENT-2 (un complément est une création évitée), INV-INTEG-2 (lien d'office vers l'intégration),
INV-PLAFOND-1 (un agent ne lève le rangement que par `hors_rangement`).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import langues, liens, rangement, rapprochement
from .vault import Invalide, NonTrouve, exiger_description


class CorpsComplement(BaseModel):
    texte: str
    titre: str = ""  # titre de la demande d'origine : relie le complément au refus qui l'a précédé
    de: str | None = None
    sauts: int = 0


def creer(moteur, tache, c, source: str | None):
    """POST /api/taches. `source` : tâche de l'agent appelant (en-tête de `orch`), jamais candidate."""
    mesure = rapprochement.Mesure(moteur.config.donnees)
    origine = source or (c.de if c.de not in (None, "", "orch") else None)  # tâche de l'agent appelant
    if not c.conteneur and not c.parent and origine:  # B2 : sans projet dit, celui de la tâche courante
        try:
            c.conteneur = moteur.vault.tache(origine).conteneur
        except NonTrouve:
            pass
    agent = bool(c.de or source)
    if not c.forcer:
        cands = rapprochement.proches(moteur.vault, c.titre, c.description, c.conteneur,
                                      exclure=(c.parent, source, c.de))
        if rapprochement.forte(cands):
            mesure.refus(c.titre, cands)
            return JSONResponse(status_code=409, content={
                "detail": langues.t("serveur.api_rapprochement.proche"), "candidates": cands})
    if c.genre and not rangement.valide(c.genre):
        raise Invalide(langues.t("serveur.rangement.nature_inconnue", genre=c.genre))
    genre = rangement.valide(c.genre) or rangement.deduire(c.titre, c.description)  # INV-NATURE-1
    # B3 : pour un agent, `forcer` (--nouvelle) ne lève que la proximité ; le rangement se dérogue par
    # `hors_rangement`. L'interface (ni `de` ni en-tête) garde un `forcer` complet : dérogation humaine.
    if not (c.hors_rangement if agent else c.forcer) and not c.groupe:  # INV-PLAFOND-1, INV-NATURE-1
        rang = rangement.propositions(moteur.vault, moteur.config.rangement, c.titre, c.description,
                                      c.conteneur, c.parent, genre)
        if rang:
            return JSONResponse(status_code=409, content={
                "detail": langues.t(f"serveur.api_rapprochement.rangement_{rang['raison']}",
                                    ouvertes=rang["ouvertes"], plafond=rang["plafond"]), "rangement": rang})
    if agent:  # créée par un agent (corps `de` ou en-tête de `orch`)
        c.description = exiger_description(c.description, "tâche")
    parent, conteneur = c.parent, c.conteneur
    if c.groupe:  # le regroupement demandé naît sous le parent ; la tâche s'y range
        parent = moteur.creer(c.groupe, langues.t("serveur.rangement.groupe_description", titre=c.titre),
                              conteneur, parent)
        if genre:
            moteur.vault.modifier(parent, {"genre": genre})
    ident = moteur.creer(c.titre, c.description, conteneur, parent, c.lancer,
                         c.harnais, c.modele, c.echeance, c.priorite, c.mission)
    if genre:
        moteur.vault.modifier(ident, {"genre": genre})
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
