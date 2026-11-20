"""Signe de vie des tours : phrase d'activité, raison d'attente, silence et exploration signalés.

Rôle : écoute les événements publiés par le moteur (comme un abonné SSE) et tient, par tour en
cours, la phrase de ce que fait l'agent, l'heure de son dernier événement et le nombre de lectures
consécutives. Une veille marque « silencieux » un tour muet depuis `[vigie] silence_s`, le
diagnostique (`diagnostic`, hors de la boucle asyncio) et publie l'alerte (SSE `vigie`). Dit aussi
pourquoi un tour en file n'a pas démarré.
Frontières : aucune écriture vault ; aucun arrêt de sa propre initiative (gestes humains :
arrêter un descendant du tour, attendre) ; lit l'état du moteur et des créneaux sans le modifier.
Tient aussi le suivi du tour (sous-agents lancés, avancement, fichiers modifiés) lu dans les
événements `suivi` et `tour_outil` (tableau « En cours »).
Invariants portés : INV-VIGIE-1 (détection seule ; un arrêt n'atteint qu'un descendant du tour),
INV-VIGIE-2 (raison d'attente d'un tour en file), INV-TRAVAUX-1 (suivi lu dans le flux, borné).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time
from dataclasses import dataclass, field

from . import diagnostic, echecs, langues, poste_ram
from .propositions import maintenant
from .simultanes import GO, pid_de
from .vault import Conflit, Invalide

log = logging.getLogger(__name__)

# Nom d'outil (en minuscules) -> (verbe, nature). Verbe : identifiant, rendu par `_verbe`. Nature : lecture
# (compte pour l'exploration), ecriture (la remet à zéro), "" (neutre : une commande peut lire comme agir).
OUTILS = {
    "read": ("lit", "lecture"), "grep": ("cherche", "lecture"), "glob": ("fichiers", "lecture"),
    "ls": ("parcourt", "lecture"), "notebookread": ("lit", "lecture"),
    "webfetch": ("page", "lecture"), "websearch": ("web", "lecture"),
    "web_search": ("web", "lecture"),
    "write": ("ecrit", "ecriture"), "edit": ("modifie", "ecriture"), "multiedit": ("modifie", "ecriture"),
    "notebookedit": ("modifie", "ecriture"), "file_change": ("modifie", "ecriture"),
    "bash": ("lance", ""), "powershell": ("lance", ""), "command_execution": ("lance", ""),
    "task": ("sous_tache", ""), "agent": ("sous_tache", ""),
    "todowrite": ("etapes", ""), "skill": ("methode", ""),
}
FICHIER = {"lit", "ecrit", "modifie"}
# Commande lancée -> phrase simple (tableau « En cours ») ; la première qui correspond l'emporte.
COMMANDES = [
    (re.compile(r"pytest|check(_ui)?\.py|\b(npm|pnpm|yarn) (run )?test|cargo test|go test", re.I), "tests"),
    (re.compile(r"\bgit (commit|merge|rebase)\b", re.I), "enregistre"),
    (re.compile(r"\bgit push\b", re.I), "publie"),
    (re.compile(r"\b(pip|npm|pnpm|yarn|uv) (install|add)\b", re.I), "installe"),
]
SOUS_AGENTS_MAX = 20  # INV-TRAVAUX-1 : un tour qui en lance des centaines ne gonfle pas l'état
CHERCHE = re.compile(r"search|find|query|list|get|read", re.I)


def _outil(texte: str) -> tuple[str, str]:
    nom, _, detail = (texte or "").partition(":")
    return nom.strip(), " ".join(detail.split())


def nature_outil(texte: str) -> str:
    return OUTILS.get(_outil(texte)[0].lower(), ("", ""))[1]


def _verbe(verbe: str, detail: str) -> str:
    """Phrase d'une action de l'agent ; `detail` toujours en fin de phrase (vide : retiré par `strip`)."""
    t = langues.t
    match verbe:
        case "lit":
            return t("serveur.vigie.verbe_lit", detail=detail)
        case "cherche":
            return t("serveur.vigie.verbe_cherche", detail=detail)
        case "fichiers":
            return t("serveur.vigie.verbe_fichiers", detail=detail)
        case "parcourt":
            return t("serveur.vigie.verbe_parcourt", detail=detail)
        case "page":
            return t("serveur.vigie.verbe_page", detail=detail)
        case "web":
            return t("serveur.vigie.verbe_web", detail=detail)
        case "ecrit":
            return t("serveur.vigie.verbe_ecrit", detail=detail)
        case "modifie":
            return t("serveur.vigie.verbe_modifie", detail=detail)
        case "lance":
            return t("serveur.vigie.verbe_lance", detail=detail)
        case "sous_tache":
            return t("serveur.vigie.verbe_sous_tache", detail=detail)
        case "etapes":
            return t("serveur.vigie.verbe_etapes", detail=detail)
        case "methode":
            return t("serveur.vigie.verbe_methode", detail=detail)
        case "tests":
            return t("serveur.vigie.commande_tests")
        case "enregistre":
            return t("serveur.vigie.commande_enregistre")
        case "publie":
            return t("serveur.vigie.commande_publie")
        case "installe":
            return t("serveur.vigie.commande_installe")
    return ""


def phrase_outil(texte: str) -> str:
    """« Write: C:/x/build.py » -> « écrit build.py » ; « mcp__claude_ai_Gmail__search_threads »
    -> « cherche dans Gmail »."""
    nom, detail = _outil(texte)
    if nom.lower().startswith("mcp__"):
        parts = nom.split("__")
        serveur = re.sub(r"^(claude_ai_|plugin_[^_]+_)", "", parts[1] if len(parts) > 1 else "")
        serveur = serveur.replace("_", " ") or langues.t("serveur.vigie.un_connecteur")
        action = parts[-1] if len(parts) > 2 else ""
        if CHERCHE.search(action):
            return langues.t("serveur.vigie.mcp_cherche", serveur=serveur)
        return langues.t("serveur.vigie.mcp_utilise", serveur=serveur)
    verbe = OUTILS.get(nom.lower(), ("", ""))[0]
    if verbe == "lance" and (simple := next((p for r, p in COMMANDES if r.search(detail)), "")):
        return _verbe(simple, "")
    if not verbe:
        if not nom:
            return ""
        if detail:
            return langues.t("serveur.vigie.outil_detail", nom=nom, detail=detail[:60])
        return langues.t("serveur.vigie.outil", nom=nom)
    if verbe in FICHIER:
        detail = re.split(r"[\\/]", detail)[-1]
    return _verbe(verbe, detail[:80]).strip()


def phrase_texte(texte: str) -> str:
    """Première phrase du dernier paragraphe écrit par l'agent, sans balisage, 160 caractères."""
    paras = [p for p in re.split(r"\n\s*\n", texte or "") if p.strip()]
    if not paras:
        return ""
    p = re.sub(r"[`*_>#]|^\s*[-+]\s+", "", " ".join(paras[-1].split()))
    phrase = re.match(r"(.+?[.!?…:])(\s|$)", p)
    p = (phrase[1] if phrase else p).strip()
    return p[:160] + ("…" if len(p) > 160 else "")


