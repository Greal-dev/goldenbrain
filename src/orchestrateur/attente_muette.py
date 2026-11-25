"""Pas d'attente muette : à la fin d'un tour, l'agent conclut ou il est renvoyé (deux fois au plus).

Rôle : juger la fin d'un tour réussi. Conclusion valable = « terminé », ou une demande humaine précise
(`prochain_pas` renseigné), ou une attente nommée (file, sous-tâche, réveil, routine, report). Sinon le tour
est muet : GoldenBrain renvoie à l'IA « conclus : terminé ou demande précise » (`MESSAGE`), au plus
`MAX_RENVOIS` fois ; ensuite la tâche passe en « Action humaine nécessaire : l'agent n'a pas conclu »
(`epuise`) et reste au statut retour. Compter les renvois par tâche, persistés dans `<donnees>/etat/attente.json`.
Frontières : aucun harnais lancé ici (le renvoi passe par `Moteur.soumettre`) ; jamais pour une tâche tenue
par l'humain, de pilotage ou permanente ; jamais pour un tour arrêté, en échec ou sans fiche (autres gardes :
INV-EXEC-1, INV-EXEC-8, INV-EXEC-12). Un geste humain (`soumettre(humain=True)`) remet le compteur à zéro.
Invariants portés : INV-MAIN-2 (une fin de tour sans conclusion est renvoyée, au plus MAX_RENVOIS fois,
sans boucle), INV-MAIN-3 (renvois épuisés = demande humaine nommée, jamais un silence).
"""

from __future__ import annotations

import json
import logging
import os
import re

from . import etat_main
from .vault import ErreurOrch

log = logging.getLogger(__name__)
MAX_RENVOIS = 2
MESSAGE = ("[GoldenBrain — conclus] Ton dernier tour ne conclut pas : la tâche n'est ni terminée ni en attente "
           "d'une demande précise. Ne refais pas le travail. Rends seulement un bloc <fiche> final : statut "
           "terminee si c'est fini ; sinon statut en_attente avec, dans prochain_pas, UNE demande humaine "
           "précise (question fermée ou choix). Une fiche « reste : … » sans demandeur n'est pas une conclusion.")
VIDE = re.compile(r"^\W*(rien|aucun[e]?|néant|n/?a|none|tout est fait)?\W*$", re.I)


class AttenteMuette:
    def __init__(self, moteur):
        self.m = moteur
        self.chemin = moteur.config.donnees / "etat" / "attente.json"
        self.etat: dict[str, dict] = self._lire()

    def _lire(self) -> dict:
        try:
            return json.loads(self.chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _ecrire(self) -> None:
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.etat, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.chemin)
        except OSError as e:
            log.warning("compteur de renvois non écrit : %s", e)

    def renvois(self, ident: str) -> int:
        return int(self.etat.get(ident, {}).get("renvois") or 0)

    def epuise(self, ident: str) -> bool:
        return bool(self.etat.get(ident, {}).get("epuise"))

    def remettre(self, ident: str) -> None:
        """Un geste humain ou une conclusion valable repart de zéro."""
        if self.etat.pop(ident, None) is not None:
            self._ecrire()

    def conclusion(self, statut: str, fiche: dict, t) -> bool:
        """Vrai si le tour s'est conclu : terminé, demande précise, ou attente nommée."""
        if statut == "fait":
            return True
        demande = " ".join(str(fiche.get("prochain_pas") or "").split())
        if statut == self.m.vault.retour:
            return bool(demande) and not VIDE.match(demande)
        if statut == "en-cours":
            return etat_main.en_attente_legitime(self.m, etat_main.Contexte(self.m), t) is not None
        return True  # bloque, etc. : déjà expliqué par ses propres gardes

    def juger(self, ident: str, statut: str, fiche: dict) -> str | None:
        """None (conclu ou hors périmètre), `renvoye` ou `epuise` ; applique le verdict."""
        try:
            t = self.m.vault.tache(ident)
        except ErreurOrch:
            return None
        if t.pilotage or str(t.fm.get("nature") or "") in ("permanente", "recurrente") or str(t.fm.get("executant") or "") == "humain":
            return None
        if self.conclusion(statut, fiche, t):
            self.remettre(ident)
            return None
        rec = self.etat.setdefault(ident, {"renvois": 0, "epuise": False})
        if rec["renvois"] >= MAX_RENVOIS:
            rec["epuise"] = True
            self._ecrire()
            if statut != self.m.vault.retour:
                self.m.vault.poser_statut(ident, self.m.vault.retour)  # INV-MAIN-3 : jamais « en-cours » sans personne
            return "epuise"
        rec["renvois"] += 1
        self._ecrire()
        self.renvoyer(ident)
        return "renvoye"

    def renvoyer(self, ident: str, consigne: str = "") -> None:
        texte = MESSAGE + (f"\n\nConsigne de l'utilisateur : {consigne.strip()}" if consigne.strip() else "")
        try:
            self.m.soumettre(ident, texte, direct=True)
        except ErreurOrch as e:
            log.warning("renvoi de %s impossible : %s", ident, e)
