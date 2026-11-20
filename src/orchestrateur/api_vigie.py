"""Signe de vie des tours : routes `/api/taches/{id}/vigie` et enrichissement de `GET /etat`.

Rôle : exposer les incidents (`GET /api/incidents`, bandeau de la tâche), la phrase d'activité, la raison d'attente et l'alerte de silence (module `vigie`),
et les gestes humains sur un tour silencieux : diagnostiquer, attendre, arrêter un processus enfant.
Frontières : aucune décision ni sonde système ici ; aucune écriture vault.
Invariants portés : INV-VIGIE-1 (un arrêt est un geste humain, borné à l'arbre du tour), INV-VIGIE-2,
INV-INCIDENT-1.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .vigie import Vigie


class CorpsEnfant(BaseModel):
    pid: int


def vue_tache(vigie: Vigie, ident: str) -> dict:
    return {"signe": vigie.vue(ident), "raison_attente": vigie.raison_attente(ident),
            "incident": vigie.m.incidents.dernier(ident)}  # INV-INCIDENT-1 : bandeau de la conversation


def enrichir_etat(vigie: Vigie, etat: dict) -> dict:
    for t in etat.get("tours", []):
        t["signe"] = vigie.vue(t["tache"])
    for f in etat.get("file", []):
        f["raison"] = vigie.raison_attente(f["tache"])
    etat["alertes_vigie"] = vigie.alertes()
    return etat


def routes(vigie: Vigie) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/incidents")
    async def incidents(limite: int = 200):
        """INV-INCIDENT-1 : vue Incidents, comptes épuisés et heure de reprise (jauge)."""
        return {"incidents": vigie.m.incidents.public(limite), "epuises": vigie.m.quota.public()}

    @r.get("/taches/{ident}/vigie")
    async def lire(ident: str):
        vigie.m.vault.tache(ident)
        return vue_tache(vigie, ident)

    @r.post("/taches/{ident}/vigie/diagnostiquer")
    async def diagnostiquer(ident: str):
        vigie.m.vault.tache(ident)
        return {"diagnostic": await vigie.diagnostiquer(ident)}

    @r.post("/taches/{ident}/vigie/attendre")
    async def attendre(ident: str):
        vigie.m.vault.tache(ident)
        vigie.attendre(ident)
        return vue_tache(vigie, ident)

    @r.post("/taches/{ident}/vigie/arreter-enfant")
    async def arreter_enfant(ident: str, c: CorpsEnfant):
        vigie.m.vault.tache(ident)
        return await vigie.arreter_enfant(ident, c.pid)

    return r
