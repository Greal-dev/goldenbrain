"""Pastille « évitable ? » de la page Décisions : cette tâche aurait-elle pu être tranchée par l'agent ?

Rôle : pour une décision `reponse` ou `validation`, compter des critères vérifiables sans IA et, si
la part remplie atteint le seuil réglé, produire un motif lisible (critères remplis et manquants).
Réglage (activée, seuil en % des critères) persisté dans `<donnees>/etat/evitable.json`, relu à chaque
lecture, modifié depuis la page Réglages. Défaut : activée, 75 % (informatif et sans effet sur le
vault ; 75 % exige « presque tout » sans bloquer sur un critère douteux).
Frontières : lecture seule du vault, du journal de validation automatique et des verdicts de contrôle ;
n'écrit que son fichier de réglage ; ne pose aucun statut (la décision reste à l'utilisateur).
Invariants portés : INV-EVITABLE-1.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path

from . import fiches, langues, validation_auto as va
from .vault import Invalide, NonTrouve

log = logging.getLogger(__name__)
DEFAUT = {"actif": True, "seuil": 75}
SEUIL_MIN, SEUIL_MAX = 25, 100
GENRES = ("reponse", "validation")
# Question de l'agent qui demande une permission ou un choix ordinaire plutôt qu'un arbitrage.
PERMISSION = re.compile(r"\b(veux-tu|voulez-vous|dois-je|puis-je|souhaites-tu|souhaitez-vous|"
                        r"je proc[eè]de|ok pour|d'accord pour|tu pr[ée]f[èe]res|on continue)\b", re.I)


def _fichier(donnees: Path) -> Path:
    return donnees / "etat" / "evitable.json"


def lire(donnees: Path) -> dict:
    """Réglage effectif ; fichier absent ou illisible : défaut (jamais d'erreur à la lecture)."""
    try:
        brut = json.loads(_fichier(donnees).read_text("utf-8"))
    except (OSError, ValueError):
        brut = {}
    brut = brut if isinstance(brut, dict) else {}
    seuil = brut.get("seuil")
    return {"actif": brut["actif"] if isinstance(brut.get("actif"), bool) else DEFAUT["actif"],
            "seuil": seuil if isinstance(seuil, int) and SEUIL_MIN <= seuil <= SEUIL_MAX else DEFAUT["seuil"]}


def regler(donnees: Path, actif: bool | None = None, seuil: int | None = None) -> dict:
    """Écrit les champs donnés (validés avant toute écriture) et rend le réglage effectif."""
    if seuil is not None and not SEUIL_MIN <= seuil <= SEUIL_MAX:
        raise Invalide(langues.t("serveur.evitable.seuil_invalide", mini=SEUIL_MIN, maxi=SEUIL_MAX))
    r = lire(donnees)
    if actif is not None:
        r["actif"] = actif
    if seuil is not None:
        r["seuil"] = seuil
    _fichier(donnees).parent.mkdir(parents=True, exist_ok=True)
    fiches.ecrire_atomique(_fichier(donnees), json.dumps(r, indent=1))  # INV-VAULT-2
    return r


def _criteres(moteur, t, genre: str, question: str) -> list[tuple[str, bool]]:
    if genre == "reponse":
        return [(langues.t("serveur.evitable.critere_permission"), bool(PERMISSION.search(question))),
                (langues.t("serveur.evitable.critere_perimetre"), moteur.validation_auto.applique(t.id))]
    vue = moteur.controle_vue(t.id)
    v = (vue or {}).get("verdict") or {}
    a = moteur.validation_auto.motif(t.id)
    # INV-VALID-2 : `revue_refusee` marque le refus de la revue IA sans lire un motif traduit ; l'ancien préfixe
    # « revue IA » couvre les entrées du journal écrites avant.
    refus_revue = bool(a and a["issue"] == "refus"
                       and (a.get("revue_refusee") or str(a.get("motif", "")).startswith("revue IA")))
    return [(langues.t("serveur.evitable.critere_fiche"), bool(str(t.fiche.get("resultat") or "").strip()
                                                              and str(t.fiche.get("essai") or "").strip())),
            (langues.t("serveur.evitable.critere_essai"), not va.demontrable(t)),
            (langues.t("serveur.evitable.critere_controle"), v.get("verdict") == "reussi" and v.get("perime") is False),
            (langues.t("serveur.evitable.critere_revue"), not refus_revue)]


def evaluer(moteur, t, genre: str, question: str, reglage: dict) -> dict | None:
    """INV-EVITABLE-1 : None si la pastille ne s'affiche pas ; sinon {score, sur, seuil, motif, criteres}.
    Une exclusion sensible (argent, envoi, secret, publication…) écarte toujours la pastille."""
    if not reglage["actif"] or genre not in GENRES:
        return None
    try:
        r = va.reglage(moteur.vault, t.id)
    except NonTrouve:
        return None
    if va.exclusion(t, r["exclusions"], r["exemptions"]):
        return None
    criteres = _criteres(moteur, t, genre, question)
    score = sum(ok for _, ok in criteres)
    if score < max(1, math.ceil(reglage["seuil"] / 100 * len(criteres))):
        return None
    detail = " ; ".join(f"{'✓' if ok else '✗'} {nom}" for nom, ok in criteres)
    return {"score": score, "sur": len(criteres), "seuil": reglage["seuil"],
            "motif": langues.t("serveur.evitable.motif", score=score, sur=len(criteres), detail=detail),
            "criteres": [{"nom": n, "ok": ok} for n, ok in criteres]}
