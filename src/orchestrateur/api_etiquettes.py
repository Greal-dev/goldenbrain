"""Routes des étiquettes libres : liste, pose et retrait sur une tâche, consigne, renommage et fusion.

Rôle : traduire HTTP en appels à `etiquettes` et `lot_statuts` ; fournir à `GET /api/taches/{id}` les étiquettes,
leurs consignes et les tâches liées par étiquette ; `GET /api/etiquettes` sert le filtre et Réglages.
Frontières : aucune logique d'étiquette ici (module `etiquettes`) ; le renommage et la fusion passent par un lot
annulable (INV-LOT-1). La consigne, le renommage et la fusion sont des gestes humains : refusés à un agent.
Invariants portés : INV-ETIQUETTE-1, INV-ETIQUETTE-4 (vue par étiquette, lecture seule), INV-ETIQUETTE-2 (un agent pose une étiquette connue, ne l'invente pas, ne
retire pas celle d'un autre), INV-LOT-1.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import etiquettes, langues, lot_statuts, vue_etiquette
from .vault import Conflit, Invalide


class CorpsPose(BaseModel):
    ajouter: list[str] = []
    retirer: list[str] = []


class CorpsConsigne(BaseModel):
    consigne: str = ""


class CorpsRenommage(BaseModel):
    de: str
    vers: str


def vue(moteur, ident: str) -> dict:
    return etiquettes.vue(moteur.vault, moteur.etiquettes, ident)


def _humain(request: Request) -> None:
    if request.headers.get("x-orch-tache"):
        raise Conflit(langues.t("serveur.etiquettes.humain_seul"))


def renommer(moteur, de: str, vers: str) -> dict:
    """Renomme `de` en `vers` sur toutes les fiches (fusion si `vers` existe) ; annulable par son lot."""
    de, vers = etiquettes.normaliser(de), etiquettes.normaliser(vers)
    if de == vers:
        raise Invalide(langues.t("serveur.etiquettes.identiques"))
    taches = moteur.vault.index()[0]
    ids = [k for k, t in taches.items() if de in etiquettes.de(t.fm)]
    if not ids and de not in moteur.etiquettes.declarees():
        raise Invalide(langues.t("serveur.etiquettes.inconnue", mot=de))
    r = {"lot": None, "changees": [], "exclues": []}
    avant = moteur.etiquettes.deplacer(de, vers)
    if ids:
        try:
            r = lot_statuts.appliquer(moteur, ids, etiquettes={"ajouter": [vers], "retirer": [de]},
                                      renommage=avant)
        except Exception:
            moteur.etiquettes.restaurer(avant)
            raise
    moteur.publier("arbre")
    return {**r, "de": de, "vers": vers}


def routes(moteur, tache) -> APIRouter:
    r = APIRouter()

    @r.get("/api/etiquettes")
    async def lister():
        return {"etiquettes": [{"mot": m, **v} for m, v in
                               etiquettes.connues(moteur.vault.index()[0], moteur.etiquettes).items()]}

    @r.get("/api/etiquettes/{mot}/vue")
    async def vue_par_etiquette(mot: str):
        return vue_etiquette.assembler(moteur, mot)

    @r.post("/api/taches/{ident}/etiquettes")
    async def poser(ident: str, c: CorpsPose, request: Request):
        if request.headers.get("x-orch-tache"):  # INV-ETIQUETTE-2
            if c.retirer:
                raise Conflit(langues.t("serveur.etiquettes.agent_retire"))
            connues = etiquettes.connues(moteur.vault.index()[0], moteur.etiquettes)
            for mot in map(etiquettes.normaliser, c.ajouter):
                if mot not in connues:
                    raise Invalide(langues.t("serveur.etiquettes.agent_inconnue", mot=mot, id=ident,
                                             existantes=", ".join(list(connues)[:15]) or "—"))
        else:
            for mot in c.ajouter:  # un mot posé à la main devient une étiquette connue
                moteur.etiquettes.declarer(mot)
        etiquettes.appliquer(moteur.vault, ident, c.ajouter, c.retirer)
        moteur.publier("arbre")
        return tache(ident)

    @r.put("/api/etiquettes/{mot}")
    async def consigne(mot: str, c: CorpsConsigne, request: Request):
        _humain(request)
        return {"mot": moteur.etiquettes.declarer(mot, c.consigne), "consigne": c.consigne.strip()}

    @r.delete("/api/etiquettes/{mot}")
    async def oublier(mot: str, request: Request):
        _humain(request)
        mot = etiquettes.normaliser(mot)
        if etiquettes.utilisees(moteur.vault.index()[0]).get(mot):
            raise Conflit(langues.t("serveur.etiquettes.encore_utilisee", mot=mot))
        moteur.etiquettes.oublier(mot)
        return {"mot": mot}

    @r.post("/api/etiquettes/renommer")
    async def renommer_route(c: CorpsRenommage, request: Request):
        _humain(request)
        return renommer(moteur, c.de, c.vers)

    return r
