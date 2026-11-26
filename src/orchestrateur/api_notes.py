"""Routes `/api/vault/*` (lot 6) : parcourir, lire, chercher, résoudre, écrire, créer ; mentions
non liées et graphe du second cerveau.

Rôle : traduire HTTP en appels à `notes.py` et `index_notes.py`, hors de la boucle d'événements.
Frontières : aucune logique de chemin ni d'écriture ici ; la garde INV-API-1 reste celle d'`api.py`.
Invariants portés : INV-NOTE-1 (tout chemin client passe par `notes.chemin_sur`),
INV-NOTE-2 (409 avec la version courante), INV-NOTE-3 (déplacement tout ou rien),
INV-VERROU-1 (note d'une tâche ou d'un conteneur occupé : 409 sauf `forcer`), INV-GRAPHE-1
(l'index est assuré avant de servir le graphe : une écriture le périme).
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import langues, notes, notes_chat
from .config import Config
from .graphe import PLAFOND, Graphe
from .index_notes import IndexNotes
from .vault import Conflit, Invalide, NonTrouve, Vault

TAILLE_MAX = 200 * 1024 * 1024
# INV-NOTE-1 : liste blanche ; jamais `.md`, `.html`, ni un exécutable servis.
TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
         "webp": "image/webp", "bmp": "image/bmp", "avif": "image/avif", "svg": "image/svg+xml",
         "pdf": "application/pdf", "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
         "m4a": "audio/mp4", "flac": "audio/flac", "mp4": "video/mp4", "webm": "video/webm",
         "mov": "video/quicktime", "txt": "text/plain; charset=utf-8",
         "csv": "text/csv; charset=utf-8"}


class CorpsNoteEcrire(BaseModel):
    chemin: str
    contenu: str
    mtime_ns: str
    forcer: bool = False  # INV-VERROU-1


class CorpsNoteCreer(BaseModel):
    dossier: str = ""
    nom: str
    contenu: str = ""
    creer_dossier: bool = False


class CorpsNoteIA(BaseModel):
    chemin: str
    action: str
    consigne: str = ""


class CorpsNoteDeplacer(BaseModel):
    chemin: str
    vers: str
    creer_dossier: bool = False
    forcer: bool = False  # INV-VERROU-1


def routes(config: Config, vault: Vault, publier, verrou) -> APIRouter:
    """`verrou` : le `Moteur` (occupation, demi-verrou, INV-VERROU-1)."""
    r = APIRouter(prefix="/api/vault")
    index = IndexNotes(vault.racine, config.notes.exclure, config.notes.ttl_s)
    motifs = config.notes.exclure
    graphe = Graphe(index, vault, config.vault.contexte)

    def sur(chemin: str, vide_ok: bool = False):
        return notes.chemin_sur(index.racine, chemin, motifs, vide_ok)

    def dossier(chemin: str) -> dict:
        index.assurer_sans_attendre()  # compteurs de l'index : jamais de balayage à la demande
        rel, d = sur(chemin, vide_ok=True)
        if not d.is_dir():
            raise NonTrouve(langues.t("serveur.api_notes.dossier_introuvable", chemin=chemin))
        compte = index.compter()
        segs = rel.split("/") if rel else []
        parents = [{"nom": index.racine.name, "chemin": ""}] if rel else []
        parents += [{"nom": s, "chemin": "/".join(segs[:i + 1])} for i, s in enumerate(segs[:-1])]
        dossiers, refs, fichiers = [], [], []
        for e in os.scandir(d):
            c = f"{rel}/{e.name}" if rel else e.name
            # INV-NOTE-1 : liens symboliques, jonctions et exclus invisibles.
            if e.is_symlink() or e.is_junction() or notes.exclu(c, motifs):
                continue
            if e.is_dir():
                dossiers.append({"nom": e.name, "chemin": c, "notes": compte.get(c, 0)})
            elif e.name.lower().endswith(".md"):
                if (ref := index.ref(c)) is None:
                    index.maj(c)
                    ref = index.ref(c)
                if ref:
                    refs.append(ref)
            elif e.is_file():
                fichiers.append({"nom": e.name, "chemin": c, "taille": e.stat().st_size})
        return {"chemin": rel, "parents": parents,
                "dossiers": sorted(dossiers, key=lambda x: x["nom"].casefold()),
                "notes": sorted(refs, key=lambda x: x["nom"].casefold()),
                "fichiers": sorted(fichiers, key=lambda x: x["nom"].casefold())}

    def lire(chemin: str) -> dict:
        index.assurer()
        rel, p = sur(chemin)
        notes.est_note(rel)
        return notes.note(index, vault, rel, p)

    def ecrire(c: CorpsNoteEcrire) -> dict:
        index.assurer()
        rel, p = sur(c.chemin)
        return notes.ecrire(index, vault, rel, p, c.contenu, c.mtime_ns)

    def creer(c: CorpsNoteCreer) -> dict:
        index.assurer()
        rel, d = sur(c.dossier, vide_ok=True)
        return notes.creer(index, vault, rel, d, c.nom, c.contenu, c.creer_dossier)

    def deplacer(c: CorpsNoteDeplacer) -> tuple[str, dict, int, bool]:
        index.assurer()
        rel, p = sur(c.chemin)
        try:
            vers, q = sur(c.vers)
        except NonTrouve as e:
            raise Conflit(langues.t("serveur.api_notes.destination_refusee", erreur=e)) from None
        n, nb, tache = notes.deplacer(index, vault, rel, p, vers, q, c.creer_dossier,
                                      config.vault.exclure,
                                      lambda i: verrou.occupation(i) is not None)
        return rel, n, nb, tache

    def chercher(q: str, limite: int, dans: str) -> list[dict]:
        index.assurer()
        rel = sur(dans, vide_ok=True)[0] if dans else ""
        return index.chercher(q, min(max(limite, 1), 100), rel)

    def resoudre_(lien: str, depuis: str) -> dict:
        index.assurer()
        source = sur(depuis)[0] if depuis else None
        brut = lien.strip().removeprefix("!").removeprefix("[[").removesuffix("]]")
        cible = brut.partition("|")[0].rstrip("\\").partition("#")[0]
        return {"chemin": index.resoudre(cible, source)}

    def fichier(chemin: str):
        rel, p = sur(chemin)
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel.rsplit("/", 1)[-1] else ""
        if ext not in TYPES:
            raise Invalide(langues.t("serveur.api_notes.type_non_servi", chemin=rel))
        if not p.is_file():
            raise NonTrouve(langues.t("serveur.api_notes.fichier_introuvable", chemin=rel))
        if p.stat().st_size > TAILLE_MAX:
            raise Invalide(langues.t("serveur.api_notes.fichier_volumineux"))
        # Un svg peut porter du script : téléchargé s'il est ouvert seul (l'<img> l'affiche).
        dispo = "attachment" if ext == "svg" else "inline"
        return FileResponse(p, media_type=TYPES[ext], filename=p.name,
                            content_disposition_type=dispo,
                            headers={"X-Content-Type-Options": "nosniff"})

    def cible(chemin: str) -> tuple[str, bool] | None:
        """Nœud que porte une note : (tâche, True) pour un fichier de tâche, (conteneur, False)
        pour le `contexte.md` d'un conteneur ; None sinon."""
        rel, p = sur(chemin)
        taches, conts = vault.index()
        if t := next((t for t in taches.values() if t.chemin == p), None):
            return t.id, True
        dossier, _, nom = rel.rpartition("/")
        return (dossier, False) if nom == config.vault.contexte and dossier in conts else None

    async def demi_verrou(chemin: str, forcer: bool, seule: bool) -> None:
        # INV-VERROU-1 : tâche seule à l'édition, sa descendance au déplacement ; un conteneur,
        # toujours sa descendance. Le verrou dur d'INV-ALIGN-2 reste dans `notes.deplacer`.
        if not forcer and (c := await asyncio.to_thread(cible, chemin)):
            verrou.demi_verrou(c[0], False, seule=seule and c[1])

    async def publier_note(n: dict) -> dict:
        # Une note écrite peut être une tâche ou la fiche `contexte.md` d'un projet neuf : l'index
        # des tâches est périmé aussitôt (constat du 14/11 : projet créé, « conteneur inconnu »).
        vault._index = None
        publier("note", chemin=n["chemin"])
        if n["chemin"].rsplit("/", 1)[-1] == config.vault.contexte or "/taches/" in n["chemin"]:
            publier("arbre")
        return n

    @r.get("/dossier")
    async def get_dossier(chemin: str = ""):
        return await asyncio.to_thread(dossier, chemin)

    @r.get("/note")
    async def get_note(chemin: str):
        return await asyncio.to_thread(lire, chemin)

    @r.put("/note")
    async def put_note(c: CorpsNoteEcrire):
        await demi_verrou(c.chemin, c.forcer, seule=True)
        try:
            n = await asyncio.to_thread(ecrire, c)
        except notes.ConflitNote as e:
            return JSONResponse({"detail": str(e), "courante": e.courante}, status_code=409)
        return await publier_note(n)

    @r.post("/note", status_code=201)
    async def post_note(c: CorpsNoteCreer):
        return await publier_note(await asyncio.to_thread(creer, c))

    @r.post("/note/deplacer")
    async def deplacer_note(c: CorpsNoteDeplacer):
        await demi_verrou(c.chemin, c.forcer, seule=False)
        ancien, n, nb, tache = await asyncio.to_thread(deplacer, c)
        publier("note", chemin=n["chemin"], ancien=ancien)
        if tache:
            publier("arbre")
        return {"note": n, "fichiers_reecrits": nb}

    @r.post("/note/ia")
    async def note_ia(c: CorpsNoteIA, request: Request):
        # INV-NOTECHAT-1 : proposition seulement ; l'écriture suit le geste de l'utilisateur.
        if request.headers.get("x-orch-tache"):  # geste humain : un agent n'appelle pas le modèle des notes
            raise Conflit(langues.t("serveur.notes_chat.refus_agent"))
        n = await asyncio.to_thread(lire, c.chemin)
        return await notes_chat.proposer(verrou, n["chemin"], n["contenu"], c.action, c.consigne)

    @r.get("/recherche")
    async def recherche(q: str = "", limite: int = 30, dossier: str = ""):
        return await asyncio.to_thread(chercher, q, limite, dossier)

    @r.get("/resoudre")
    async def resoudre(lien: str, depuis: str = ""):
        return await asyncio.to_thread(resoudre_, lien, depuis)

    @r.get("/fichier")
    async def get_fichier(chemin: str):
        return await asyncio.to_thread(fichier, chemin)

    def mentions_(chemin: str) -> list[dict]:
        index.assurer()
        rel, _ = sur(chemin)
        return index.mentions(rel)

    def graphe_(centre: str, profondeur: int, filtres: dict, limite: int) -> dict:
        index.assurer()
        if centre:
            return graphe.local(centre, profondeur, limite)
        return graphe.global_(limite=limite, **filtres)

    @r.get("/mentions")
    async def mentions(chemin: str):
        return await asyncio.to_thread(mentions_, chemin)

    @r.get("/graphe")
    async def get_graphe(centre: str = "", profondeur: int = 1, casquette: str = "",
                         projet: str = "", genre: str = "", type: str = "", tag: str = "",
                         jours: int = 0, limite: int = PLAFOND):
        f = {"casquette": casquette, "projet": projet, "genre": genre, "type_": type, "tag": tag,
             "jours": jours}
        return await asyncio.to_thread(graphe_, centre, profondeur, f, limite)

    @r.get("/graphe/facettes")
    async def get_facettes():
        return await asyncio.to_thread(lambda: (index.assurer(), graphe.facettes())[1])

    index.demarrer()
    r.index = index
    r.graphe = graphe  # accès des tests à l'index (mesure des relectures)
    return r
