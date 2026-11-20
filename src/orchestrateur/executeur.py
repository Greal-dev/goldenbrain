"""`orch executeur` : ce PC exécute les tours que lui confie un GoldenBrain chef.

Rôle : se connecter au chef (sortant seulement : rien n'écoute ici), s'annoncer (harnais
disponibles, mémoire libre, places, tours tenus) à intervalle régulier, recevoir les ordres par
long-poll, préparer le dépôt (clone ou mise à jour depuis GitHub), lancer le harnais localement
et renvoyer ses événements au fil de l'eau, numérotés, jusqu'à accusé de réception.
Frontières : n'importe ni le moteur, ni le vault, ni le catalogue ; aucun fichier du vault n'est
lu ni écrit ici ; aucune écoute réseau.
Invariants portés : INV-DISTANT-1 (jeton porté par chaque appel, agents compris par
`ORCH_JETON`), INV-DISTANT-3 (vault par l'API du chef seulement : `ORCH_URL` désigne le chef),
INV-DISTANT-4 (renvoi des événements après coupure ; tour abandonné quand le chef ne le connaît
plus), INV-APPAIRAGE-1 (le jeton reçu en échange d'un code n'est jamais affiché ; il vit dans un
fichier du dossier personnel, lisible du seul utilisateur), INV-INSTALL-4 (état des prérequis annoncé ;
une réparation ne lance que l'étape du catalogue local dont la commande est l'accord reçu).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import poste_ram
from .harnais import HARNAIS, Evenement
from .harnais.processus import resoudre

log = logging.getLogger(__name__)
RACINE = Path(__file__).resolve().parents[2]
URL_DEPOT = re.compile(r"(https://|git@)[A-Za-z0-9._@:/~+-]+")
NOM_DEPOT = re.compile(r"[A-Za-z0-9._-]{1,100}")
LIAISON = Path.home() / ".goldenbrain-executeur.json"   # {serveur, jeton} gardés après appairage


def orch_local() -> str:
    return f'"{Path(sys.executable).as_posix()}" "{(RACINE / "orch.py").as_posix()}"'


def harnais_disponibles() -> list[str]:
    sortie = []
    for nom in HARNAIS:
        try:
            resoudre(nom)  # commande par défaut de chaque adaptateur : son nom
            sortie.append(nom)
        except FileNotFoundError:
            pass
    return sortie


def http_urllib(serveur: str, jeton: str):
    async def http(methode: str, chemin: str, corps: dict | None = None, delai: float = 40):
        def appel():
            req = urllib.request.Request(
                serveur.rstrip("/") + chemin, method=methode,
                data=json.dumps(corps).encode("utf-8") if corps is not None else None,
                headers={"Content-Type": "application/json", "X-Orchestrateur": "1",
                         "X-Orch-Jeton": jeton})
            try:
                with urllib.request.urlopen(req, timeout=delai) as r:
                    return r.status, json.loads(r.read().decode("utf-8") or "null")
            except urllib.error.HTTPError as e:
                return e.code, None
        return await asyncio.to_thread(appel)
    return http


class JetonRefuse(Exception):
    pass


class AppairageRefuse(Exception):
    pass


def appel_urllib(url: str, corps: dict) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, method="POST", data=json.dumps(corps).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Orchestrateur": "1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "null")
        except ValueError:
            return e.code, None


def lier(serveur: str, code: str, fichier: Path | None = None, appel=appel_urllib) -> str:
    """Échange le code d'appairage contre le jeton, le range dans `fichier` ; rend le nom du PC."""
    fichier = fichier or LIAISON
    try:
        etat, corps = appel(serveur.rstrip("/") + "/api/executeurs/appairage/echange", {"code": code})
    except OSError as e:
        raise AppairageRefuse(f"chef injoignable : {e}") from e
    if etat != 200 or not corps or not corps.get("jeton"):
        raise AppairageRefuse((corps or {}).get("detail") or f"refus du chef ({etat})")
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps({"serveur": serveur.rstrip("/"), "jeton": corps["jeton"]}), encoding="utf-8")
    try:
        os.chmod(fichier, 0o600)  # sans effet fort sous Windows : le dossier personnel y suffit
    except OSError:
        pass
    return corps["nom"]


def liaison(fichier: Path | None = None) -> tuple[str, str]:
    """(serveur, jeton) gardés par un appairage précédent, ou deux chaînes vides."""
    try:
        d = json.loads((fichier or LIAISON).read_text(encoding="utf-8"))
        return str(d.get("serveur") or ""), str(d.get("jeton") or "")
    except (OSError, ValueError):
        return "", ""


class TourLocal:
    def __init__(self, ordre: dict):
        self.ordre, self.id = ordre, ordre["tour"]
        self.attente: list[dict] = []   # événements non encore acquittés par le chef
        self.n = 0
        self.fini = False
        self.abandonne = False
        self.signal = asyncio.Event()
        self.harnais = None


