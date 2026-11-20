"""Reprise d'un tour interrompu : automatique après un redémarrage du serveur, ou sur « Relancer ».

Rôle : persister le message de chaque tour actif (`<donnees>/etat/tours.json`) et la file des
messages pas encore démarrés (`file.json`) ; au démarrage, resoumettre chaque tour interrompu par
l'arrêt du serveur puis restaurer la file ; offrir le même geste à la main (`relancer`).
Frontières : aucun harnais lancé ici (tout passe par `Moteur.soumettre`) ; aucune écriture vault.
Invariants portés : INV-EXEC-1 (une reprise automatique par incident, jamais en boucle ; tâche
fermée jamais reprise), INV-EXEC-9 (la file survit à un redémarrage).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import fiches, langues
from .propositions import lire_liste
from .vault import Conflit, Invalide

log = logging.getLogger(__name__)

# Signé GoldenBrain (crochet initial) : l'interface ne l'attribue jamais à l'utilisateur.
MESSAGE_REPRISE = ("[GoldenBrain — reprise après interruption] Ton tour précédent a été "
                   "interrompu ({motif}) avant sa fin. Reprends ton travail là où tu en étais, "
                   "sans refaire ce qui est déjà fait, puis termine par ta fiche.")
CHAMPS = ("texte", "sauts", "de", "source", "mandat", "role", "reprise")
CHAMPS_FILE = ("texte", "sauts", "de", "harnais", "modele", "source", "mandat", "role", "reprise", "pour")
FICHIER_FILE = "file.json"


def enregistrement(ident: str, envoi) -> dict:
    """Ce qu'il faut garder d'un tour actif pour pouvoir le reprendre. INV-EXEC-1 : `reprise` n'est
    vrai que tant que le tour repris n'a rien produit ; après un signe de progrès, il redevient éligible."""
    rec = {"tache": ident, **{c: getattr(envoi, c) for c in CHAMPS}}
    rec["reprise"] = bool(envoi.reprise and not envoi.progres)
    return rec


def progres(moteur, ident: str, envoi) -> None:
    """INV-EXEC-1 : premier événement d'un tour repris d'office : la marque tombe sur disque."""
    if envoi.reprise and not envoi.progres:
        envoi.progres = True
        if ident in moteur.actifs:
            moteur.actifs[ident] = enregistrement(ident, envoi)
            moteur._sauver_actifs()


def lire_file(chemin: Path) -> list[dict]:
    return [x for x in lire_liste(chemin) if isinstance(x, dict) and isinstance(x.get("tache"), str)]


def sauver_file(moteur) -> None:
    """INV-EXEC-9 : messages en file, retenus par un prérequis compris, dans l'ordre de départ."""
    envois = []
    for ident in dict.fromkeys([*moteur.attente, *moteur.files]):
        attente = [moteur.attente[ident]] if ident in moteur.attente else []
        envois += [{"tache": ident, **{c: getattr(e, c) for c in CHAMPS_FILE}}
                   for e in [*attente, *moteur.files[ident]]]
    fiches.ecrire_atomique(moteur.fichier_tours.with_name(FICHIER_FILE), json.dumps(envois, ensure_ascii=False))


def restaurer_file(moteur) -> list[str]:
    """INV-EXEC-9 : remet en file, dans l'ordre, les messages que le dernier arrêt avait gardés."""
    restaures = []
    for rec in moteur.file_precedente:
        ident = rec["tache"]
        try:
            if not moteur.vault.ouverte(moteur.vault.tache(ident)) or not rec.get("texte"):
                continue  # tâche fermée ou disparue : rien à restaurer
            # `de` et `pour` ont déjà marqué le texte : on les repose sans repasser par la préparation.
            moteur.soumettre(ident, str(rec["texte"]), sauts=int(rec.get("sauts") or 0),
                             harnais=rec.get("harnais"), modele=rec.get("modele"),
                             source=str(rec.get("source") or ""), mandat=bool(rec.get("mandat")),
                             role=str(rec.get("role") or ""))
            e = moteur.files[ident][-1]
            e.de, e.pour, e.reprise = str(rec.get("de") or ""), str(rec.get("pour") or ""), bool(rec.get("reprise"))
            restaures.append(ident)
        except Exception as ex:  # un message refusé n'empêche pas les suivants
            log.warning("message en file de %s non restauré : %s", ident, ex)
    moteur.file_precedente = []
    return restaures


def charger(liste: list) -> dict[str, dict]:
    """`tours.json` -> {tâche: enregistrement} ; l'ancien format (liste d'identifiants) est lu."""
    out: dict[str, dict] = {}
    for x in liste:
        if isinstance(x, str):
            out[x] = {"tache": x}  # écrit par une version antérieure : message inconnu
        elif isinstance(x, dict) and isinstance(x.get("tache"), str):
            out[x["tache"]] = x
    return out


def _resoumettre(moteur, ident: str, motif: str, auto: bool) -> str:
    rec = moteur.interrompus.get(ident) or {"tache": ident}
    t = moteur.vault.tache(ident)
    session = str(t.fm.get("session") or "")
    role = str(rec.get("role") or "")
    if session and role in ("", "tache", "mandat"):
        # Même session du harnais : l'agent a déjà le contexte, un message de reprise suffit.
        # Le mandat éventuel reste en attente et sera traité par ce tour s'il réussit.
        etat = moteur.soumettre(ident, MESSAGE_REPRISE.format(motif=motif),
                                sauts=int(rec.get("sauts") or 0),
                                source=str(rec.get("de") or rec.get("source") or ""))
    elif rec.get("texte"):
        # Pas de session (premier tour) ou tour éphémère d'un rôle : le même message repart.
        etat = moteur.soumettre(ident, str(rec["texte"]), sauts=int(rec.get("sauts") or 0),
                                mandat=bool(rec.get("mandat")), role=role,
                                source=str(rec.get("de") or rec.get("source") or ""))
    else:
        raise Invalide(langues.t("serveur.reprise.rien_a_relancer"))
    # INV-EXEC-1 : tant qu'il n'a rien produit, un tour repris automatiquement ne l'est pas deux fois.
    moteur.files[ident][-1].reprise = auto
    moteur.interrompus.pop(ident, None)
    return etat


def reprendre_au_demarrage(moteur) -> list[str]:
    """Resoumet chaque tour interrompu par l'arrêt du serveur ; rend les tâches reprises."""
    reprises = []
    for ident, rec in list(moteur.interrompus.items()):
        try:
            if rec.get("reprise"):
                continue  # INV-EXEC-1 : repris sans avoir progressé (même incident) : geste humain
            if not moteur.vault.ouverte(moteur.vault.tache(ident)):
                continue  # tâche fermée entre-temps : rien à reprendre
            _resoumettre(moteur, ident, "redémarrage du serveur", auto=True)
            reprises.append(ident)
        except Exception as e:  # une tâche disparue ou invalide n'empêche pas les autres
            log.warning("reprise de %s impossible : %s", ident, e)
    restaurer_file(moteur)  # INV-EXEC-9 : après les tours repris, les messages qui attendaient leur tour
    return reprises


def relancer(moteur, ident: str) -> str:
    """Geste humain « Relancer » sur un tour interrompu."""
    if moteur.etat_de(ident) != "interrompu":
        raise Conflit(langues.t("serveur.reprise.aucun_interrompu"))
    return _resoumettre(moteur, ident, "arrêt ou redémarrage", auto=False)
