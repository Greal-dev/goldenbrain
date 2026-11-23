"""Propositions d'agent : persistance et gestes d'acceptation (INV-EXEC-5).

Rôle : stocker les propositions (`etat/propositions.json`), les créer, les trancher et, sur
acceptation, appeler la fonction du geste humain correspondant.
Frontières : mélangé au `Moteur` (dont il emprunte vault, publier, soumettre, creer, deriver) ;
pas de HTTP.
Invariants portés : INV-EXEC-5 (une proposition n'est exécutée que sur geste humain).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from . import fiches, langues, liens, rattachement, temps, transformations
from .vault import Conflit, Invalide, NonTrouve, exiger_description, titre_valide

TYPES_PROPOSITION = ("deplacer", "ticket", "projet", "lier", "operation", "tache", "perimetre", "echeance", "fermer",
                     "renommer", "rattacher")
FERMETURES = ("cloture", "abandonne")  # statuts qu'une proposition « fermer » peut poser
log = logging.getLogger(__name__)


def maintenant() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def lire_liste(chemin: Path) -> list:
    # Un fichier d'état absent ou corrompu ne doit jamais empêcher le serveur de démarrer.
    try:
        liste = json.loads(chemin.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(liste, list):
        log.warning("état ignoré (pas une liste) : %s", chemin)
        return []
    return liste


class Propositions:
    """Propositions d'agent, persistées dans `etat/propositions.json`."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.liste: list[dict] = lire_liste(chemin)
        for p in self.liste:  # propositions d'avant le lot 2 : pas de motif
            if isinstance(p, dict):
                p.setdefault("motif", "")

    def sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.liste, ensure_ascii=False, indent=1))

    def get(self, n: int) -> dict:
        try:
            return next(p for p in self.liste if p["n"] == n)
        except StopIteration:
            raise NonTrouve(langues.t("serveur.propositions.inconnue", n=n)) from None


