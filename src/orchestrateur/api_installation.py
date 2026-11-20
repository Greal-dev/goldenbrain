"""Routes locales de l'assistant « Ajouter ce PC comme exécuteur » (Réglages de l'exécuteur).

Rôle : traduire HTTP en appels à `installation.Assistant` : diagnostic, UNE étape à la fois sur accord
(travail d'arrière-plan, sortie relevée par scrutation), appairage au chef.
Frontières : aucune commande ne vient du client : il désigne une étape du catalogue et rend la
commande exacte qu'il a montrée ; la garde d'`api.py` (INV-DISTANT-1) réserve ces routes au poste.
Invariants portés : INV-INSTALL-1 (accord = commande exacte, une étape à la fois), INV-INSTALL-2
(clavier fermé : une connexion qui dialogue se lance dans un terminal ; jamais d'identifiant ici),
INV-INSTALL-3 (repli en instructions à copier), INV-APPAIRAGE-1 (le jeton reçu n'est jamais rendu).
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import executeur, installation, langues

ROUTE = "/api/installation"


class CorpsAccord(BaseModel):
    accord: str = Field(max_length=500)


class CorpsLiaison(BaseModel):
    serveur: str = Field(max_length=200, pattern=r"^https?://\S+$")
    code: str = Field(max_length=32)


class Travail:
    """Une seule étape à la fois ; la sortie récente se relève par scrutation."""

    def __init__(self):
        self.verrou = threading.Lock()
        self.etape = ""
        self.lignes: deque[str] = deque(maxlen=80)
        self.en_cours = False
        self.resultat: dict | None = None

    def demarrer(self, assistant: installation.Assistant, ident: str, accord: str) -> None:
        with self.verrou:
            if self.en_cours:
                raise HTTPException(409, langues.t("serveur.api_installation.deja_en_cours"))
            self.etape, self.en_cours, self.resultat = ident, True, None
            self.lignes.clear()
        threading.Thread(target=self._courir, args=(assistant, ident, accord), daemon=True).start()

    def _courir(self, assistant: installation.Assistant, ident: str, accord: str) -> None:
        try:
            r = assistant.executer(ident, accord, interactif=False, sortie=self.lignes.append)
            self.resultat = {"code": r.code, "etat": r.etat, "repli": r.repli}
        except Exception as e:  # l'échec se lit dans l'interface, jamais de mort silencieuse
            self.resultat = {"code": None, "etat": "", "repli": "", "erreur": str(e)}
        finally:
            self.en_cours = False

    def vue(self) -> dict:
        return {"etape": self.etape, "en_cours": self.en_cours, "sortie": list(self.lignes), "resultat": self.resultat}


def routes() -> APIRouter:
    r = APIRouter()
    assistant = installation.Assistant()
    travail = Travail()

    @r.get(ROUTE)
    async def diagnostic():
        serveur, jeton = executeur.liaison()
        plan = await asyncio.to_thread(assistant.plan)
        return {"plateforme": assistant.systeme.plateforme, "admin": assistant.systeme.est_admin(), "etapes": plan,
                "liaison": {"serveur": serveur, "jeton_garde": bool(jeton)}}

    @r.get(ROUTE + "/travail")
    async def en_cours():
        return travail.vue()

    @r.post(ROUTE + "/etapes/{ident}")
    async def lancer(ident: str, c: CorpsAccord):
        try:
            ligne = assistant.ligne(ident)
        except installation.EtapeInconnue:
            raise HTTPException(404, langues.t("serveur.api_installation.etape_inconnue")) from None
        if ligne["etat"] == "bloque":
            raise HTTPException(409, langues.t("serveur.api_installation.d_abord", etapes=", ".join(ligne["attend"])))
        if ligne["commande"] and c.accord != ligne["commande"]:  # INV-INSTALL-1 : on ne lance que ce qui a été montré
            raise HTTPException(400, langues.t("serveur.api_installation.accord_refuse"))
        travail.demarrer(assistant, ident, c.accord)
        return {"demarre": ident}

    @r.post(ROUTE + "/appairage")
    async def appairer(c: CorpsLiaison):
        # INV-APPAIRAGE-1 : le jeton va dans le fichier de liaison, jamais dans la réponse.
        try:
            nom = await asyncio.to_thread(executeur.lier, c.serveur, c.code)
        except executeur.AppairageRefuse as e:
            raise HTTPException(400, str(e)) from None
        relie = await asyncio.to_thread(installation.verifier_chef, c.serveur, executeur.liaison()[1])
        return {"nom": nom, "relie": relie}

    return r
