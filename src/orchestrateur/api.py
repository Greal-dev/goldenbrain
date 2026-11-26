"""API HTTP de l'orchestrateur (FastAPI) : routes JSON, flux SSE, garde locale, statiques `web/`.

Rôle : traduire HTTP en appels au moteur et au vault, et leurs erreurs en codes HTTP.
Frontières : aucune logique métier ; aucun chemin client n'est utilisé tel quel.
Invariants portés : INV-API-1 (garde Host et en-tête), INV-VAULT-3 (identifiants résolus
par l'index, jamais de chemin fourni par le client), INV-VERROU-1 (gestes humains gardés).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (api_lecteur, api_styles, api_compagnon, api_apprendre, api_accueil, api_lignes, api_livrables, modeles, api_appareils, api_arbre, api_codespace, api_executeurs, api_installation, api_retour, api_compactage, api_decisions,
               api_economie, api_etoile, api_executant, api_execution, api_feux, api_interface, api_maj, api_notes, api_pilotage, api_poste,
               api_rapprochement, api_resultat, api_routines, api_simultanes, api_manager, api_telegram, api_temps, api_titre,
               api_reflexes, api_travaux, api_validation, api_vigie, api_chaines, api_lots, api_etiquettes)
from .api_temps import CorpsTache
from . import (appareils, codespace, conseil, console, decisions, depot, etat_main, executant, geste, guide, langues, liens, recherche, regroupement,
               prechauffage, reprise, temps, transformations, version, vigie)
from .alignement import Aligneur
from .catalogue import Catalogue
from .config import RACINE_DEPOT, Config
from .harnais import distant
from .jardinage import Jardinier
from .routines import Routines
from .telegram import Connecteur
from .moteur import Moteur, session_valide
from .verrou import Occupee
from .vault import ErreurOrch, Invalide

WEB = RACINE_DEPOT / "web"
# no-cache : l'interface est servie sans build, le navigateur doit revalider chaque module.
ENTETES = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache",
           "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"}
# INV-API-1 : seule exception, un fichier du vault (PDF) s'incorpore dans l'interface elle-même.
ENTETES_FICHIER = {**ENTETES, "X-Frame-Options": "SAMEORIGIN",
                   "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'"}

class CorpsMessage(BaseModel):
    texte: str
    de: str | None = None
    sauts: int = 0
    harnais: str | None = None
    modele: str | None = None


class CorpsMoteur(BaseModel):
    harnais: str | None = None
    modele: str | None = None


class CorpsForcer(BaseModel):
    forcer: bool = False  # INV-VERROU-1 : geste confirmé malgré un agent au travail


class CorpsStatut(CorpsForcer):
    statut: str


class CorpsDeplacer(CorpsForcer):
    conteneur: str | None = None
    parent: str | None = None


class CorpsDeriver(BaseModel):
    titre: str
    lien: str
    avec_fil: bool = False
    message: str | None = None


class CorpsPromouvoir(CorpsForcer):
    nom: str | None = None
    decouper: bool = True


class CorpsReduire(CorpsForcer):
    conteneur: str
    point_git: bool = True


class CorpsConseil(BaseModel):
    action: str
    tache: str | None = None
    conteneur: str | None = None


class CorpsSession(BaseModel):
    session: str
    harnais: str | None = None


class CorpsLien(BaseModel):
    type: str
    cible: str


class CorpsPersona(BaseModel):
    nom: str = ""
    actif: bool = True
    declenchement: str = "filtre"
    casquettes: list[str] = []
    conteneurs: list[str] = []
    mots: list[str] = []
    harnais: str = ""
    modele: str = ""
    mandat: str = ""
    focus: str = ""


class CorpsSolliciter(BaseModel):
    persona: str
    question: str = ""


class CorpsTexte(CorpsForcer):
    texte: str


def creer_app(config: Config, moteur: Moteur | None = None) -> FastAPI:
    moteur = moteur or Moteur(config)
    langues.regler(config.interface.langue)  # INV-LANGUE-1
    distant.GH = config.gh
    vault = moteur.vault
    jardinier = Jardinier(moteur)
    moteur.routines = Routines(moteur)  # INV-ROUTINE-1 : lu aussi par l'arbre et les « Décisions »
    connecteur = Connecteur(moteur)
    catalogue = Catalogue(config.harnais, moteur.registre)
    aligneur = Aligneur(vault, config.alignement.externes)
    moteur.vigie = vigie.Vigie(moteur)  # INV-VIGIE-1 : signe de vie des tours

    @asynccontextmanager
    async def cycle(_: FastAPI):
        # INV-JARD-1, INV-AGENTSCC-1, INV-ROUTINE-3, INV-CHAINE-4 : planificateurs de fond, arrêtés avec le serveur.
        fond = [asyncio.create_task(b()) for b in (jardinier.boucle, moteur.agents_cc.boucle, moteur.routines.boucle, moteur.chaines.boucle)]
        moteur.vigie.demarrer()
        # INV-EXEC-1 : tours coupés par l'arrêt, repris une fois ; INV-EXEC-10 : un tour repris d'office
        # n'est pas aussi relancé par un réveil sur quota (jamais les deux).
        for ident in reprise.reprendre_au_demarrage(moteur):
            moteur.annuler_reveil(ident)
        moteur.demarrer_reveils()
        app.state.maj_auto.demarrer()  # INV-MAJ-3
        connecteur.demarrer()  # INV-TELEGRAM-1 : seulement si activé dans les Réglages
        await prechauffage.chauffer_tout(moteur, catalogue.lister, routeur_maj.chauffer, routeur_arbre.chauffer)  # INV-FROID-1 : premier écran chaud avant la première requête
        yield
        for x in fond: x.cancel()
        moteur.vigie.fermer()
        app.state.maj_auto.fermer()
        connecteur.arreter()
        await moteur.fermer()  # INV-EXEC-1 : à l'arrêt, aucun processus d'agent ne survit

    app = FastAPI(title="orchestrateur", lifespan=cycle)
    app.state.moteur = moteur
    app.state.jardinier = jardinier
    app.state.telegram = connecteur
    app.state.aligneur, app.state.version = aligneur, version.Version()  # INV-VERSION-1 : empreinte au démarrage
    app.state.appareils = connecteur.appareils = registre = appareils.Appareils(config.donnees)  # INV-DISTANT-6, INV-APPAIRAGE-2
    hotes = {f"{h}:{config.port}" for h in ("127.0.0.1", "localhost", config.executeurs.ecoute,  # INV-DISTANT-1
                                            config.distant.nom_hote if config.executeurs.ecoute else "") if h}

    @app.middleware("http")
    async def garde(request: Request, appel):
        # INV-API-1 : défense contre le DNS rebinding et les requêtes intersites du navigateur.
        if request.headers.get("host") not in hotes:
            reponse = JSONResponse({"detail": langues.t("serveur.api.hote_refuse")}, status_code=403)
        elif refus := api_appareils.refus(registre, moteur.executeurs, config, request):
            reponse = JSONResponse({"detail": refus[1]}, status_code=refus[0])  # INV-DISTANT-1, INV-DISTANT-6
        elif request.method != "GET" and request.headers.get("x-orchestrateur") != "1":
            reponse = JSONResponse({"detail": langues.t("serveur.api.entete_requis")}, status_code=403)
        elif refus := executant.refus_agent(vault, request.method, request.url.path, request.headers.get("x-orch-tache") or ""):
            reponse = JSONResponse({"detail": refus}, status_code=409)  # INV-EXECUTANT-1
        elif f := api_interface.famille_fermee(config.interface, request.url.path, request.method):
            reponse = JSONResponse({"detail": langues.t("serveur.api.fonction_desactivee", fonction=f)}, status_code=409)
        else:
            reponse = await appel(request)
            if reponse.status_code == 404 and request.url.path.startswith("/api/"):
                reponse = await app.state.version.marquer_404(reponse)  # INV-VERSION-1
        # INV-API-1 : l'interface ne peut être encadrée par une page tierce (clickjacking).
        reponse.headers.update(api_lecteur.entetes(request.url.path, reponse.headers.get("content-security-policy")) or (ENTETES_FICHIER if request.url.path == "/api/vault/fichier" else {**ENTETES, "Cache-Control": "no-store"} if request.url.path.startswith("/api/compagnon/") else ENTETES))  # INV-PWA-2 : l'instantané n'entre pas dans le cache HTTP
        return reponse

    @app.exception_handler(ErreurOrch)
    async def erreur_metier(_: Request, e: ErreurOrch):
        # INV-VERROU-1 : le demi-verrou dit à l'interface qui travaille, pour confirmer.
        occupee = {"occupee": e.occupee} if isinstance(e, Occupee) else {}
        return JSONResponse({"detail": str(e), **occupee}, status_code=e.code)

    @app.exception_handler(RequestValidationError)
    async def erreur_entree(_: Request, e: RequestValidationError):
        champs = ", ".join(".".join(map(str, x["loc"][1:])) for x in e.errors())
        return JSONResponse({"detail": langues.t("serveur.api.entree_invalide", champs=champs)}, status_code=400)

    def tache(ident: str) -> dict:
        d, origine = depot.dossier_de_travail(vault, ident)
        return {**vault.detail(ident), "etat_execution": moteur.etat_de(ident),
                "reprise_auto": moteur.reprise_auto.attendue(ident), "main": etat_main.lire(moteur, vault.tache(ident), profond=True),  # INV-REPRISE-1, INV-MAIN-1
                "dossier_travail": d, "dossier_travail_origine": origine,
                "attente_poste": moteur.attente_poste(ident), "rang_poste": moteur.poste.rang(ident),  # INV-POSTE-1
                "pause_ram": moteur._sem.en_pause(ident), "pause": moteur.pause_de(ident),  # INV-SIMULT-1, INV-EXEC-10
                "controle": moteur.controle_vue(ident),  # INV-CONTROLE-1
                "attente_prerequis": moteur.attente_prerequis(ident),  # INV-ORDO-1
                "rang_file": moteur.rang_file(ident),  # INV-ORDO-2
                "execution": regroupement.vue(moteur, ident),  # INV-REGROUPE-1
                **api_vigie.vue_tache(moteur.vigie, ident),  # INV-VIGIE-1, INV-VIGIE-2
                "liens": liens.refs(vault.index()[0], ident), **executant.vue(vault, ident),  # INV-EXECUTANT-1
                "revues": moteur.revues.derniers(ident), "renvois": moteur.revues.nb_renvois(ident),
                **temps.vue(vault, vault.tache(ident)), **api_etiquettes.vue(moteur, ident)}

    def harnais_de(ident: str):
        t = vault.tache(ident)
        nom = str(t.fm.get("harnais") or config.moteur.harnais_defaut)
        if nom not in moteur.registre:
            raise Invalide(langues.t("serveur.api.harnais_inconnu", nom=nom))
        conf = depot.conf_harnais(vault, config.harnais.get(nom, {}), ident)
        with suppress(Invalide):  # tâche au codespace : transcript et reprise y restent
            conf = codespace.conf_tour(conf, nom, vault, t)
        return t, nom, moteur.executeurs.releve(ident, moteur.registre[nom](conf))  # INV-DISTANT-2

    @app.get("/api/conteneurs")
    async def conteneurs():
        return [{"id": c.id, "titre": c.titre, "casquette": c.casquette, "operation": c.operation}
                for c in vault.index()[1].values()]

    @app.get("/api/etat")
    async def etat():
        return {**api_vigie.enrichir_etat(moteur.vigie, moteur.etat_global()),  # INV-VIGIE-1
                "decisions": decisions.compter(moteur),
                "version": await app.state.version.etat()}

    @app.post("/api/conseil")
    async def avis_conseil(c: CorpsConseil):
        return await conseil.avis(moteur, c.action, c.tache, c.conteneur)

    @app.post("/api/conteneurs/reduire")
    async def reduire(c: CorpsReduire):
        moteur.demi_verrou(c.conteneur, c.forcer)  # INV-VERROU-1 ; INV-ALIGN-2 reste dur
        r = await transformations.reduire(moteur, aligneur, c.conteneur, c.point_git)
        return {"tache": tache(r["tache"]), "archive": r["archive"]}

    @app.get("/api/taches/{ident}")
    async def lire(ident: str):
        return tache(ident)

    @app.post("/api/taches", status_code=201)
    async def creer(c: CorpsTache, request: Request):
        return api_rapprochement.creer(moteur, tache, c, request.headers.get("x-orch-tache"))  # INV-RAPPROCHEMENT-1

    @app.post("/api/taches/{ident}/messages", status_code=202)
    async def message(ident: str, c: CorpsMessage):
        return {"etat_execution": moteur.soumettre(ident, c.texte, c.de, c.sauts,  # INV-EXEC-11 : humain sans `de`
                                                   c.harnais, c.modele, humain=not c.de)}

    @app.get("/api/harnais")
    async def harnais():
        return await catalogue.lister()

    @app.post("/api/taches/{ident}/moteur")
    async def changer_moteur(ident: str, c: CorpsMoteur):
        moteur.changer_moteur(ident, c.harnais, c.modele)
        return tache(ident)

    @app.post("/api/taches/{ident}/reprise")
    async def reprendre_maintenant(ident: str):
        vault.tache(ident)
        moteur.reprendre_maintenant(ident)  # INV-EXEC-10
        return {"etat_execution": moteur.etat_de(ident)}

    @app.post("/api/taches/{ident}/arret")
    async def arret(ident: str):
        return {"etat_execution": await moteur.arreter(ident)}

    @app.post("/api/taches/{ident}/relancer", status_code=202)
    async def relancer(ident: str):
        return {"etat_execution": reprise.relancer(moteur, ident)}  # INV-EXEC-1 : geste humain

    @app.post("/api/taches/{ident}/statut")
    async def statut(ident: str, c: CorpsStatut):
        moteur.demi_verrou(ident, c.forcer, seule=True)  # INV-VERROU-1
        vault.poser_statut(ident, c.statut, humain=True)
        moteur.liberer(ident)  # INV-EXEC-11 : geste humain, la file retenue repart (ou tombe si close)
        return tache(ident)

    @app.post("/api/taches/{ident}/deplacer")
    async def deplacer(ident: str, c: CorpsDeplacer):
        if bool(c.conteneur) == bool(c.parent):
            raise Invalide(langues.t("serveur.api.conteneur_ou_parent"))
        moteur.demi_verrou(ident, c.forcer)  # INV-VERROU-1 : ses sous-tâches suivent
        if c.conteneur:
            vault.deplacer_conteneur(ident, c.conteneur)
        else:
            vault.deplacer_parent(ident, c.parent)
        moteur.publier("arbre")
        return tache(ident)

    @app.post("/api/taches/{ident}/deriver", status_code=201)
    async def deriver(ident: str, c: CorpsDeriver):
        return tache(moteur.deriver(ident, c.titre, c.lien, c.avec_fil, c.message))

    @app.post("/api/taches/{ident}/promouvoir")
    async def promouvoir(ident: str, c: CorpsPromouvoir):
        moteur.demi_verrou(ident, c.forcer)  # INV-VERROU-1
        conteneur = transformations.promouvoir(moteur, ident, c.nom, c.decouper)
        return {"conteneur": conteneur, "tache": tache(ident)}

    @app.post("/api/taches/{ident}/session")
    async def session(ident: str, c: CorpsSession):
        if c.harnais and c.harnais not in moteur.registre:
            raise Invalide(langues.t("serveur.api.harnais_inconnu", nom=c.harnais))
        maj = {"session": session_valide(c.session), **({"harnais": c.harnais} if c.harnais else {})}
        vault.modifier(ident, maj)
        moteur.publier("arbre")
        return tache(ident)

    @app.post("/api/taches/{ident}/natif")
    async def natif(ident: str):
        return moteur.natif.ouvrir(ident)  # INV-NATIF-1

    @app.post("/api/taches/{ident}/console")
    async def ouvrir_console(ident: str):
        t = tache(ident)
        commande = console.ouvrir(t["id"], t["titre"], f"http://127.0.0.1:{config.port}",
                                  str(RACINE_DEPOT / "orch.py"))
        return {"commande": commande}

    @app.post("/api/taches/{ident}/liens")
    async def lier(ident: str, c: CorpsLien):
        liens.lier(vault, ident, c.type, c.cible)
        moteur.publier("arbre")
        return tache(ident)

    @app.post("/api/taches/{ident}/liens/retirer")
    async def delier(ident: str, c: CorpsLien):
        liens.delier(vault, ident, c.type, c.cible)
        moteur.publier("arbre")
        return tache(ident)

    @app.get("/api/recherche")
    async def chercher(q: str = "", limite: int = 20):
        return recherche.chercher(vault, q, min(max(limite, 1), 200))

    @app.get("/api/agents-cc")
    async def agents_cc(relever: bool = False):
        # INV-AGENTSCC-1 : lecture seule ; `relever` relit le dossier de Claude Code maintenant.
        if relever:
            await asyncio.to_thread(moteur.agents_cc.relever)
            moteur.publier("arbre")
        return {"actif": moteur.agents_cc.actif(), "derniere": moteur.agents_cc.etat.get("derniere"),
                "groupes": await asyncio.to_thread(moteur.agents_cc.vue)}

    @app.get("/api/jardinage")
    async def jardinage():
        return jardinier.public()

    @app.post("/api/jardinage", status_code=202)
    async def jardiner():
        return {"tache": jardinier.lancer()}

    @app.get("/api/equipe")
    async def equipe():
        return moteur.revues.equipe.lister()

    @app.put("/api/equipe/{pid}")
    async def ecrire_persona(pid: str, c: CorpsPersona):
        if c.harnais and c.harnais not in moteur.registre:
            raise Invalide(langues.t("serveur.api.harnais_inconnu", nom=c.harnais))
        return moteur.revues.equipe.ecrire(pid, c.model_dump())

    @app.delete("/api/equipe/{pid}", status_code=204)
    async def retirer_persona(pid: str):
        moteur.revues.equipe.retirer(pid)
        return Response(status_code=204)

    @app.get("/api/taches/{ident}/revues")
    async def revues(ident: str):
        vault.tache(ident)
        return moteur.revues.avis_de(ident)

    @app.post("/api/taches/{ident}/solliciter", status_code=202)
    async def solliciter(ident: str, c: CorpsSolliciter):
        moteur.revues.solliciter(ident, c.persona, c.question)
        return {"tache": ident, "persona": c.persona}

    @app.post("/api/taches/{ident}/valider")
    async def valider(ident: str, c: CorpsForcer | None = None):
        moteur.demi_verrou(ident, bool(c and c.forcer), seule=True)  # INV-VERROU-1
        moteur.revues.valider(ident)
        moteur.publier("arbre")
        return tache(ident)

    @app.post("/api/taches/{ident}/renvoyer")
    async def renvoyer(ident: str, c: CorpsTexte):
        moteur.demi_verrou(ident, c.forcer, seule=True)  # INV-VERROU-1
        moteur.revues.renvoyer(ident, c.texte)
        return tache(ident)

    @app.post("/api/taches/{ident}/liberer")
    async def liberer(ident: str):
        vault.liberer(ident)
        moteur.publier("arbre")
        return tache(ident)

    @app.get("/api/propositions")
    async def propositions():
        return moteur.propositions.liste

    @app.post("/api/propositions", status_code=201)
    async def proposer(c: api_arbre.CorpsProposition):
        return moteur.proposer(c.type, c.tache, c.valeur, c.de or "", c.motif or "", annexe={"taches": c.taches or []} if c.type == "rattacher" else None)

    @app.post("/api/propositions/{n}/accepter")
    async def accepter(n: int):
        p = moteur.propositions.get(n)
        if p["type"] == "operation" and p["etat"] == "en_attente":
            # INV-ARBRE-2 : le dossier du projet rejoint l'opération (plan, verrou, tout ou rien) ;
            # un refus (409) laisse la proposition en attente (INV-EXEC-5).
            moteur.propositions.reserver(n)  # C8 : le double clic ne rejoue pas le plan
            try:
                plan = await asyncio.to_thread(geste.planifier_operation, aligneur, p["tache"], p["valeur"])
                await routeur_arbre.appliquer(plan["jeton"])
                return moteur.conclure(p, True)
            finally:
                moteur.propositions.liberer(n)
        return moteur.trancher(n, True)

    @app.post("/api/propositions/{n}/refuser")
    async def refuser(n: int):
        return moteur.trancher(n, False)

    @app.post("/api/propositions/{n}/annuler")  # INV-PROP-1 : défaire un geste appliqué d'office
    async def annuler(n: int):
        return moteur.annuler(n)

    @app.get("/api/evenements")
    async def evenements(request: Request):
        q = moteur.abonner()

        async def flux():
            try:
                yield ": ouvert\n\n"
                while not await request.is_disconnected() and not api_appareils.revoque(request):  # INV-DISTANT-6
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=15)
                    except TimeoutError:
                        yield ": veille\n\n"
                        continue
                    # INV-DISTANT-6 : rien n'est émis après la révocation ; la boucle s'arrête au tour suivant
                    yield "" if api_appareils.revoque(request) else f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            finally:
                moteur.desabonner(q)

        return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # Lot 6 : notes du vault ; inclus avant le montage de `web/`, qui capte tout le reste.
    routeur_notes = api_notes.routes(config, vault, moteur.publier, moteur)
    app.state.index_notes = routeur_notes.index
    app.include_router(routeur_notes)
    routeur_arbre = api_arbre.routes(config, moteur, aligneur, routeur_notes.index)
    app.include_router(api_titre.routes(vault, moteur.publier, tache)); app.include_router(api_temps.routes(vault, moteur.publier, tache, lambda: etat_main.humain_par_id(moteur)))  # INV-RENOMMER-1, INV-MAIN-4
    app.include_router(api_rapprochement.routes(moteur))
    app.include_router(api_codespace.routes(vault, moteur, tache))
    app.include_router(api_feux.routes(api_feux.FeuxVerts(moteur)))  # INV-FEU-1
    app.include_router(api_simultanes.routes(config, moteur))
    app.include_router(api_economie.routes(config, moteur))  # INV-ECO-1
    app.include_router(api_compactage.routes(config, moteur))  # INV-COMPACT-1
    app.include_router(api_apprendre.routes(config, moteur, tache))  # INV-APPRENDRE-1
    app.include_router(api_decisions.routes(moteur))
    for rt in (api_lignes.routes(config, moteur, tache), api_livrables.routes(config, moteur), api_routines.routes(moteur.routines), api_chaines.routes(moteur), api_compagnon.routes(config, moteur)): app.include_router(rt)  # INV-ROUTINE-1, INV-CHAINE-1
    app.include_router(api_accueil.routes(config, moteur, vault))  # INV-ACCUEIL-1 : poste seulement
    app.include_router(api_installation.routes())  # INV-INSTALL-1 : poste seulement (garde INV-DISTANT-1)
    app.include_router(api_validation.routes(moteur))  # INV-VALID-2
    app.include_router(api_retour.routes(config, moteur, harnais_de))  # INV-RETOUR-1
    app.include_router(routeur_arbre)
    app.state.maj_auto = (routeur_maj := api_maj.routes(config, moteur, app.state.version)).auto  # INV-MAJ-3
    app.include_router(routeur_maj)
    app.include_router(api_poste.routes(moteur, vault))
    app.include_router(api_interface.routes(config, moteur.publier))
    app.include_router(api_etoile.routes(config))  # INV-ETOILE-1
    app.include_router(api_resultat.routes(moteur))  # INV-RESULTAT-1 : poste seulement
    app.include_router(api_pilotage.routes(moteur))  # INV-PILOTAGE-1
    app.include_router(api_execution.routes(moteur))  # INV-REGROUPE-1, INV-REGROUPE-2
    app.include_router(api_vigie.routes(moteur.vigie))  # INV-VIGIE-1
    app.include_router(api_travaux.routes(moteur))  # INV-TRAVAUX-1, INV-TRAVAUX-2
    app.include_router(api_executeurs.routes(config, moteur))  # INV-DISTANT-1
    app.include_router(api_appareils.routes(config, registre))  # INV-DISTANT-5
    app.include_router(api_telegram.routes(config, moteur, connecteur))
    app.include_router(api_manager.routes(connecteur))  # INV-MANAGER-1
    for m in (guide, modeles): app.include_router(m.routes())  # INV-GUIDE-1, INV-MODELES-1
    app.include_router(api_reflexes.routes_traces(vault, moteur.publier, tache))  # INV-TRACE-1
    for r in (api_executant.routes(moteur, tache), api_lots.routes(moteur), api_lecteur.routes(config, moteur), api_etiquettes.routes(moteur, tache), api_styles.routes(WEB)): app.include_router(r)  # INV-EXECUTANT-1, INV-REACTIVITE-1 (styles avant le montage des fichiers)
    if WEB.is_dir():
        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app
