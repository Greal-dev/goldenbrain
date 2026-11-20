"""Agents de Claude Code : inventaire, regroupement des doublons, rattachement aux tâches.

Rôle : lire (lecture seule) le dossier de travaux de Claude Code (un sous-dossier par agent, avec un
`state.json`), regrouper les doublons (même nom, à la casse et aux marques de dérivation près, et même
dossier : le plus récent est le titulaire, les autres l'historique), proposer pour chaque groupe un
rattachement — tâche déjà liée à une de ses sessions, tâche ouverte correspondante (titre, dossier),
création d'une tâche, ou « ignorer » —, puis appliquer le choix de l'utilisateur (lot de la page « Décisions »).
Frontières : n'écrit jamais dans le dossier de Claude Code ; n'écrit dans le vault que par les
fonctions du moteur (`creer`) ou `vault.modifier` sur le geste humain ; ne lance aucun tour. L'état propre
(dernier relevé, sessions ignorées) vit dans `<données>/etat/agents_cc.json`.
Invariants portés : INV-AGENTSCC-1 (rien n'est créé ni rattaché sans geste ; la reprise d'une tâche
rattachée est la session titulaire du groupe ; une tâche qui a déjà une autre conversation n'est jamais
proposée).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import depot, fiches, langues
from .vault import ErreurOrch, Invalide, NonTrouve

log = logging.getLogger(__name__)
SEUIL_TITRE = 0.6       # similarité de titre qui suffit à proposer un rattachement
SEUIL_CANDIDAT = 0.4    # similarité minimale d'un candidat offert au choix
BONUS_DOSSIER = 0.2     # la tâche vit dans le projet que le dossier de l'agent désigne
PERIODES = {"horaire": dt.timedelta(hours=1), "quotidien": dt.timedelta(days=1)}
ACTIONS = ("rattacher", "creer", "ignorer")
LONGUEUR_DETAIL = 600


@dataclass
class Agent:
    job: str
    nom: str
    etat: str
    dossier: str      # dossier d'origine (ce qui range l'agent dans un projet)
    cwd: str          # dossier de la session (celui d'où `claude --resume` la retrouve)
    cree: str
    maj: str
    session: str      # session à reprendre
    sessions: tuple[str, ...]
    detail: str


@dataclass
class Groupe:
    cle: str
    titulaire: Agent
    historique: list[Agent] = field(default_factory=list)

    @property
    def ident(self) -> str:
        return hashlib.sha1(self.cle.encode("utf-8")).hexdigest()[:12]

    @property
    def sessions(self) -> set[str]:
        return {s for a in (self.titulaire, *self.historique) for s in a.sessions}


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def norme(texte: str) -> str:
    """Nom comparable : casse, accents, ponctuation, marque de dérivation « ⑂ » et suffixe « (2) » ignorés."""
    t = re.sub(r"\(\d+\)\s*$", "", str(texte or "").strip())
    return " ".join(re.sub(r"[\W_]+", " ", _sans_accents(t).casefold()).split())


def _chemin(p: str) -> str:
    return str(p or "").strip().strip('"').replace("\\", "/").rstrip("/").casefold()


def _dans(d: str, base: str) -> bool:
    return bool(base) and (d == base or d.startswith(base + "/"))


def _court(texte, n: int = LONGUEUR_DETAIL) -> str:
    t = " ".join(str(texte or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def lire_jobs(dossier: Path) -> list[Agent]:
    """Un agent par sous-dossier à `state.json` lisible ; un état illisible ou sans session est ignoré."""
    agents = []
    try:
        entrees = sorted(p for p in dossier.iterdir() if p.is_dir())
    except OSError:
        return []
    for p in entrees:
        try:
            d = json.loads((p / "state.json").read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        session = str(d.get("resumeSessionId") or d.get("sessionId") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session):
            continue
        cwd = str(d.get("cwd") or "")
        sessions = tuple(dict.fromkeys(s for s in (session, str(d.get("sessionId") or ""),
                                                   str(d.get("forkParentSessionId") or "")) if s))
        agents.append(Agent(
            job=p.name, nom=_court(d.get("name") or d.get("intent") or p.name, 120),
            etat=str(d.get("state") or ""), dossier=str(d.get("originCwd") or cwd), cwd=cwd,
            cree=str(d.get("createdAt") or ""), maj=str(d.get("updatedAt") or d.get("createdAt") or ""),
            session=session, sessions=sessions,
            detail=_court(d.get("detail") or (d.get("output") or {}).get("result"))))
    return agents


def regrouper(agents: list[Agent]) -> list[Groupe]:
    """Même nom normalisé et même dossier : un groupe, le plus récent titulaire (INV-AGENTSCC-1)."""
    par_cle: dict[str, list[Agent]] = {}
    for a in agents:
        par_cle.setdefault(f"{norme(a.nom)}|{_chemin(a.dossier)}", []).append(a)
    groupes = []
    for cle, liste in par_cle.items():
        liste.sort(key=lambda a: (a.maj, a.job), reverse=True)
        groupes.append(Groupe(cle, liste[0], liste[1:]))
    groupes.sort(key=lambda g: g.titulaire.maj, reverse=True)
    return groupes


def conteneur_de(vault, dossier: str) -> str | None:
    """Conteneur du projet dont le dépôt contient `dossier` (clé `depot:` du projet, sinon table des
    projets externes) ; le dépôt le plus précis l'emporte ; None si aucun."""
    d, meilleur = _chemin(dossier), (0, None)
    conteneurs = vault.index()[1]
    for cid in conteneurs:
        try:
            dep = str(vault._lire_meta(vault.racine / cid / vault.cfg.contexte)[0].get("depot") or "")
        except OSError:
            continue
        if _dans(d, _chemin(dep)) and len(dep) > meilleur[0]:
            meilleur = (len(dep), cid)
    for chemin, projet in depot._table(vault):
        if _dans(d, _chemin(chemin)) and len(chemin) > meilleur[0]:
            cid = next((c for c in conteneurs if c.rsplit("/", 1)[-1].casefold() == projet.casefold()), None)
            if cid:
                meilleur = (len(chemin), cid)
    return meilleur[1]


