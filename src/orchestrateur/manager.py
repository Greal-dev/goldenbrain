"""Volet « manager » : fil commun de l'assistant, lu et écrit depuis l'interface comme depuis Telegram.

Rôle : journal du fil (instructions de l'utilisateur, réponses de l'assistant, choix et gestes à boutons),
entrée d'une instruction tapée dans le volet, bouton Confirmer / Annuler / choix pressé dans le volet.
Frontières : l'assistant reste la tâche permanente du connecteur (`Connecteur.tache_tri`) : même
conversation, même entête (`telegram_assistant.entete`), mêmes gestes (`telegram_assistant.trancher`) ;
aucun appel à Telegram ici ; état dans `<donnees>/etat/manager.json`, jamais dans le vault.
Invariants portés : INV-MANAGER-1 (un seul fil pour les deux canaux), INV-TELEGRAM-3 (un geste n'est
appliqué que sur un bouton humain, une seule fois), INV-TELEGRAM-4 (nature posée par le code).
"""

from __future__ import annotations

import datetime as dt
import json

from . import fiches, langues
from . import telegram_assistant as assistant
from .vault import Conflit, Invalide

MESSAGES_MAX = 200  # le volet montre le fil récent ; la conversation complète reste celle de la tâche


class Fil:
    def __init__(self, conn):
        self.conn = conn
        self.chemin = conn.config.donnees / "etat" / "manager.json"
        try:
            etat = json.loads(self.chemin.read_text("utf-8"))
        except (OSError, ValueError):
            etat = {}
        self.etat = etat if isinstance(etat, dict) and isinstance(etat.get("messages"), list) \
            else {"n": 0, "messages": []}

    def _sauver(self) -> None:
        self.etat["messages"] = self.etat["messages"][-MESSAGES_MAX:]
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.etat, ensure_ascii=False))

    def prochain(self) -> int:
        return int(self.etat.get("n", 0)) + 1

    def ajouter(self, de: str, texte: str, canal: str, **extra) -> dict:
        """`de` : `vous` ou `manager` ; `canal` : `volet` ou `telegram` ; publié en direct (SSE)."""
        n = self.prochain()
        m = {"n": n, "de": de, "texte": texte, "canal": canal,
             "quand": dt.datetime.now().isoformat(timespec="seconds"), **extra}
        self.etat["n"] = n
        self.etat["messages"].append(m)
        self._sauver()
        self.conn.moteur.publier("manager", message=m)
        return m

    def clore(self, cle: str, issue: str) -> None:
        """Choix ou geste tranché (d'un canal ou de l'autre) : ses boutons tombent dans le volet."""
        for m in self.etat["messages"]:
            if m.get("cle") == cle and not m.get("issue"):
                m["issue"] = issue
                self._sauver()
                self.conn.moteur.publier("manager", message=m)

    def public(self) -> dict:
        ident = str(self.conn.etat.get("tache_tri") or "")
        return {"messages": self.etat["messages"], "tache": ident or None,
                "en_cours": bool(ident) and self.conn.moteur.etat_de(ident) == "en_cours",
                "telegram": bool(self.conn.cfg.actif)}

    def instruction(self, texte: str) -> dict:
        """INV-TELEGRAM-4 : ce que l'utilisateur tape dans le volet est une instruction (code, pas agent)."""
        texte = texte.strip()
        if not texte:
            raise Invalide(langues.t("serveur.manager.message_vide"))
        if texte == assistant.NOUVEAU:
            self.ajouter("vous", texte, "volet")
            return self.ajouter("manager", assistant.nouveau_fil(self.conn), "volet")
        ident = self.conn.tache_tri()
        # INV-MANAGER-1 : même tâche, même entête que Telegram ; seule l'étiquette du canal change.
        resume = self.conn.etat.get("resume", "")  # `entete` le consomme (pop) : à rendre si soumettre échoue
        try:
            self.conn.moteur.soumettre(ident, "\n".join([*assistant.entete(self.conn, ident, texte),
                                                         "[Instruction du volet]", f"[instruction] {texte}"]),
                                       humain=True)
        except Exception:
            if resume:
                self.conn.etat["resume"] = resume
            raise
        # Journalisé après soumettre : un échec ne laisse pas de doublon au renvoi (tour asynchrone, la réponse suit).
        m = self.ajouter("vous", texte, "volet")
        self.conn._sauver()
        return m

    def bouton(self, n: int, choix: str) -> dict:
        m = next((x for x in self.etat["messages"] if x.get("n") == n and x.get("cle")), None)
        if not m or m.get("issue"):
            raise Conflit(langues.t("serveur.telegram_assistant.choix_inactif"))
        texte, message = assistant.trancher(self.conn, m["cle"], choix)
        if message is None:
            raise Conflit(texte)
        self.conn.moteur.soumettre(self.conn.tache_tri(), message, humain=True)
        return {"texte": texte}