class Executeur:
    def __init__(self, serveur: str, jeton: str, depots: Path, places: int = 1, http=None,
                 harnais: dict | None = None, disponibles: list[str] | None = None, git=None,
                 assistant=None):
        self.serveur, self.jeton, self.depots, self.places = serveur.rstrip("/"), jeton, depots, places
        self.http = http or http_urllib(serveur, jeton)
        self.registre = harnais or HARNAIS
        self.disponibles = disponibles if disponibles is not None else harnais_disponibles()
        self.git = git or self._git
        self.tours: dict[str, TourLocal] = {}
        self.taches: set[asyncio.Task] = set()
        self.intervalle = 10
        self.depart = True
        self.assistant = assistant       # `installation.Assistant` ; None : pas d'état des prérequis
        self.prerequis: list[dict] = []
        self.plan_a = 0.0
        self.reparation: dict | None = None   # résultat de la dernière réparation, rendu au chef

    # --- annonce et ordres -----------------------------------------------------------------
    async def diagnostiquer(self, force: bool = False) -> None:
        """Relevé des prérequis de ce PC (sous-processus : hors de la boucle), au plus une fois par minute."""
        if not self.assistant or not (force or time.monotonic() - self.plan_a > 60):
            return
        self.plan_a = time.monotonic()
        plan = await asyncio.to_thread(self.assistant.plan)
        cles = ("id", "libelle", "etat", "genre", "optionnel", "commande", "instructions", "attend")
        self.prerequis = [{k: l[k] for k in cles} for l in plan]

    async def reparer(self, ordre: dict) -> None:
        """INV-INSTALL-4 : relance UNE étape du catalogue local ; l'accord reçu du chef doit être sa commande exacte."""
        etape = str(ordre.get("etape") or "")
        try:
            r = await asyncio.to_thread(self.assistant.executer, etape, str(ordre.get("accord") or ""))
            self.reparation = {"etape": etape, "etat": r.etat, "code": r.code, "message": r.repli}
        except (KeyError, ValueError) as err:   # étape inconnue, bloquée, ou accord ≠ commande
            self.reparation = {"etape": etape, "etat": "refuse", "code": None, "message": str(err)}
        await self.diagnostiquer(force=True)
        await self.annoncer()

    async def annoncer(self) -> None:
        m = poste_ram.mesurer()
        await self.diagnostiquer()
        corps = {
            "harnais": self.disponibles, "places": self.places, "depart": self.depart,
            "memoire": {"libre": m.libre, "total": m.total} if m else {},
            "tours": [i for i, t in self.tours.items() if not t.fini]}
        if self.prerequis:
            corps["prerequis"] = self.prerequis
        if self.reparation:
            corps["reparation"] = self.reparation
        code, r = await self.http("POST", "/api/executeurs/annonce", corps)
        if code == 401:
            raise JetonRefuse("jeton refusé par le chef")
        if code == 200 and r:
            if corps.get("reparation") is self.reparation:
                self.reparation = None   # rendu une fois au chef
            self.depart = False
            self.intervalle = r.get("intervalle") or self.intervalle
            for i in r.get("abandonner") or []:
                await self.abandonner(i)

    async def relever(self, attente: float = 25) -> None:
        code, r = await self.http("GET", f"/api/executeurs/travail?attente={attente}", None, attente + 15)
        if code == 401:
            raise JetonRefuse("jeton refusé par le chef")
        if code != 200 or not r:
            raise ConnectionError(f"travail : réponse {code}")
        for ordre in r.get("ordres") or []:
            if ordre.get("type") == "tour" and ordre.get("tour") not in self.tours:
                t = self.tours[ordre["tour"]] = TourLocal(ordre)
                self._tache(self.executer(t))
            elif ordre.get("type") == "reparer" and self.assistant:
                self._tache(self.reparer(ordre))
            elif ordre.get("type") == "arret":
                await self.abandonner(ordre.get("tour", ""))

    async def abandonner(self, ident: str) -> None:
        if (t := self.tours.get(ident)) and not t.fini:
            t.abandonne = True
            if t.harnais:
                await t.harnais.arreter()

    def _tache(self, coro) -> None:
        tache = asyncio.ensure_future(coro)
        self.taches.add(tache)
        tache.add_done_callback(self.taches.discard)

    # --- un tour ---------------------------------------------------------------------------
    def _git(self, *args: str) -> None:
        # Liste d'arguments, jamais de shell ; `--` sépare les options de l'URL.
        subprocess.run(["git", *args], check=True, capture_output=True, timeout=600)

    def preparer(self, url: str | None) -> Path:
        """Dossier de travail : clone du dépôt de la tâche, mis à jour (branches gb/… comprises)."""
        self.depots.mkdir(parents=True, exist_ok=True)
        if not url:
            return self.depots
        nom = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1].removesuffix(".git")
        if not URL_DEPOT.fullmatch(url) or not NOM_DEPOT.fullmatch(nom) or nom in (".", ".."):
            raise ValueError(f"dépôt refusé : {url!r}")
        dossier = self.depots / nom
        if (dossier / ".git").exists():
            self.git("-C", str(dossier), "fetch", "--all", "--prune")
        else:
            self.git("clone", "--", url, str(dossier))
        return dossier

    def _noter(self, t: TourLocal, ev) -> None:
        t.n += 1
        t.attente.append({"n": t.n, "type": ev.type, "session": ev.session, "texte": ev.texte,
                          "brut": ev.brut, "mesure": ev.mesure})
        t.signal.set()

    async def executer(self, t: TourLocal) -> None:
        envoi = asyncio.ensure_future(self.expedier(t))
        o = t.ordre
        try:
            dossier = await asyncio.to_thread(self.preparer, o.get("depot"))
            h = t.harnais = self.registre[o["harnais"]]({"dossier": str(dossier)})
            if o.get("compactage"):
                h.compactage = tuple(o["compactage"])
            orch = o.get("orch") or ""
            remplacer = (lambda s: s.replace(orch, orch_local())) if orch else (lambda s: s)
            # INV-DISTANT-3 : les agents d'ici parlent au chef par son API, jeton à l'appui.
            env = {**(o.get("env") or {}), "ORCH_URL": self.serveur, "ORCH_JETON": self.jeton}
            async for ev in h.lancer(remplacer(o.get("message") or ""), session=o.get("session"),
                                     deriver=bool(o.get("deriver")),
                                     consigne=remplacer(o.get("consigne") or ""), env=env,
                                     modele=o.get("modele") or ""):
                self._noter(t, ev)
                if t.abandonne:
                    break
        except Exception as e:  # le chef reçoit l'échec en clair, jamais de mort silencieuse
            log.exception("tour %s", t.id)
            self._noter(t, Evenement("erreur", texte=f"exécuteur : {e}"))
        finally:
            t.fini = True
            t.signal.set()
            await envoi
            self.tours.pop(t.id, None)

    async def expedier(self, t: TourLocal) -> None:
        """Renvoie les événements dans l'ordre jusqu'à accusé ; après une coupure, renvoie le
        même lot (le chef écarte les numéros déjà reçus, INV-DISTANT-4)."""
        while True:
            await t.signal.wait()
            t.signal.clear()
            while t.attente or t.fini:
                lot, fini = t.attente[:200], t.fini and len(t.attente) <= 200
                try:
                    code, _ = await self.http("POST", "/api/executeurs/evenements",
                                              {"tour": t.id, "evenements": lot, "fini": fini})
                except OSError:
                    code = 0
                if code == 410:  # le chef ne connaît plus ce tour : l'abandonner
                    await self.abandonner(t.id)
                    return
                if code != 200:
                    await asyncio.sleep(2)
                    continue
                del t.attente[:len(lot)]
                if fini:
                    return

    # --- boucles ---------------------------------------------------------------------------
    async def tourner(self) -> None:
        async def annonces():
            while True:
                try:
                    await self.annoncer()
                except OSError as e:
                    log.warning("chef injoignable : %s", e)
                await asyncio.sleep(self.intervalle)
        self._tache(annonces())
        while True:
            try:
                await self.relever()
            except (OSError, ConnectionError) as e:
                log.warning("relevé impossible : %s", e)
                await asyncio.sleep(5)