def similitude(nom: str, titre: str) -> float:
    a, b = norme(nom), norme(titre)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ma, mb = {m for m in a.split() if len(m) >= 3}, {m for m in b.split() if len(m) >= 3}
    j = len(ma & mb) / len(ma | mb) if ma and mb else 0.0
    return max(j, 0.8) if (a in b or b in a) and min(len(a), len(b)) >= 8 else j


def _rattachement(vault, g: Groupe, taches: dict) -> dict:
    """Proposition pour un groupe : (a) déjà lié, (b) tâche ouverte correspondante, (c) création, (d) ignorer."""
    a, conteneur = g.titulaire, conteneur_de(vault, g.titulaire.dossier)
    liee = next((k for k, t in taches.items() if str(t.fm.get("session") or "") in g.sessions), "")
    if liee:
        return {"action": "deja", "tache": liee, "candidats": [], "conteneur": conteneur,
                "motif": langues.t("serveur.agents_cc.deja")}
    cands = []
    for k, t in taches.items():
        if not vault.ouverte(t) or t.fm.get("session"):
            continue  # INV-AGENTSCC-1 : jamais une tâche qui a déjà sa conversation
        s = similitude(a.nom, t.titre) + (BONUS_DOSSIER if conteneur and t.conteneur == conteneur else 0)
        if s >= SEUIL_CANDIDAT:
            cands.append({"tache": k, "titre": t.titre, "score": round(min(s, 1.0), 2)})
    cands = sorted(cands, key=lambda c: -c["score"])[:3]
    if cands and cands[0]["score"] >= SEUIL_TITRE:
        return {"action": "rattacher", "tache": cands[0]["tache"], "candidats": cands, "conteneur": conteneur,
                "motif": langues.t("serveur.agents_cc.proche", titre=cands[0]["titre"])}
    if not a.detail and a.etat != "blocked":
        return {"action": "ignorer", "tache": "", "candidats": cands, "conteneur": conteneur,
                "motif": langues.t("serveur.agents_cc.clos")}
    return {"action": "creer", "tache": "", "candidats": cands, "conteneur": conteneur,
            "motif": langues.t("serveur.agents_cc.aucune")}


def _vue_agent(a: Agent) -> dict:
    return {"job": a.job, "session": a.session, "etat": a.etat, "maj": a.maj, "cree": a.cree}


