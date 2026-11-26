"""Propositions d'agent : persistance et gestes d'acceptation (INV-EXEC-5).

Rôle : stocker les propositions (`etat/propositions.json`), les créer, les trancher et, sur
acceptation, appeler la fonction du geste humain correspondant.
Frontières : mélangé au `Moteur` (dont il emprunte vault, publier, soumettre, creer, deriver) ;
pas de HTTP.
Invariants portés : INV-EXEC-5 (une proposition n'est exécutée que sur geste humain), INV-RAPPROCHEMENT-1,
INV-PLAFOND-1 et INV-INTEG-2 (une tâche ou un ticket accepté passe les mêmes gardes que `orch creer`),
INV-LIEN-2 (un lien `alimente` vers une tâche permanente est posé d'office), INV-PROP-1 (gestes de
routine appliqués d'office, tracés et annulables), INV-LIGNES-1 (la tâche proposée par un agent devient une ligne de sa tâche).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from . import annulation, depot, etiquettes, fiches, langues, liens, lignes, rangement, rapprochement, rattachement, temps, transformations
from .vault import Conflit, Invalide, NonTrouve, exiger_description, titre_valide

TYPES_PROPOSITION = ("deplacer", "ticket", "projet", "lier", "operation", "tache", "perimetre", "echeance", "fermer",
                     "renommer", "rattacher", "etiquette")
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
        self.en_cours: set[int] = set()  # C8 : propositions dont l'acceptation (asynchrone) est en train de s'appliquer
        for p in self.liste:  # propositions d'avant le lot 2 : pas de motif
            if isinstance(p, dict):
                p.setdefault("motif", "")

    def sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.liste, ensure_ascii=False, indent=1))

    def reserver(self, n: int) -> None:
        """C8 : un second « accepter » pendant l'application du premier est refusé (409), pas rejoué."""
        if n in self.en_cours:
            raise Conflit(langues.t("serveur.propositions.en_cours", n=n))
        self.en_cours.add(n)

    def liberer(self, n: int) -> None:
        self.en_cours.discard(n)

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
        if type_ == "etiquette":  # INV-ETIQUETTE-2 : l'agent propose, l'utilisateur accepte
            valeur = etiquettes.normaliser(valeur)
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
        if type_ == "lier":  # B7 : refus à la création, pas à l'acceptation
            if self.vault.tache(_lien_propose(valeur)[1]).id == t.id:
                raise Conflit(langues.t("serveur.propositions.auto_lien"))
            self._borner_lien(t, self.vault.tache(_lien_propose(valeur)[1]))  # INV-ETIQUETTE-3
        if q := next((q for q in self.propositions.liste if q["etat"] == "en_attente" and q["type"] == type_
                      and q["tache"] == tache and q["valeur"] == valeur
                      and (q.get("taches") or []) == ((annexe or {}).get("taches") or [])), None):
            return {"type": type_, "tache": tache, "valeur": valeur, "etat": "deja_proposee", "n": q["n"]}
        if self._deja_fait(type_, tache, valeur, (annexe or {}).get("taches")):  # rien à décider : on ne dépose pas
            return {"type": type_, "tache": tache, "valeur": valeur, "etat": "deja_fait"}
        permanent = type_ == "lier" and self._lien_de_routine(valeur)  # INV-LIEN-2
        jardin = getattr(self, "jardinier", None)  # INV-JARD-2 : plafond par passage, jamais d'office
        montrer = not permanent and ((jardin is not None and jardin.admettre(de)) or montrer)
        if type_ == "tache" and de and not montrer and de in self.vault.index()[0]:
            # INV-LIGNES-1 : la suite d'un agent est une ligne de sa tâche, pas une tâche à trancher.
            texte = valeur if not motif.strip() else f"{valeur} — {' '.join(motif.split())}"
            lignes.ajouter(self.vault, de, texte[:lignes.LONGUEUR], auteur="ia")
            self.publier("arbre")
            return {"type": type_, "tache": de, "valeur": valeur, "etat": "ligne"}
        # INV-PROP-1 : un geste de routine (réversible) est appliqué d'office ; INV-SCAN-1 : une préconisation
        # du scan (`montrer`) attend toujours le geste humain.
        routine = permanent or (not montrer and type_ in self.config.interface.gestes_office())
        politique = "accepter" if routine else "montrer" if montrer else self.config.interface.politique()
        if politique == "ignorer":  # INV-INTERFACE-3 : ignorée en silence, rien n'est mémorisé
            return {"type": type_, "tache": tache, "valeur": valeur, "etat": "ignoree"}
        n = max((p["n"] for p in self.propositions.liste), default=0) + 1
        p = {"n": n, "type": type_, "tache": tache, "titre_tache": t.titre, "valeur": valeur,
             "de": de or "", "motif": " ".join((motif or "").split()), "etat": "en_attente",
             "cree": maintenant(), **({"auto": True} if routine else {}), **(annexe or {})}
        self.propositions.liste.append(p)
        self.propositions.sauver()
        self.publier("proposition", n=n)
        if politique != "accepter":
            return p
        if not routine:
            return self.trancher(n, True)
        p["avant"] = annulation.etat_avant(self.vault, p)
        try:
            p = self.trancher(n, True)
        except (Conflit, Invalide, NonTrouve) as e:  # le geste d'office échoue : il attend la décision humaine
            p.pop("auto", None)
            p["echec"] = str(e)
            self.propositions.sauver()
            return p
        self.vault.consigner(tache, "Traces", f"- {dt.datetime.now():%Y-%m-%d %H:%M} — "
                             + langues.t("serveur.propositions.geste_d_office", n=n, geste=f"{type_} {valeur}"))
        return p

    def annuler(self, n: int) -> dict:
        """INV-PROP-1 : défait un geste appliqué d'office (journal « Appliqué d'office » de Décisions)."""
        p = self.propositions.get(n)
        if not p.get("auto") or p["etat"] != "acceptee":
            raise Conflit(langues.t("serveur.propositions.non_annulable", n=n))
        annulation.defaire(self, p)
        p["etat"] = "annulee"
        self.propositions.sauver()
        self.vault.consigner(p["tache"], "Traces", f"- {dt.datetime.now():%Y-%m-%d %H:%M} — "
                             + langues.t("serveur.propositions.geste_annule", n=n, geste=f"{p['type']} {p['valeur']}"))
        self.publier("proposition", n=n)
        self.publier("arbre")
        return p

    def _lien_de_routine(self, valeur: str) -> bool:
        """INV-LIEN-2 : un lien « alimente » vers une tâche permanente (l'intégration) est un geste de
        routine : posé d'office, jamais mis en attente. Les autres liens suivent la politique."""
        type_, cible = _lien_propose(valeur)
        try:
            return type_ == "alimente" and str(self.vault.tache(cible).fm.get("nature") or "") == "permanente"
        except NonTrouve:
            return False

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
        if accepter and self._deja_fait(p["type"], p["tache"], p["valeur"], p.get("taches")):
            p["deja_fait"] = True  # geste déjà réalisé entre-temps : acceptée, sans erreur, mention discrète
        elif accepter:  # une exception laisse la proposition en attente (INV-EXEC-5)
            self._executer(p["type"], p["tache"], p["valeur"], p["motif"], p.get("taches"))
        return self.conclure(p, accepter)

    def _gardes_creation(self, titre: str, description: str, conteneur: str, parent: str | None, origine: str) -> str:
        """C7 : une tâche ou un ticket accepté passe les gardes de `orch creer` : doublon (INV-RAPPROCHEMENT-1),
        plafond et nature (INV-PLAFOND-1, INV-NATURE-1). Le geste humain tranche la proposition, pas ces refus :
        l'acceptation échoue (409) et la proposition reste en attente. Rend la nature déduite."""
        cands = rapprochement.proches(self.vault, titre, description, conteneur, exclure=(origine,))
        if rapprochement.forte(cands):
            raise Conflit(langues.t("serveur.propositions.doublon", titre=titre,
                                    proches=", ".join(c["id"] for c in cands[:3])))
        genre = rangement.deduire(titre, description)
        if rang := rangement.propositions(self.vault, self.config.rangement, titre, description, conteneur, parent, genre):
            raise Conflit(langues.t(f"serveur.api_rapprochement.rangement_{rang['raison']}",
                                    ouvertes=rang["ouvertes"], plafond=rang["plafond"]))
        return genre

    def _apres_creation(self, ident: str, genre: str | None) -> None:
        if genre:
            self.vault.modifier(ident, {"genre": genre})
        liens.relier_integration(self.vault, ident)  # INV-INTEG-2 : sans lien, la branche livrée n'est jamais intégrée

    def _borner_lien(self, a, b) -> None:
        """INV-ETIQUETTE-3 : une étiquette borne le périmètre ; la tâche d'intégration du projet reste liable."""
        if not etiquettes.borne(a.fm, b.fm):
            return
        try:
            if depot.integration(self.vault, a.id) == b.id:
                return
        except (Invalide, NonTrouve):
            pass
        mots = lambda t: ", ".join(f"#{m}" for m in etiquettes.de(t.fm)) or "—"  # noqa: E731
        raise Conflit(langues.t("serveur.etiquettes.lien_borne", a=a.titre, mots_a=mots(a), b=b.titre, mots_b=mots(b)))

    def _deja_fait(self, type_: str, tache: str, valeur: str, taches: list | None = None) -> bool:
        """INV-DEJAFAIT-1 : l'effet de la proposition est-il déjà en place ? (lien présent, déjà rattachée, au bon endroit, déjà ce titre ou ce statut)"""
        try:
            t = self.vault.tache(tache)
            if type_ == "lier":
                return liens.existe(self.vault, tache, *_lien_propose(valeur))
            if type_ == "rattacher":
                return rattachement.deja(self.vault, taches or [tache], valeur)
            if type_ == "deplacer":
                return t.conteneur == valeur and not t.parent_brut
            if type_ == "renommer":
                return t.titre == valeur
            if type_ == "etiquette":
                return valeur in etiquettes.de(t.fm)
            return type_ == "fermer" and t.statut == valeur
        except (NonTrouve, Invalide):
            return False  # le geste lui-même dira pourquoi il échoue

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
            conteneur = self.vault.tache(tache).conteneur
            genre = self._gardes_creation(valeur, motif, conteneur, tache, tache)  # C7
            ident = self.deriver(tache, valeur, "enfant", avec_fil, description=motif)
            self._apres_creation(ident, genre)
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
        elif type_ == "etiquette":  # geste humain : l'étiquette n'existe qu'une fois acceptée
            self.etiquettes.declarer(valeur)
            etiquettes.appliquer(self.vault, tache, [valeur])
        elif type_ == "rattacher":  # INV-RATTACHER-1 : tout le lot ou rien, recontrôlé à l'acceptation
            rattachement.appliquer(self.vault, self.config.rangement, self.occupation, taches or [tache], valeur)
        elif type_ == "tache":
            conteneur = self.vault.tache(tache).conteneur
            genre = self._gardes_creation(valeur, motif, conteneur, None, tache)  # C7 : elle naît à la racine du projet
            ident = self.creer(valeur, motif, conteneur=conteneur)
            liens.lier(self.vault, ident, "voir_aussi", tache)
            self._apres_creation(ident, genre)
        else:  # perimetre
            self.soumettre(tache, f"[Périmètre révisé, validé par l'utilisateur] {valeur}")


def _lien_propose(valeur: str) -> tuple[str, str]:
    type_, _, cible = valeur.partition(":")
    if type_ not in liens.TYPES or not cible.strip():
        raise Invalide(langues.t("serveur.propositions.valeur_lien"))
    return type_, cible.strip()