def main(serveur: str, jeton: str, depots: str | None, places: int, code: str = "") -> int:
    if code:  # INV-APPAIRAGE-1 : le code est échangé contre le jeton, qui n'est jamais affiché
        if not serveur:
            print("--serveur requis avec --code", file=sys.stderr)
            return 2
        try:
            print(f"appairé comme « {lier(serveur, code)} » : jeton gardé dans {LIAISON}")
        except AppairageRefuse as err:
            print(f"appairage refusé : {err}", file=sys.stderr)
            return 1
    if not jeton:
        serveur_garde, jeton = liaison()
        serveur = serveur or serveur_garde
        if serveur_garde and serveur.rstrip("/") != serveur_garde:
            jeton = ""  # le jeton gardé vaut pour un autre chef
    if not (serveur and jeton):
        print("jeton manquant : --code (appairage), --jeton ou ORCH_JETON_EXECUTEUR", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    from .installation import Assistant   # import tardif : installation.py importe ce module
    e = Executeur(serveur, jeton, Path(depots) if depots else Path.home() / "goldenbrain-depots",
                  max(1, places), assistant=Assistant())
    print(f"exécuteur relié à {serveur} ; harnais : {', '.join(e.disponibles) or 'aucun'}")
    try:
        asyncio.run(e.tourner())
    except KeyboardInterrupt:
        return 0
    except JetonRefuse as err:
        print(str(err), file=sys.stderr)
        return 1
    return 0
