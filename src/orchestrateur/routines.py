"""Routines programmées : tâches `nature: routine` exécutées à l'heure par la file du moteur.

Rôle : créer une routine, tenir sa prochaine échéance et son historique (`etat/routines.json`),
soumettre un tour à l'heure (rattrapage d'une échéance manquée, jamais deux exécutions
simultanées), pause / reprise, « Exécuter maintenant », annoter l'arbre et les « Décisions ».
Frontières : n'exécute rien lui-même — tout passe par `moteur.soumettre` (file, mémoire,
prérequis, réseau, poste) ; n'écrit dans le vault que par `Vault` (clés gérées) ; l'analyse du
programme est dans `programme.py`.
Invariants portés : INV-ROUTINE-1 à INV-ROUTINE-5.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from collections.abc import Callable

from . import fiches, langues, programme, reseau
from .vault import Conflit, Invalide, NonTrouve

log = logging.getLogger(__name__)
NATURE = "routine"
ACTIVE, EN_PAUSE = "active", "en-pause"
CONTEXTES = ("suite", "neuf")
RATTRAPAGES = ("une", "aucune")
OCCUPEE = ("en_cours", "en_file", "en_pause", reseau.ETAT)
RETARD_TOLERE = dt.timedelta(minutes=5)  # la boucle passe chaque minute : au-delà, échéance manquée
HISTORIQUE_MAX = 30


def est_routine(t) -> bool:
    return str(t.fm.get("nature") or "") == NATURE


def consigne_de(t) -> str:
    """Corps de la note, sans le titre ni la fiche : la consigne donnée à chaque exécution."""
    lignes = fiches.corps_sans_fiche(fiches.lire(t.chemin)).splitlines()
    if lignes and lignes[0].startswith("# "):
        lignes = lignes[1:]
    return "\n".join(lignes).strip() or t.titre


class Routines:
    def __init__(self, moteur, horloge: Callable[[], dt.datetime] = dt.datetime.now):
        self.moteur = moteur
        self.vault = moteur.vault
        self.chemin = moteur.config.donnees / "etat" / "routines.json"
        self.horloge = horloge  # injectable : les tests avancent le temps sans attendre
        self.etat: dict[str, dict] = self._lire()

    # --- état persistant -------------------------------------------------------------
    def _lire(self) -> dict:
        try:
            etat = json.loads(self.chemin.read_text("utf-8"))
        except (OSError, ValueError):
            return {}  # absent ou corrompu : le serveur démarre quand même
        return etat if isinstance(etat, dict) else {}

    def _sauver(self) -> None:
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.chemin, json.dumps(self.etat, ensure_ascii=False))
        except OSError as e:
            log.warning("état des routines non persisté : %s", e)

    def _routines(self) -> dict:
        return {k: t for k, t in self.vault.index()[0].items() if est_routine(t)}

    def _routine(self, ident: str):
        t = self.vault.tache(ident)
        if not est_routine(t):
            raise Invalide(langues.t("serveur.routines.pas_routine"))
        return t

    # --- gestes ------------------------------------------------------------------------
    def creer(self, titre: str, consigne: str, prog: str, conteneur: str | None = None,
              harnais: str | None = None, modele: str | None = None, contexte: str = "suite",
              rattrapage: str = "une") -> str:
        programme.analyser(prog)  # INV-ROUTINE-2 : refusé avant toute écriture
        if contexte not in CONTEXTES or rattrapage not in RATTRAPAGES:
            raise Invalide(langues.t("serveur.routines.contexte_invalide"))
        if not (consigne or "").strip():
            raise Invalide(langues.t("serveur.routines.consigne_requise"))
        ident = self.moteur.creer(titre, consigne, conteneur, harnais=harnais, modele=modele)
        # Clés posées par l'écriture gérée (INV-VAULT-1) ; la routine n'a pas de cycle a-faire/fait.
        self.vault.modifier(ident, {"nature": NATURE, "programme": prog.strip(), "routine": ACTIVE,
                                    "contexte": contexte, "rattrapage": rattrapage, "statut": "en-cours"})
        self._planifier(ident, self.vault.tache(ident), self.horloge())  # l'échéance compte dès la création
        self._sauver()
        self.moteur.publier("arbre")
        return ident

    def convertir(self, ident: str, prog: str, contexte: str = "suite", rattrapage: str = "une") -> dict:
        """Fait d'une tâche existante une routine, sur place : même fichier, même session, même statut.
        La consigne est le corps de la note (comme à la création) ; rien n'est exécuté tant que
        l'échéance n'est pas atteinte."""
        t = self.vault.tache(ident)
        if est_routine(t):
            raise Conflit(langues.t("serveur.routines.deja_routine"))
        if self.moteur.etat_de(ident) in OCCUPEE:
            raise Conflit(langues.t("serveur.routines.convertir_en_cours"))
        programme.analyser(prog)  # INV-ROUTINE-2 : refusé avant toute écriture
        if contexte not in CONTEXTES or rattrapage not in RATTRAPAGES:
            raise Invalide(langues.t("serveur.routines.contexte_invalide"))
        self.vault.modifier(ident, {"nature": NATURE, "programme": prog.strip(), "routine": ACTIVE,
                                    "contexte": contexte, "rattrapage": rattrapage})
        self._planifier(ident, self.vault.tache(ident), self.horloge())
        self._sauver()
        self.moteur.publier("arbre")
        return self.public(ident)

    def retirer(self, ident: str) -> None:
        """Geste inverse : la tâche redevient ordinaire (statut et historique d'exécutions conservés)."""
        self._routine(ident)
        if self.moteur.etat_de(ident) in OCCUPEE:
            raise Conflit(langues.t("serveur.routines.retirer_en_cours"))
        self.vault.modifier(ident, {k: None for k in ("nature", "programme", "routine", "contexte", "rattrapage")})
        self.etat.get(ident, {}).pop("prochaine", None)
        self._sauver()
        self.moteur.publier("arbre")

    def modifier(self, ident: str, prog: str | None = None, pause: bool | None = None) -> dict:
        self._routine(ident)
        maj: dict = {}
        if prog is not None:
            programme.analyser(prog)  # INV-ROUTINE-2
            maj["programme"] = prog.strip()
        if pause is not None:
            maj["routine"] = EN_PAUSE if pause else ACTIVE
        if maj:
            self.vault.modifier(ident, maj)
            # INV-ROUTINE-3 : la prochaine échéance repart de maintenant (pas de rattrapage d'une pause).
            self.etat.setdefault(ident, {}).pop("prochaine", None)
            self._planifier(ident, self.vault.tache(ident), self.horloge())
            self._sauver()
            self.moteur.publier("arbre")
        return self.public(ident)

    def executer(self, ident: str, origine: str = "manuelle") -> str:
        """Soumet une exécution maintenant ; 409 si la précédente n'est pas finie (INV-ROUTINE-1)."""
        t = self._routine(ident)
        self._clore(ident)
        if self.moteur.etat_de(ident) in OCCUPEE:
            raise Conflit(langues.t("serveur.routines.precedente_non_terminee"))
        if str(t.fm.get("contexte") or "") == "neuf":
            self.vault.modifier(ident, {"session": None})  # une conversation neuve par exécution
        quand = self.horloge()
        texte = (f"[Routine « {t.titre} » — exécution {origine} du {quand:%d/%m/%Y %H:%M}]\n"
                 f"{consigne_de(t)}\n\n(INV-ROUTINE-4) Si l'exécution produit un livrable ou une action "
                 "pour l'utilisateur, dis-le dans ta fiche et, si besoin, crée une tâche (orch creer).")
        etat = self.moteur.soumettre(ident, texte)
        self._noter(ident, {"a": quand.isoformat(timespec="seconds"), "origine": origine, "issue": "en_cours"})
        return etat

    # --- planification -----------------------------------------------------------------
    def _noter(self, ident: str, entree: dict) -> None:
        e = self.etat.setdefault(ident, {})
        e["historique"] = (e.get("historique") or [])[-(HISTORIQUE_MAX - 1):] + [entree]
        self._sauver()

    def _clore(self, ident: str) -> None:
        """Issue de la dernière exécution, lue une fois le tour fini (échec_tour posé par le moteur)."""
        hist = (self.etat.get(ident) or {}).get("historique") or []
        if not hist or hist[-1].get("issue") != "en_cours" or self.moteur.etat_de(ident) in OCCUPEE:
            return
        try:
            t = self.vault.tache(ident)
        except NonTrouve:
            return
        echec = str(t.fm.get("echec_tour") or "")
        hist[-1].update(issue="echouee" if echec else "reussie", session=str(t.fm.get("session") or ""),
                        **({"motif": echec} if echec else {}))
        self._sauver()

    def _planifier(self, ident: str, t, maintenant: dt.datetime) -> dt.datetime | None:
        e = self.etat.setdefault(ident, {})
        if str(t.fm.get("routine") or ACTIVE) == EN_PAUSE:
            e.pop("prochaine", None)
            return None
        prog = str(t.fm.get("programme") or "")
        if e.get("programme") != prog or not e.get("prochaine"):
            try:
                p = programme.prochaine(programme.analyser(prog), maintenant)
            except Invalide as err:
                e.update(programme=prog, prochaine=None, erreur=str(err))
                return None
            e.update(programme=prog, prochaine=p.isoformat(timespec="minutes") if p else None)
            e.pop("erreur", None)
        return dt.datetime.fromisoformat(e["prochaine"]) if e.get("prochaine") else None

    def verifier(self) -> list[str]:
        """Un passage du planificateur : exécute les routines échues ; renvoie leurs identifiants."""
        maintenant, lancees = self.horloge(), []
        for ident, t in self._routines().items():
            self._clore(ident)
            echeance = self._planifier(ident, t, maintenant)
            if echeance is None or echeance > maintenant:
                continue
            e = self.etat[ident]
            suivante = programme.prochaine(programme.analyser(e["programme"]), maintenant)
            e["prochaine"] = suivante.isoformat(timespec="minutes") if suivante else None
            manquee = maintenant - echeance > RETARD_TOLERE
            a = echeance.isoformat(timespec="minutes")
            # INV-ROUTINE-3 : plusieurs échéances manquées ne donnent qu'un rattrapage, ou aucun.
            if manquee and str(t.fm.get("rattrapage") or "une") == "aucune":
                self._noter(ident, {"a": a, "issue": "sautee", "motif": langues.t("serveur.routines.rattrapage_manque")})
            elif self.moteur.etat_de(ident) in OCCUPEE:  # INV-ROUTINE-1
                self._noter(ident, {"a": a, "issue": "sautee", "motif": langues.t("serveur.routines.precedente_non_terminee")})
            else:
                try:
                    self.executer(ident, "rattrapée" if manquee else "programmée")
                    lancees.append(ident)
                except Exception as err:  # une routine en échec n'arrête pas les autres
                    log.exception("routine %s non lancée", ident)
                    self._noter(ident, {"a": a, "issue": "echouee", "motif": langues.t("serveur.routines.non_lancee", erreur=err)})
            self._sauver()
        return lancees

    async def boucle(self) -> None:
        while True:
            try:
                self.verifier()
            except Exception:  # le planificateur survit à un échec ponctuel
                log.exception("planificateur des routines")
            await asyncio.sleep(60)

    # --- lecture -------------------------------------------------------------------------
    def public(self, ident: str, t=None) -> dict:
        t = t or self._routine(ident)
        self._clore(ident)
        e = self.etat.get(ident) or {}
        prochaine = self._planifier(ident, t, self.horloge())
        hist = e.get("historique") or []
        derniere = next((h for h in reversed(hist) if h.get("issue") != "sautee"), None)
        return {"id": ident, "titre": t.titre, "programme": str(t.fm.get("programme") or ""),
                "etat": str(t.fm.get("routine") or ACTIVE), "contexte": str(t.fm.get("contexte") or "suite"),
                "rattrapage": str(t.fm.get("rattrapage") or "une"),
                "prochaine": prochaine.isoformat(timespec="minutes") if prochaine else None,
                "erreur": e.get("erreur") or "", "derniere": derniere, "historique": list(reversed(hist))}

    def liste(self) -> list[dict]:
        return [self.public(k, t) for k, t in self._routines().items()]

    def annoter(self, noeuds: list[dict]) -> list[dict]:
        """INV-ROUTINE-5 : une routine reste à sa place dans l'arbre, avec son repère `routine`."""
        routines = self._routines()
        pile = list(noeuds)
        while pile:
            n = pile.pop()
            pile.extend(n.get("enfants") or [])
            if n.get("type") == "tache" and n.get("id") in routines:
                p = self.public(n["id"], routines[n["id"]])
                n["routine"] = {k: p[k] for k in ("programme", "etat", "prochaine", "derniere", "erreur")}
        return noeuds

    def en_echec(self) -> list[tuple[str, dict]]:
        """Routines actives dont la dernière exécution a échoué : une ligne chacune dans « Décisions »
        (la mettre en pause vaut réponse)."""
        return [(p["id"], p["derniere"]) for p in self.liste()
                if p["etat"] == ACTIVE and p["derniere"] and p["derniere"].get("issue") == "echouee"]
