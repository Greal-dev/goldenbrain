"""Écran « En cours » : `GET /api/travaux`, pause et reprise d'un tour à la main.

Rôle : rassembler en une lecture ce qui travaille (tours, sous-agents, avancement), ce qui attend
(file et raison), les routines à venir et les incidents ouverts ; exposer la pause manuelle.
Frontières : lecture seule hors pause/reprise ; aucune sonde système, aucun minuteur — l'écran se
recharge sur les événements SSE existants. Aucune écriture vault.
Invariants portés : INV-TRAVAUX-1 (rien n'est sondé : tout vient de l'état déjà tenu),
INV-TRAVAUX-2 (pause manuelle hors régulation RAM).
"""

from __future__ import annotations

from fastapi import APIRouter

ROUTINES_MAX = 10
INCIDENTS_MAX = 20


def _projet(vault, ident: str) -> str:
    try:
        return " › ".join(vault.fil_ariane(ident))  # ancêtres seuls : la tâche n'y est pas
    except Exception:  # noqa: BLE001 — tâche disparue entre deux lectures
        return ""


def _moteur(moteur, ident: str, tour=None) -> tuple[str, str]:
    try:
        fm = moteur.vault.tache(ident).fm
    except Exception:  # noqa: BLE001
        fm = {}
    harnais = str(fm.get("harnais") or getattr(getattr(tour, "harnais", None), "nom", "")
                  or moteur.config.moteur.harnais_defaut)
    return harnais, str(fm.get("modele") or "")


def travaux(moteur) -> dict:
    etat = moteur.etat_global()
    vigie = moteur.vigie
    tours = []
    for t in etat["tours"]:
        harnais, modele = _moteur(moteur, t["tache"], moteur.tours.get(t["tache"]))
        tours.append({**t, "projet": _projet(moteur.vault, t["tache"]), "harnais": harnais,
                      "modele": modele, "signe": vigie.vue(t["tache"])})
    file = [{**f, "projet": _projet(moteur.vault, f["tache"]),
             "raison": vigie.raison_attente(f["tache"])} for f in etat.get("file", [])]
    routines = sorted((r for r in moteur.routines.liste()
                       if r.get("prochaine") and r.get("etat") == "active"),
                      key=lambda r: r["prochaine"])[:ROUTINES_MAX]
    incidents = [i for i in moteur.incidents.public() if not i.get("clos")][:INCIDENTS_MAX]
    return {"tours": tours, "file": file, "routines": routines, "incidents": incidents}


def routes(moteur) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/travaux")
    async def lire():
        return travaux(moteur)

    @r.post("/taches/{ident}/suspendre")
    async def suspendre(ident: str):
        moteur.vault.tache(ident)
        moteur._sem.pauser_main(ident)  # INV-TRAVAUX-2
        return {"pause": True}

    @r.post("/taches/{ident}/continuer")
    async def continuer(ident: str):
        moteur.vault.tache(ident)
        moteur._sem.reprendre_main(ident)
        return {"pause": False}

    return r