@dataclass
class Signe:
    tour: object
    dernier: float  # horloge du dernier événement
    date: str       # même instant, en ISO, pour l'interface (« il y a 40 s »)
    texte: str = ""
    etape: str = ""
    lectures: int = 0
    acquitte: float = 0.0  # « Attendre » : pas d'alerte avant cette horloge
    diagnostic: dict | None = None
    alerte: bool = False
    sous_agents: dict = field(default_factory=dict)  # id -> {description, genre, debut, fin, erreur}
    avancement: dict | None = None
    fichiers: set = field(default_factory=set)


class Vigie:
    def __init__(self, moteur, horloge=time.monotonic, sonde=diagnostic.diagnostiquer,
                 arret=diagnostic.arreter):
        self.m, self.horloge, self.sonde, self.arret = moteur, horloge, sonde, arret
        self.signes: dict[str, Signe] = {}
        self._taches: list[asyncio.Task] = []

    @property
    def cfg(self):
        return self.m.config.vigie

    # --- écoute ----------------------------------------------------------------------------
    def demarrer(self) -> None:
        q = self.m.abonner()
        boucle = asyncio.get_running_loop()
        self._taches = [boucle.create_task(self._ecouter(q)), boucle.create_task(self._veiller())]

    def fermer(self) -> None:
        for t in self._taches:
            t.cancel()

    async def _ecouter(self, q: asyncio.Queue) -> None:
        while True:
            e = await q.get()
            try:
                self.noter(e)
            except Exception:  # INV-EXEC-6 : l'écoute ne meurt pas en silence
                log.exception("vigie : événement %s", e.get("type"))

    def _signe(self, ident: str) -> Signe | None:
        tour = self.m.tours.get(ident)
        if tour is None:
            self.signes.pop(ident, None)
            return None
        s = self.signes.get(ident)
        if s is None or s.tour is not tour:
            try:  # le silence court depuis le début du tour, pas depuis la première veille
                age = max(0.0, (dt.datetime.now() - dt.datetime.fromisoformat(tour.depuis)).total_seconds())
            except (TypeError, ValueError):
                age = 0.0
            s = self.signes[ident] = Signe(tour, self.horloge() - age, tour.depuis or maintenant())
        return s

    def noter(self, e: dict) -> None:
        type_, ident = e.get("type"), e.get("tache")
        if type_ == "tour_fin":
            self.signes.pop(ident, None)
            return
        if type_ not in ("tour_texte", "tour_outil", "pause_ram", "suivi") or not ident:
            return
        if (s := self._signe(ident)) is None:
            return
        if type_ == "suivi":
            self._suivre(s, e)
            return
        avant = self._etat(ident, s)
        s.dernier, s.date, s.diagnostic = self.horloge(), maintenant(), None
        if type_ == "tour_texte":
            s.texte, s.lectures = phrase_texte(e.get("texte", "")) or s.texte, 0
        elif type_ == "tour_outil":
            s.etape = phrase_outil(e.get("texte", ""))
            nature = nature_outil(e.get("texte", ""))
            if nature == "ecriture" and (chemin := _outil(e.get("texte", ""))[1]):
                s.fichiers.add(chemin)
            s.lectures = s.lectures + 1 if nature == "lecture" else 0 if nature == "ecriture" else s.lectures
        if self._etat(ident, s) != avant:
            self.m.publier("vigie", tache=ident)

    def _suivre(self, s: Signe, e: dict) -> None:
        """INV-TRAVAUX-1 : sous-agent lancé ou revenu, avancement de la liste d'étapes."""
        s.dernier, s.date = self.horloge(), maintenant()  # un sous-agent qui avance n'est pas un silence
        if isinstance(a := e.get("avancement"), dict):
            s.avancement = {"fait": int(a.get("fait") or 0), "total": int(a.get("total") or 0)}
        if isinstance(sa := e.get("sous_agent"), dict) and (sid := str(sa.get("id") or "")):
            if sa.get("fin"):
                if sid in s.sous_agents and not s.sous_agents[sid]["fin"]:
                    s.sous_agents[sid].update(fin=maintenant(), erreur=bool(sa.get("erreur")))
            elif sid not in s.sous_agents:
                s.sous_agents[sid] = {"description": str(sa.get("description") or ""),
                                      "genre": str(sa.get("genre") or ""), "debut": maintenant(),
                                      "fin": None, "erreur": False}
                while len(s.sous_agents) > SOUS_AGENTS_MAX:  # le plus ancien fini part d'abord
                    vieux = next((k for k, v in s.sous_agents.items() if v["fin"]), next(iter(s.sous_agents)))
                    s.sous_agents.pop(vieux)

    # --- état ------------------------------------------------------------------------------
    def _etat(self, ident: str, s: Signe) -> tuple[bool, bool]:
        return self._silencieux(ident, s), s.lectures >= self.cfg.lectures_max

    def _silencieux(self, ident: str, s: Signe) -> bool:
        # Un tour en pause RAM est muet par construction : ce n'est pas un silence (INV-SIMULT-1).
        h = self.horloge()
        return (h - s.dernier >= self.cfg.silence_s and h >= s.acquitte
                and not self.m._sem.en_pause(ident))

    def vue(self, ident: str) -> dict | None:
        """Signe de vie d'un tour en cours ; None hors tour."""
        if (s := self._signe(ident)) is None:
            return None
        silence = int(self.horloge() - s.dernier)
        silencieux, exploration = self._etat(ident, s)
        return {"phrase": s.texte or s.etape or langues.t("serveur.vigie.demarrage"), "etape": s.etape,
                "depuis": s.date,
                "silence_s": silence, "silencieux": silencieux,
                "exploration": exploration, "lectures": s.lectures,
                "diagnostic": s.diagnostic if silencieux else None,
                "sous_agents": [{"id": k, **v} for k, v in s.sous_agents.items()],  # INV-TRAVAUX-1
                "avancement": s.avancement, "fichiers": len(s.fichiers),
                "pause_manuelle": self.m._sem.en_pause_manuelle(ident)}

    def alertes(self) -> list[dict]:
        """Tours silencieux ou en exploration prolongée (bandeau)."""
        sortie = []
        for ident, tour in list(self.m.tours.items()):
            v = self.vue(ident)
            if v and (v["silencieux"] or v["exploration"]):
                sortie.append({"tache": ident, "titre": self._titre(ident), **v})
        return sortie

    def _titre(self, ident: str) -> str:
        try:
            return self.m.vault.tache(ident).titre
        except Exception:  # tâche disparue du vault pendant le tour
            return ident

    # --- veille ----------------------------------------------------------------------------
    async def _veiller(self) -> None:
        while not self.m.ferme:
            await asyncio.sleep(self.cfg.intervalle_s)
            try:
                await self.veiller_une_fois()
            except Exception:  # INV-EXEC-6
                log.exception("veille de la vigie")

    async def veiller_une_fois(self) -> None:
        """INV-VIGIE-1 : silence constaté -> diagnostic et alerte publiés ; rien n'est arrêté."""
        for ident in list(self.m.tours):
            if (s := self._signe(ident)) is None:
                continue
            silencieux = self._silencieux(ident, s)
            if silencieux:
                await self.diagnostiquer(ident)
            if silencieux != s.alerte:
                s.alerte = silencieux
                self.m.publier("vigie", tache=ident)
        for ident in [i for i in self.signes if i not in self.m.tours]:
            self.signes.pop(ident, None)

    async def diagnostiquer(self, ident: str) -> dict:
        s = self._signe(ident)
        if s is None:
            raise Conflit(langues.t("serveur.vigie.aucun_tour"))
        pid = pid_de(s.tour.harnais)
        try:
            d = await asyncio.to_thread(self.sonde, pid)
        except Exception as e:  # une sonde en échec se dit, elle ne tue pas la veille
            log.exception("diagnostic de %s", ident)
            d = {**diagnostic.neutre(), "phrase": langues.t("serveur.vigie.diagnostic_impossible", erreur=e)}
        d = {**d, "vivant": pid is not None, **self._trace(s.tour.harnais)}
        if self.signes.get(ident) is s:
            s.diagnostic = d
            self.m.publier("vigie", tache=ident)
        return d

    @staticmethod
    def _trace(harnais) -> dict:
        """INV-VIGIE-1 : dernière ligne du journal propre au harnais et indice quota (18/11)."""
        try:
            trace = str(getattr(harnais, "derniere_trace", lambda: "")() or "")
        except OSError:
            trace = ""
        return {"trace": trace[-400:], "quota": echecs.est_quota(trace)} if trace else {}

    # --- gestes humains --------------------------------------------------------------------
    def attendre(self, ident: str) -> None:
        """« Attendre » : l'alerte se tait pour un nouveau délai de silence."""
        if (s := self._signe(ident)) is None:
            raise Conflit(langues.t("serveur.vigie.aucun_tour"))
        s.acquitte, s.alerte = self.horloge() + self.cfg.silence_s, False
        self.m.publier("vigie", tache=ident)

    async def arreter_enfant(self, ident: str, pid: int) -> dict:
        """INV-VIGIE-1 : n'arrête que un descendant (pas la racine) de l'arbre du tour en cours ;
        l'agent reçoit l'échec de sa commande et reprend."""
        if (s := self._signe(ident)) is None:
            raise Conflit(langues.t("serveur.vigie.aucun_tour"))
        racine = pid_de(s.tour.harnais)
        if racine is None:
            raise Conflit(langues.t("serveur.vigie.programme_introuvable"))
        arbre = await asyncio.to_thread(poste_ram.arbre, racine)
        if pid == racine or pid not in arbre:
            raise Invalide(langues.t("serveur.vigie.programme_etranger"))
        if not await asyncio.to_thread(self.arret, pid):
            raise Conflit(langues.t("serveur.vigie.arret_refuse", pid=pid))
        log.info("vigie : processus %s du tour %s arrêté sur geste humain", pid, ident)
        s.diagnostic, s.acquitte, s.alerte = None, self.horloge() + self.cfg.silence_s, False
        self.m.publier("vigie", tache=ident)
        return {"arrete": pid}

    # --- raison d'attente (INV-VIGIE-2) -----------------------------------------------------
    def raison_attente(self, ident: str) -> str | None:
        """Pourquoi le tour en file de cette tâche n'a pas démarré ; None hors file."""
        if self.m.etat_de(ident) != "en_file":
            return None
        if att := self.m.attente_prerequis(ident):
            return langues.t("serveur.vigie.attente_prerequis", titres=", ".join(p["titre"] for p in att))
        if poste := self.m.attente_poste(ident):
            return langues.t("serveur.vigie.poste_reserve", titre=poste["titre"])
        raisons = []
        if (r := self.m._sem.rangs().get(ident)) and r[0] > 1:
            raisons.append(langues.t("serveur.vigie.file_derriere.plusieurs", n=r[0] - 1) if r[0] > 2
                           else langues.t("serveur.vigie.file_derriere.un", n=r[0] - 1))
        if limite := self._limite():
            raisons.append(limite)
        if quota := self._quota(ident):
            raisons.append(quota)
        return " ; ".join(raisons) or langues.t("serveur.vigie.demarrage_imminent")

    def _limite(self) -> str:
        c = self.m._sem
        if c.gele:
            return langues.t("serveur.vigie.maj_preparation")
        if c.bloque or self.m.exclusif_actif:
            return langues.t("serveur.vigie.deplacement")
        if c.regule():
            if c.pauses:
                return langues.t("serveur.vigie.pause_memoire")
            if c.depasse(c.mesure):
                return langues.t("serveur.vigie.limite_memoire", go=f"{c.mesure.libre / GO:.1f}")
            if c.cfg.mode == "optimiser" and c.mesure.cpu >= c.cfg.cpu_max_pct:
                return langues.t("serveur.vigie.processeur", pct=f"{c.mesure.cpu:.0f}")
        if c.pris >= c.limite():
            return langues.t("serveur.vigie.agents_max", pris=c.pris, limite=c.limite())
        return ""

    def _quota(self, ident: str) -> str:
        try:
            echec = str(self.m.vault.tache(ident).fm.get("echec_tour") or "")
        except Exception:
            return ""
        if not echecs.est_quota(echec):
            return ""
        r = echecs.REPRISE.search(echec)
        if r:
            return langues.t("serveur.vigie.dernier_quota_reprise", reprise=r[1])
        return langues.t("serveur.vigie.dernier_quota")