class MixinPropositions:
    """Gestes de proposition du moteur."""

    def proposer(self, type_: str, tache: str, valeur: str, de: str = "", motif: str = "",
                 montrer: bool = False, annexe: dict | None = None) -> dict:
        if type_ not in TYPES_PROPOSITION:
            raise Invalide(langues.t("serveur.propositions.type_inconnu", type=type_))
        if not valeur or not str(valeur).strip():
            raise Invalide(langues.t("serveur.propositions.valeur_requise"))
        if type_ == "lier":
            _lien_propose(valeur)
        if type_ == "echeance":
            temps.valider(str(valeur).strip(), None)  # refus immédiat d'une date illisible
            valeur = str(valeur).strip()
        if type_ in ("tache", "ticket"):  # l'agent dit de quoi il s'agit : le motif devient la description
            motif = exiger_description(motif, langues.t("serveur.propositions.objet", type=type_))
        if type_ == "fermer":
            valeur = str(valeur).strip()
            if valeur not in FERMETURES:
                raise Invalide(langues.t("serveur.propositions.valeur_fermer", valeurs=", ".join(FERMETURES)))
        if type_ == "renommer":  # INV-RENOMMER-2 : titre actuel -> titre proposé, motif obligatoire
            valeur = titre_valide(valeur)
            if valeur == self.vault.tache(tache).titre:
                raise Invalide(langues.t("serveur.propositions.titre_identique"))
            if not " ".join(str(motif or "").split()):
                raise Invalide(langues.t("serveur.propositions.motif_renommer"))
        if type_ == "deplacer":
            valeur = self._conteneur_canonique(str(valeur).strip())
        if type_ == "rattacher":  # INV-RATTACHER-1 : refus immédiat, mêmes garde-fous qu'à l'acceptation
            valeur = str(valeur).strip()
            ids = rattachement.normaliser([tache, *((annexe or {}).get("taches") or [])])
            rattachement.verifier(self.vault, self.config.rangement, self.occupation, ids, valeur)
            tache = ids[0]
            annexe = {**(annexe or {}), "taches": ids, "titres": [self.vault.tache(i).titre for i in ids]}
        t = self.vault.tache(tache)
        jardin = getattr(self, "jardinier", None)  # INV-JARD-2 : plafond par passage, jamais d'office
        montrer = (jardin is not None and jardin.admettre(de)) or montrer
        # INV-SCAN-1 : une préconisation du scan (`montrer`) attend toujours le geste humain.
        politique = "montrer" if montrer else self.config.interface.politique()
        if politique == "ignorer":  # INV-INTERFACE-3 : ignorée en silence, rien n'est mémorisé
            return {"type": type_, "tache": tache, "valeur": valeur, "etat": "ignoree"}
        n = max((p["n"] for p in self.propositions.liste), default=0) + 1
        p = {"n": n, "type": type_, "tache": tache, "titre_tache": t.titre, "valeur": valeur,
             "de": de or "", "motif": " ".join((motif or "").split()), "etat": "en_attente",
             "cree": maintenant(), **(annexe or {})}
        self.propositions.liste.append(p)
        self.propositions.sauver()
        self.publier("proposition", n=n)
        return self.trancher(n, True) if politique == "accepter" else p

    def _conteneur_canonique(self, valeur: str) -> str:
        # Les agents citent souvent le seul nom du dossier (« META-Cognitive-System ») : on
        # le ramène à l'identifiant du conteneur, ou on refuse tout de suite avec des pistes
        # plutôt que de laisser une proposition inacceptable (revue réelle du 13/11).
        conteneurs = self.vault.index()[1]
        if valeur in conteneurs:
            return valeur
        nom = valeur.rstrip("/").rsplit("/", 1)[-1].casefold()
        proches = [c for c in conteneurs if c.rsplit("/", 1)[-1].casefold() == nom]
        if len(proches) == 1:
            return proches[0]
        pistes = proches or sorted(c for c in conteneurs if nom[:6] in c.casefold())[:5]
        if pistes:
            raise Invalide(langues.t("serveur.propositions.conteneur_pistes", valeur=valeur, pistes=", ".join(pistes)))
        raise Invalide(langues.t("serveur.propositions.conteneur_inconnu", valeur=valeur))

    def trancher(self, n: int, accepter: bool) -> dict:
        p = self.propositions.get(n)
        if p["etat"] != "en_attente":
            raise Conflit(langues.t("serveur.propositions.deja_acceptee") if p["etat"] == "acceptee"
                          else langues.t("serveur.propositions.deja_refusee"))
        if accepter:  # une exception laisse la proposition en attente (INV-EXEC-5)
            self._executer(p["type"], p["tache"], p["valeur"], p["motif"], p.get("taches"))
        return self.conclure(p, accepter)

    def conclure(self, p: dict, accepter: bool) -> dict:
        """Marque la proposition tranchée (après l'exécution du geste, pour une acceptation)."""
        p["etat"] = "acceptee" if accepter else "refusee"
        self.propositions.sauver()
        self.publier("proposition", n=p["n"])
        self.publier("arbre")
        return p

    def _executer(self, type_: str, tache: str, valeur: str, motif: str = "", taches: list | None = None) -> None:
        # INV-EXEC-5 : chaque acceptation appelle la fonction du geste humain correspondant.
        if type_ == "deplacer":
            self.vault.deplacer_conteneur(tache, valeur)
        elif type_ == "ticket":
            avec_fil = bool(self.vault.tache(tache).fm.get("session"))
            self.deriver(tache, valeur, "enfant", avec_fil, description=motif)
        elif type_ == "projet":
            transformations.promouvoir(self, tache, valeur, decouper=True)
        elif type_ == "lier":
            liens.lier(self.vault, tache, *_lien_propose(valeur))
        elif type_ == "operation":
            # INV-ARBRE-2 : le geste déplace le dossier (plan + verrou) ; l'API s'en charge.
            raise Conflit(langues.t("serveur.propositions.operation_par_api"))
        elif type_ == "echeance":
            self.vault.poser_temps(tache, temps.valider(valeur, None))
        elif type_ == "fermer":  # geste humain : le statut ne change que sur acceptation
            self.vault.poser_statut(tache, valeur, humain=True)
        elif type_ == "renommer":  # geste humain : le titre ne change que sur acceptation
            self.vault.renommer(tache, valeur)
        elif type_ == "rattacher":  # INV-RATTACHER-1 : tout le lot ou rien, recontrôlé à l'acceptation
            rattachement.appliquer(self.vault, self.config.rangement, self.occupation, taches or [tache], valeur)
        elif type_ == "tache":
            conteneur = self.vault.tache(tache).conteneur
            liens.lier(self.vault, self.creer(valeur, motif, conteneur=conteneur), "voir_aussi", tache)
        else:  # perimetre
            self.soumettre(tache, f"[Périmètre révisé, validé par l'utilisateur] {valeur}")


def _lien_propose(valeur: str) -> tuple[str, str]:
    type_, _, cible = valeur.partition(":")
    if type_ not in liens.TYPES or not cible.strip():
        raise Invalide(langues.t("serveur.propositions.valeur_lien"))
    return type_, cible.strip()
