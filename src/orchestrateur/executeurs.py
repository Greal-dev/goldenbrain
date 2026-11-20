"""Exécuteurs distants, côté chef : jetons, annonces, répartition des tours, tours relayés.

Rôle : un seul GoldenBrain « chef » (vault, file, interface, décisions) ; d'autres PC font tourner
`orch executeur`, qui se connecte au chef (sortant), s'annonce, reçoit des tours et renvoie leurs
événements. Ce module tient le registre des exécuteurs (jetons hachés, signe de vie, mémoire,
places, harnais), décide où part un tour (`placer`) et fournit l'adaptateur `HarnaisDistant` que
le moteur lance comme n'importe quel harnais : journal, session, fiche et conversation restent
ceux du chef.
Frontières : aucun HTTP (routes : `api_executeurs`), aucune écriture du vault ; le seul état
persisté est `<donnees>/etat/executeurs.json` (hors dépôt, hors vault).
Invariants portés : INV-DISTANT-1 (jeton haché, montré une fois, révocable), INV-DISTANT-2
(répartition, conversation qui ne change pas de PC, épinglage), INV-DISTANT-3 (vault par l'API
seulement : aucun chemin de vault dans un ordre hormis la consigne, préambule imposé),
INV-DISTANT-4 (perte et retour d'un exécuteur), INV-APPAIRAGE-1 (code d'appairage, `appairage.py`),
INV-MOTEUR-1 (harnais absent de l'exécuteur :
échec avant lancement, jamais de repli).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from . import appairage, depot, fiches, langues, pilotage, reprise
from .harnais import Evenement
from .vault import Invalide, NonTrouve

log = logging.getLogger(__name__)
NOM = re.compile(r"[A-Za-z0-9_-]{1,40}")
CHEF = "chef"  # épinglage sur le poste du chef (`executeur: chef`)
# INV-DISTANT-3 : en tête de chaque tour distant ; le vault n'existe pas sur l'exécuteur.
PREAMBULE = ("[GoldenBrain — tu travailles sur l'exécuteur « {nom} », un autre PC. Le vault n'y est "
             "pas : les chemins de vault cités plus bas ne s'ouvrent pas ici. Lis et écris les tâches "
             "uniquement par la commande orch (lire, dire, chercher, arbre, proposer, fiche…). Le code "
             "vient de GitHub : clone ou mets à jour le dépôt, travaille sur une branche, pousse-la.]\n\n")


A_REPARER = ("manquant", "a_connecter")  # états d'une étape qu'une commande du catalogue peut relancer


def _prerequis(brut: list) -> list[dict]:
    """Relevé annoncé par un exécuteur : champs connus seulement, tailles bornées (donnée distante)."""
    sortie = []
    for p in brut[:40]:
        if isinstance(p, dict):
            ligne = {k: str(p.get(k) or "")[:300] for k in ("id", "libelle", "etat", "genre", "commande", "instructions")}
            ligne["optionnel"] = bool(p.get("optionnel"))
            ligne["attend"] = [str(x)[:40] for x in (p.get("attend") or [])[:10]]
            sortie.append(ligne)
    return sortie


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


@dataclass
class Executeur:
    nom: str
    vu: float = 0.0               # time.monotonic() du dernier contact
    harnais: list[str] = field(default_factory=list)
    memoire: dict = field(default_factory=dict)   # {"libre": octets, "total": octets}
    places: int = 1
    prerequis: list = field(default_factory=list)  # état des étapes de l'assistant d'installation (INV-INSTALL-4)
    reparation: dict | None = None  # résultat de la dernière réparation demandée
    ecoute: int = 0               # relevés (long-poll) en cours : signe de vie continu
    ordres: deque = field(default_factory=deque)
    evt: asyncio.Event | None = None


@dataclass
class TourDistant:
    id: str
    tache: str
    executeur: str
    ordre: dict
    file: asyncio.Queue = field(default_factory=asyncio.Queue)
    pris: float = 0.0        # instant où l'exécuteur a relevé l'ordre (0 : pas encore)
    fini: bool = False
    session: str = ""
    recu: int = 0            # dernier numéro d'événement reçu (dédoublonnage des renvois)
    repris: bool = False     # INV-DISTANT-4 : une seule reprise après perte
    attente: bool = False    # exécuteur perdu : « en attente de l'exécuteur »


class Executeurs:
    INTERVALLE_S = 10       # cadence des annonces demandée à l'exécuteur
    ATTENTE_MAX_S = 25      # long-poll de `travail`
    GRACE_S = 60            # ordre relevé absent des annonces au-delà : perdu

    def __init__(self, moteur):
        self.m = moteur
        self.fichier = moteur.config.donnees / "etat" / "executeurs.json"
        etat = self._lire()
        self.jetons: dict[str, str] = dict(etat.get("jetons") or {})   # nom -> empreinte
        self.nes: dict[str, str] = dict(etat.get("nes") or {})         # tâche -> exécuteur
        self.connus: dict[str, Executeur] = {}
        self.tours: dict[str, TourDistant] = {}
        self.lieux: dict[str, str] = {}   # tâche -> exécuteur du tour qui s'y prépare ou y court
        self._origines: dict[str, str | None] = {}
        self.appairage = appairage.Appairage(self.creer_jeton, self._valider_nom)  # INV-APPAIRAGE-1

    # --- persistance ----------------------------------------------------------------------
    def _lire(self) -> dict:
        try:
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _sauver(self) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.fichier, json.dumps(
            {"jetons": self.jetons, "nes": self.nes}, ensure_ascii=False, indent=1))

    # --- jetons (INV-DISTANT-1) -----------------------------------------------------------
    @staticmethod
    def _valider_nom(nom: str) -> None:
        if not NOM.fullmatch(nom or "") or nom == CHEF:
            raise Invalide(langues.t("serveur.executeurs.nom_invalide"))

    def creer_jeton(self, nom: str) -> str:
        """Jeton neuf pour `nom` (remplace l'ancien) ; seule son empreinte est gardée."""
        self._valider_nom(nom)
        jeton = secrets.token_urlsafe(32)
        self.jetons[nom] = empreinte(jeton)
        self._sauver()
        return jeton

    def revoquer(self, nom: str) -> None:
        if self.jetons.pop(nom, None) is None:
            raise NonTrouve(langues.t("serveur.executeurs.inconnu", nom=nom))
        self._sauver()
        self.connus.pop(nom, None)
        self.m.publier("executeurs")

    def identifier(self, jeton: str | None) -> str | None:
        if not jeton:
            return None
        e = empreinte(jeton)
        trouve = None
        for nom, attendu in self.jetons.items():
            if hmac.compare_digest(e, attendu):  # comparaison à temps constant
                trouve = nom
        return trouve

    # --- état des exécuteurs --------------------------------------------------------------
    def _exe(self, nom: str) -> Executeur:
        if nom not in self.connus:
            self.connus[nom] = Executeur(nom, evt=asyncio.Event())
        return self.connus[nom]

    def connecte(self, nom: str) -> bool:
        e = self.connus.get(nom)
        return bool(e and (e.ecoute or e.vu and time.monotonic() - e.vu < self.m.config.executeurs.delai_perte_s))

    def occupation(self, nom: str) -> int:
        # `lieux` couvre le tour de sa préparation à sa fin (posé et retiré par le poste).
        return sum(1 for lieu in self.lieux.values() if lieu == nom)

    def annoncer(self, nom: str, corps: dict) -> dict:
        """Signe de vie : harnais disponibles, mémoire, places, tours encore tenus par l'exécuteur.
        Rend les tours à abandonner (inconnus du chef : il a redémarré)."""
        e = self._exe(nom)
        revenu = not self.connecte(nom)
        e.vu = time.monotonic()
        e.harnais = [str(h) for h in corps.get("harnais") or [] if isinstance(h, str)][:20]
        mem = corps.get("memoire") or {}
        e.memoire = {k: int(mem[k]) for k in ("libre", "total") if isinstance(mem.get(k), (int, float))}
        e.places = max(1, min(int(corps.get("places") or 1), 32))
        if isinstance(corps.get("prerequis"), list):
            e.prerequis = _prerequis(corps["prerequis"])
        if isinstance(corps.get("reparation"), dict):
            e.reparation = {k: (str(v)[:600] if v is not None else None) for k, v in corps["reparation"].items()
                            if k in ("etape", "etat", "code", "message")}
            self.m.publier("executeurs")
        tenus = {str(x) for x in corps.get("tours") or []}
        self._perdus(nom, tenus, bool(corps.get("depart")))
        for t in self.tours.values():
            if t.executeur == nom:
                t.attente = False
        if revenu:
            self.m.publier("executeurs")
        return {"intervalle": self.INTERVALLE_S,
                "abandonner": sorted(i for i in tenus if i not in self.tours or self.tours[i].fini)}

    def reparer(self, nom: str, etape: str, accord: str) -> None:
        """INV-INSTALL-4 : le chef relaie à l'exécuteur l'accord humain pour UNE étape non faite, qui doit
        être la commande exacte affichée ; l'exécuteur la confronte à son propre catalogue."""
        e = self.connus.get(nom)
        if not self.connecte(nom):
            raise Invalide(langues.t("serveur.executeurs.pas_connecte", nom=nom))
        ligne = next((p for p in e.prerequis if p["id"] == etape), None)
        if not ligne or ligne["etat"] not in A_REPARER or not ligne["commande"]:
            raise Invalide(langues.t("serveur.executeurs.rien_a_reparer"))
        if accord != ligne["commande"]:
            raise Invalide(langues.t("serveur.executeurs.accord_commande"))
        e.reparation = None
        self._envoyer(nom, {"type": "reparer", "etape": etape, "accord": accord})
        self.m.publier("executeurs")

    def _perdus(self, nom: str, tenus: set[str], depart: bool) -> None:
        # INV-DISTANT-4 : un ordre relevé que l'exécuteur ne tient plus est perdu (il a redémarré,
        # ou la réponse du relevé s'est perdue en route) ; délai de grâce pour l'annonce croisée.
        for t in list(self.tours.values()):
            if t.executeur != nom or t.fini or not t.pris or t.id in tenus:
                continue
            if not depart and time.monotonic() - t.pris < self.GRACE_S:
                continue
            if not t.repris:
                t.repris, t.pris = True, 0.0
                ordre = dict(t.ordre)
                if t.session:
                    ordre.update(session=t.session, deriver=False, message=PREAMBULE.format(nom=nom)
                                 + reprise.MESSAGE_REPRISE.format(motif="redémarrage de l'exécuteur"))
                self._envoyer(nom, ordre)
                log.warning("tour %s de %s repris après redémarrage de l'exécuteur %s", t.id, t.tache, nom)
            else:
                self._clore(t, Evenement("erreur", texte=f"tour perdu deux fois par l'exécuteur {nom}"))

    def _envoyer(self, nom: str, ordre: dict) -> None:
        e = self._exe(nom)
        e.ordres.append(ordre)
        e.evt.set()

    async def travail(self, nom: str, attente: float | None = None) -> list[dict]:
        """Long-poll : ordres en attente pour `nom` (vide après `attente` secondes)."""
        e = self._exe(nom)
        e.vu = time.monotonic()
        if not e.ordres:
            e.evt.clear()
            e.ecoute += 1
            try:
                await asyncio.wait_for(e.evt.wait(), min(attente or self.ATTENTE_MAX_S, self.ATTENTE_MAX_S))
            except TimeoutError:
                pass
            finally:
                e.ecoute -= 1
                e.vu = time.monotonic()
        sortie = []
        while e.ordres:
            ordre = e.ordres.popleft()
            if ordre["type"] == "tour":
                if not (t := self.tours.get(ordre["tour"])) or t.fini:
                    continue  # arrêté avant d'être relevé
                t.pris = time.monotonic()
            sortie.append(ordre)
        e.vu = time.monotonic()
        return sortie

    def recevoir(self, nom: str, ident_tour: str, evenements: list, fini: bool) -> bool:
        """Événements d'un tour (numérotés `n`, renvoyés tels quels après une coupure). Faux : tour
        inconnu ou d'un autre exécuteur (l'exécuteur l'abandonne)."""
        t = self.tours.get(ident_tour)
        if not t or t.executeur != nom:
            return False
        self._exe(nom).vu = time.monotonic()
        if t.fini:
            return True
        for brut in evenements:
            if not isinstance(brut, dict) or int(brut.get("n") or 0) <= t.recu:
                continue  # INV-DISTANT-4 : un renvoi après coupure n'est pas rejoué
            t.recu = int(brut["n"])
            ev = Evenement(str(brut.get("type") or ""), session=str(brut.get("session") or ""),
                           texte=str(brut.get("texte") or ""),
                           brut=brut.get("brut") if isinstance(brut.get("brut"), dict) else None,
                           mesure=brut.get("mesure") if isinstance(brut.get("mesure"), dict) else None)
            if ev.session:
                t.session = ev.session
            t.file.put_nowait(ev)
        if fini:
            self._clore(t)
        return True

    def _clore(self, t: TourDistant, ev: Evenement | None = None) -> None:
        if t.fini:
            return
        t.fini = True
        if ev:
            t.file.put_nowait(ev)
        t.file.put_nowait(None)

    def veiller(self) -> None:
        """Marque « en attente de l'exécuteur » les tours d'un exécuteur perdu (jamais tués)."""
        change = False
        for t in self.tours.values():
            perdu = not t.fini and not self.connecte(t.executeur)
            change |= perdu != t.attente
            t.attente = perdu
        if change:
            self.m.publier("executeurs")

    # --- répartition (INV-DISTANT-2) ------------------------------------------------------
    def origine(self, ident: str) -> str | None:
        """URL `origin` du dépôt de la tâche ; None sans dépôt git (le tour reste au chef)."""
        dossier, _ = depot.dossier_de_travail(self.m.vault, ident)
        if not dossier:
            return None
        if dossier not in self._origines:
            try:
                r = subprocess.run(["git", "-C", dossier, "remote", "get-url", "origin"],
                                   capture_output=True, text=True, encoding="utf-8", timeout=10)
                self._origines[dossier] = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
            except (OSError, subprocess.SubprocessError):
                self._origines[dossier] = None
        return self._origines[dossier]

    def placer(self, ident: str, envoi) -> str:
        """Exécuteur du tour, ou "" pour le poste du chef. Première règle qui s'applique :
        rôle ou codespace → chef ; conversation née sur un exécuteur → lui ; conversation
        née au chef → chef ; épinglage `executeur:` (nom ou `chef`) ; `vault: intensif` ou sans dépôt git →
        chef ; place libre au chef → chef ; sinon l'exécuteur connecté qui a le plus de place."""
        if envoi.role or envoi.pour:
            return ""
        t = self.m.vault.tache(ident)
        if str(t.fm.get("ou") or "") == "codespace":
            return ""
        if ne := self.nes.get(ident):
            if t.fm.get("session"):
                return ne if ne in self.jetons else ""
            self.nes.pop(ident)  # conversation remise à zéro : elle renaîtra où il y a place
            self._sauver()
        if t.fm.get("session") or ident in self.m.a_deriver:
            return ""  # née au chef, elle y reste
        if epingle := str(t.fm.get("executeur") or "").strip():
            return "" if epingle == CHEF or epingle not in self.jetons else epingle
        if not self.connus or str(t.fm.get("vault") or "") == "intensif" or not self.origine(ident):
            return ""
        sem = self.m._sem
        if sem.peut_demarrer() and not sem.attente:
            return ""
        libres = [(e.places - self.occupation(e.nom), e.memoire.get("libre", 0), e.nom)
                  for e in self.connus.values() if self.connecte(e.nom) and e.nom in self.jetons]
        libres = [x for x in libres if x[0] > 0]
        return max(libres)[2] if libres else ""

    async def attendre_place(self, nom: str) -> None:
        """Attend que l'exécuteur soit connecté et ait une place (sans créneau du chef)."""
        while not (self.connecte(nom) and self.occupation(nom) < self._exe(nom).places):
            if nom not in self.jetons:
                raise Invalide(langues.t("serveur.executeurs.revoque", nom=nom))
            await asyncio.sleep(1)

    def envelopper(self, ident: str, nom_harnais: str, instance):
        """Adaptateur du tour : distant si la tâche a été placée sur un exécuteur."""
        if not (lieu := self.lieux.get(ident)):
            return instance
        e = self._exe(lieu)
        if e.harnais and nom_harnais not in e.harnais:
            # INV-MOTEUR-1 : échec avant lancement, jamais de repli sur un autre harnais.
            raise Invalide(langues.t("serveur.executeurs.assistant_absent", harnais=nom_harnais, nom=lieu))
        return HarnaisDistant(self, ident, lieu, nom_harnais, instance)

    def releve(self, ident: str, instance):
        """Conversation née sur un exécuteur : son transcript n'est pas sur ce disque, les
        journaux du chef en tiennent lieu."""
        return _SansTranscript(instance) if ident in self.nes else instance

    # --- vue ------------------------------------------------------------------------------
    def public(self) -> list[dict]:
        self.veiller()
        sortie = []
        for nom in sorted(set(self.jetons) | set(self.connus)):
            e = self.connus.get(nom)
            tours = [{"tache": t.tache, "titre": self._titre(t.tache), "attente": t.attente}
                     for t in self.tours.values() if t.executeur == nom and not t.fini]
            sortie.append({"nom": nom, "connecte": self.connecte(nom), "revoque": nom not in self.jetons,
                           "vu_il_y_a_s": round(time.monotonic() - e.vu) if e and e.vu else None,
                           "harnais": e.harnais if e else [], "memoire": e.memoire if e else {},
                           "places": e.places if e else 0, "tours": tours,
                           "prerequis": e.prerequis if e else [], "reparation": e.reparation if e else None,
                           "attente": [i for i, lieu in self.lieux.items() if lieu == nom
                                       and not any(t.tache == i for t in self.tours.values() if not t.fini)]})
        return sortie

    def _titre(self, ident: str) -> str:
        try:
            return self.m.vault.tache(ident).titre
        except NonTrouve:
            return ident


class _SansTranscript:
    def __init__(self, instance):
        self._i = instance

    def __getattr__(self, nom):
        return getattr(self._i, nom)

    def transcript(self, session: str, limite: int):
        raise NotImplementedError  # relu dans les journaux du chef


class HarnaisDistant:
    """Adaptateur d'un tour relayé : même contrat que les harnais locaux (`harnais.Harnais`)."""

    def __init__(self, registre: Executeurs, tache: str, executeur: str, nom: str, interne):
        self.r, self.tache, self.executeur, self.nom, self.interne = registre, tache, executeur, nom, interne
        self.consigne_native = getattr(interne, "consigne_native", False)
        self.sait_deriver = getattr(interne, "sait_deriver", False)
        self.compactage_natif = getattr(interne, "compactage_natif", False)
        self.ordre_compactage = getattr(interne, "ordre_compactage", "")
        self.compactage = getattr(interne, "compactage", None)
        self.tour: TourDistant | None = None

    def transcript(self, session: str, limite: int):
        raise NotImplementedError

    def commande_terminal(self, session: str) -> str:
        raise Invalide(langues.t("serveur.executeurs.conversation_tenue", nom=self.executeur))

    async def lancer(self, message: str, *, session, deriver, consigne, env, modele=""):
        ordre = {"type": "tour", "tour": uuid.uuid4().hex, "tache": self.tache, "harnais": self.nom,
                 "message": PREAMBULE.format(nom=self.executeur) + message, "session": session,
                 "deriver": deriver, "consigne": consigne, "modele": modele,
                 "compactage": list(self.compactage) if self.compactage else None,
                 # INV-DISTANT-3 : ni ORCH_URL ni chemin du chef ; l'exécuteur pose les siens.
                 "env": {k: v for k, v in env.items() if k in ("ORCH_TACHE", "ORCH_SAUTS")},
                 "depot": self.r.origine(self.tache), "orch": pilotage._orch()}
        self.tour = t = TourDistant(ordre["tour"], self.tache, self.executeur, ordre)
        self.r.tours[t.id] = t
        if not session:
            self.r.nes[self.tache] = self.executeur  # INV-DISTANT-2 : la conversation naît ici
            self.r._sauver()
        self.r._envoyer(self.executeur, ordre)
        self.r.m.publier("executeurs")
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(t.file.get(), 5)
                except TimeoutError:
                    self.r.veiller()  # INV-DISTANT-4 : rien n'est tué pendant l'attente
                    continue
                if ev is None:
                    return
                yield ev
        finally:
            self.r.tours.pop(t.id, None)
            self.r.m.publier("executeurs")

    async def arreter(self) -> None:
        t = self.tour
        if t and not t.fini:
            if t.pris:
                self.r._envoyer(self.executeur, {"type": "arret", "tour": t.id})
            self.r._clore(t)