class Releve:
    """Dernier relevé en mémoire (rafraîchi au rythme réglé, ou à la demande) et sessions ignorées."""

    def __init__(self, moteur):
        self.moteur = moteur
        self.cfg = moteur.config.agents_cc
        self.chemin = moteur.config.donnees / "etat" / "agents_cc.json"
        try:
            etat = json.loads(self.chemin.read_text("utf-8"))
        except (OSError, ValueError):
            etat = {}
        self.etat = etat if isinstance(etat, dict) else {}
        self.groupes: list[Groupe] | None = None

    def actif(self) -> bool:
        return bool(self.cfg.dossier)

    def _sauver(self) -> None:
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.chemin, json.dumps(self.etat, ensure_ascii=False, indent=1))
        except OSError as e:
            log.warning("état des agents de Claude Code non persisté : %s", e)

    def relever(self) -> list[Groupe]:
        if not self.actif():
            self.groupes = []
            return self.groupes
        self.groupes = regrouper(lire_jobs(Path(self.cfg.dossier).expanduser()))
        self.etat["derniere"] = dt.datetime.now().isoformat(timespec="seconds")
        self._sauver()
        return self.groupes

    def courants(self) -> list[Groupe]:
        return self.relever() if self.groupes is None else self.groupes

    def ignores(self) -> set[str]:
        return set(self.etat.get("ignores") or [])

    def due(self, maintenant: dt.datetime) -> bool:
        periode = PERIODES.get(self.cfg.rythme)
        if not self.actif() or periode is None:
            return False
        try:
            return maintenant - dt.datetime.fromisoformat(str(self.etat.get("derniere"))) >= periode
        except ValueError:
            return True

    def vue(self) -> list[dict]:
        """Tous les groupes, avec leur rattachement proposé ; `decision` : reste à trancher."""
        taches, ignores = self.moteur.vault.index()[0], self.ignores()
        sortie = []
        for g in self.courants():
            r = _rattachement(self.moteur.vault, g, taches)
            ignore = g.titulaire.session in ignores
            a = g.titulaire
            sortie.append({
                "id": g.ident, "nom": a.nom, "etat": a.etat, "dossier": a.dossier, "maj": a.maj, "cree": a.cree,
                "session": a.session, "detail": a.detail, "historique": [_vue_agent(h) for h in g.historique],
                "ignore": ignore, "decision": r["action"] != "deja" and not ignore,
                "reprise_ici": _chemin(a.cwd) == _chemin(a.dossier) or not a.cwd, **r})
        return sortie

    def decisions(self) -> list[dict]:
        return [v for v in self.vue() if v["decision"]]

    def appliquer(self, choix: list[dict]) -> dict:
        """Applique le lot geste par geste ; un refus n'arrête pas le lot (INV-AGENTSCC-1)."""
        faits, echecs = [], []
        for c in choix:
            try:
                self._un(str(c.get("id") or ""), str(c.get("action") or ""), str(c.get("tache") or ""))
                faits.append(c.get("id"))
            except ErreurOrch as e:
                echecs.append({"cible": c.get("id"), "erreur": str(e)})
        self.moteur.publier("arbre")
        return {"faits": faits, "echecs": echecs}

    def _un(self, ident: str, action: str, tache: str) -> None:
        g = next((g for g in self.courants() if g.ident == ident), None)
        if g is None:
            raise NonTrouve(langues.t("serveur.agents_cc.inconnu", ident=ident))
        if action not in ACTIONS:
            raise Invalide(langues.t("serveur.agents_cc.action_inconnue", action=action))
        m, a = self.moteur, g.titulaire
        if action == "ignorer":
            self.etat["ignores"] = sorted(self.ignores() | g.sessions)
            self._sauver()
            return
        if "claude" not in m.registre:
            raise Invalide(langues.t("serveur.agents_cc.claude_indisponible"))
        maj = {"session": a.session, "harnais": "claude"}  # session déjà validée à la lecture
        if action == "rattacher":
            t = m.vault.tache(tache)
            if t.fm.get("session"):
                raise Invalide(langues.t("serveur.agents_cc.deja_conversation", titre=t.titre))
            m.demi_verrou(tache, False, seule=True)
            m.vault.modifier(tache, maj)
            return
        conteneur = conteneur_de(m.vault, a.dossier)
        ident_t = m.creer(a.nom, _description(a), conteneur=conteneur)
        m.vault.modifier(ident_t, maj)

    async def boucle(self) -> None:
        if PERIODES.get(self.cfg.rythme) is None:
            return
        while True:
            try:
                if self.due(dt.datetime.now()):
                    await asyncio.to_thread(self.relever)
                    self.moteur.publier("arbre")  # le compteur de « Décisions » se met à jour
            except Exception:  # le relevé survit à un échec ponctuel
                log.exception("relevé des agents de Claude Code non fait")
            await asyncio.sleep(60)


def _description(a: Agent) -> str:
    base = (f"Agent de Claude Code « {a.nom} » repris dans GoldenBrain (dernière activité {a.maj[:10]}, "
            f"état {a.etat or 'inconnu'}) ; sa conversation d'origine se reprend depuis cette tâche.")
    return f"{base} Dernier message : {a.detail}" if a.detail else base
