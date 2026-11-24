"""Routes du parcours « Configurer votre second cerveau » : état, examen d'un dossier, sélecteur, application, « plus tard ».

Rôle : traduire HTTP en appels à `cerveau` ; au changement de dossier, effacer l'état des premiers pas et de l'accueil (le parcours
se rejoue sur le nouveau vault) puis demander le redémarrage propre du serveur.
Frontières : sous `/api/accueil/cerveau` donc réservées au poste (INV-ACCUEIL-1) : le sélecteur lit les dossiers du poste ;
n'écrit rien dans le vault choisi, sauf à le créer vide (`creer`).
Invariants portés : INV-CERVEAU-1, INV-CERVEAU-2.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import cerveau, langues, squelette

ROUTE = "/api/accueil/cerveau"


class CorpsChemin(BaseModel):
    chemin: str = ""


class CorpsAppliquer(BaseModel):
    chemin: str
    creer: bool = False


def routes(config, moteur, vault) -> APIRouter:
    r = APIRouter()

    @r.get(ROUTE)
    async def lire():
        e = cerveau.etat(config)
        return {"propose": e["etat"] == "", "etat": e["etat"] or "jamais", "rappel": e["etat"] == "differe",
                "vault": str(vault.racine), "vide": squelette.vide(vault.racine, vault.cfg.arrivee),
                "defaut": str(vault.racine), "maison": str(Path.home())}

    @r.post(ROUTE + "/examiner")
    async def examiner(c: CorpsChemin):
        return await asyncio.to_thread(cerveau.examiner, config, c.chemin)

    @r.post(ROUTE + "/dossiers")
    async def dossiers(c: CorpsChemin):
        return await asyncio.to_thread(cerveau.lister, c.chemin)

    @r.post(ROUTE + "/appliquer")
    async def appliquer(c: CorpsAppliquer, requete: Request):
        bilan = await asyncio.to_thread(cerveau.appliquer, config, c.chemin, c.creer)
        # Le parcours se joue sur ce vault : accueil et premiers pas se reproposent (états retirés, jamais le vault).
        for f in ("accueil.json", "premiers-pas.json"):
            (config.donnees / "etat" / f).unlink(missing_ok=True)
        cerveau.poser(config, "fait", parcours=True, vault=bilan["chemin"])
        if bilan["redemarrage"]:
            requete.app.state.version.redemarrer()  # INV-VERSION-1 : arrêt normal, code 3, le lanceur relance
        moteur.publier("arbre")
        return bilan

    @r.post(ROUTE + "/plus-tard")
    async def plus_tard():
        if cerveau.etat(config)["etat"] != "fait":
            cerveau.poser(config, "differe")
        return {"etat": cerveau.etat(config)["etat"], "message": langues.t("serveur.cerveau.rappel")}

    return r
