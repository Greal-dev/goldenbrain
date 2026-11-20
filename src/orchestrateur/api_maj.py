"""Routes `/api/mise-a-jour` : état du retard sur la branche de diffusion, mise à jour d'un clic.

Rôle : traduire HTTP en appels à `mise_a_jour.py`, hors de la boucle d'événements ; le contrôle
distant (`git fetch`) est fait au plus une fois par heure, ou à la demande (`?actualiser=1`).
Frontières : aucune logique git ici (`mise_a_jour`, `nouveautes`) ; le redémarrage est celui d'INV-VERSION-1.
Invariants portés : INV-MAJ-1 (409 si un tour tourne, ou si git refuse l'avance rapide) ;
INV-MAJ-4 (branche du canal choisi) ; INV-VERSION-3 (redémarrage du serveur différé à la fin des tours) ;
INV-SIGNAL-1 (`/api/signaler` : adresses de ticket pré-remplies sans donnée personnelle).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import langues, maj_auto, mise_a_jour, nouveautes, signalement
from .config import RACINE_DEPOT, Config
from .vault import Conflit, ErreurOrch, TropTot

TTL_S, TTL_ERREUR_S = 3600, 300  # hors ligne : on réessaie plus tôt


class CorpsRedemarrer(BaseModel):
    force: bool = False
    par: str = Field("", max_length=80)  # appelant déclaré, pour la trace (INV-VERSION-2)


class CorpsMajAuto(BaseModel):
    actif: bool | None = None
    delai_min: int | None = None
    fenetre_debut: str | None = None
    fenetre_fin: str | None = None
    canal: str | None = None  # INV-MAJ-4 : « stable » ou « beta »


def routes(config: Config, moteur, version, depot=RACINE_DEPOT) -> APIRouter:
    r, c = APIRouter(), config.mise_a_jour
    memo: dict = {"instant": 0.0, "valeur": None}
    verrou = asyncio.Lock()

    async def controle(actualiser: bool) -> dict:
        async with verrou:
            ttl = TTL_ERREUR_S if (memo["valeur"] or {}).get("erreur") else TTL_S
            if memo["valeur"] is None or actualiser or time.monotonic() - memo["instant"] >= ttl:
                try:
                    suivie, canaux = auto.suivie()
                    v = await asyncio.to_thread(mise_a_jour.etat, depot, suivie, True, canaux)
                    if v.get("retard"):  # avis « Quoi de neuf » : ce qu'apporte la version en attente
                        v["nouveautes"] = await asyncio.to_thread(
                            nouveautes.quoi_de_neuf, depot, f"{v['distant']}/{v['branche']}")
                except ErreurOrch as e:
                    v = {**(memo["valeur"] or {"depot": True, "branche": c.branche}), "erreur": str(e)}
                else:
                    v.pop("erreur", None)
                v["canal"] = auto.reglage["canal"]
                memo.update(instant=time.monotonic(), valeur=v,
                            controle=dt.datetime.now().isoformat(timespec="seconds"))
            return {**memo["valeur"], "dernier_controle": memo.get("controle")}

    auto = maj_auto.MajAuto(moteur, version, depot, c, controle, lambda: memo.update(valeur=None),
                            config.donnees / "etat" / "maj_auto.json")
    r.auto = auto  # lu par `creer_app` (démarrage et arrêt dans le lifespan)
    version.complements = lambda: {k: v for k, v in auto.vue().items() if k != "dans_fenetre"}

    @r.post("/api/redemarrer", status_code=202)
    async def redemarrer(request: Request, c: CorpsRedemarrer | None = None):
        v = version.tracer(request, c)  # INV-VERSION-2 : chaque appel est tracé, accepté ou refusé
        if not (c and c.force):
            if m := v.refus_garde(): raise TropTot(m)
            if moteur.occupe(): raise Conflit(langues.t("serveur.api_maj.occupe_redemarrer"))
        v.redemarrer()  # INV-VERSION-1 : arrêt normal (lifespan), sortie 3
        return {"code_sortie": v.code_sortie}

    @r.get("/api/maj-auto")
    async def lire_auto():
        return auto.vue()

    @r.put("/api/maj-auto")
    async def regler_auto(corps: CorpsMajAuto):
        return auto.regler(corps.model_dump())

    @r.post("/api/maj-auto/activite")
    async def activite():
        auto.activite()  # INV-MAJ-3 : l'écran est utilisé, le redémarrage attend
        return {}

    @r.delete("/api/maj-auto/bandeau")
    async def fermer_bandeau():
        auto.fermer_bandeau()
        return {}

    @r.get("/api/mise-a-jour")
    async def lire(actualiser: bool = False):
        return await controle(actualiser)

    @r.post("/api/mise-a-jour")
    async def appliquer():
        if moteur.occupe():
            raise Conflit(langues.t("serveur.api_maj.occupe_maj"))
        async with moteur.exclusif():  # aucun tour ne démarre pendant l'avance du dépôt
            res = await asyncio.to_thread(mise_a_jour.appliquer, depot, *auto.suivie())
        memo["valeur"] = None  # le prochain contrôle repart du dépôt
        if res["appliquee"]:
            version.redemarrer()  # INV-VERSION-1 : arrêt normal, sortie 3, `lancer.cmd` relance
        return {**res, "redemarre": res["appliquee"]}

    @r.get("/api/signaler")
    async def signaler():
        # INV-SIGNAL-1 : version, canal et système seulement ; l'utilisateur relit le ticket avant de l'envoyer.
        return await asyncio.to_thread(signalement.adresses, depot, auto.reglage["canal"])

    @r.post("/api/redemarrer-differe", status_code=202)
    async def armer_differe():
        version.armer_differe(moteur.occupe)  # INV-VERSION-3
        return {"differe": version.differe}

    @r.delete("/api/redemarrer-differe")
    async def annuler_differe():
        version.annuler_differe()
        return {"differe": version.differe}

    return r
