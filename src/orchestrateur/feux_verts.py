"""Feu vert lié à une version : demande, verdict du contrôleur, vérification par sha exact.

Rôle : registre des demandes de feu vert (une par sha), verdict du contrôleur désigné, trace
horodatée dans la fiche de la tâche demandeuse, message à l'autre partie.
Persistance : `<donnees>/etat/feux-verts.json` (registre interrogé par `verifier`) ; la trace
lisible vit dans le vault, section « Feux verts » du corps de la tâche demandeuse.
Frontières : n'exécute ni fusion ni déploiement ; ce sont les scripts d'un dépôt qui appellent
`orch feu-vert verifier <sha>` et s'arrêtent sur un code non nul.
Invariants portés : INV-FEU-1 (accordé seulement pour ce sha exact, par le contrôleur désigné),
INV-MSG-1 (messages soumis au plafond de sauts), INV-VAULT-1 (écriture par `Vault.consigner`).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

from . import fiches, langues
from .vault import Conflit, ErreurOrch, Invalide, NonTrouve

log = logging.getLogger(__name__)


class Interdit(ErreurOrch):
    code = 403


SHA = re.compile(r"[0-9a-f]{40}")
VERDICTS = {"accorder": "accorde", "refuser": "refuse"}
LIBELLES = {"en_attente": "feu vert demandé", "accorde": "feu vert ACCORDÉ",
            "refuse": "feu vert REFUSÉ"}


def sha_valide(sha: str) -> str:
    """INV-FEU-1 : un sha complet (40 hex) ; un préfixe rendrait « ce sha exact » ambigu."""
    sha = (sha or "").strip().lower()
    if not SHA.fullmatch(sha):
        raise Invalide(langues.t("serveur.feux_verts.sha_attendu"))
    return sha


def _maintenant() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class FeuxVerts:
    def __init__(self, moteur):
        self.m = moteur
        self.chemin = moteur.config.donnees / "etat" / "feux-verts.json"
        try:
            self.registre: dict[str, dict] = json.loads(fiches.lire(self.chemin))
        except (OSError, ValueError):
            self.registre = {}

    def _sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps(self.registre, ensure_ascii=False,
                                                       indent=1))

    def _tracer(self, f: dict, auteur: str, quand: str) -> None:
        texte = f["motif"] if f["etat"] != "en_attente" else f["objet"]
        ligne = (f"- {quand.replace('T', ' ')} — {LIBELLES[f['etat']]} pour `{f['sha']}` "
                 f"par {auteur} (contrôleur : {f['controleur']}) : {texte}")
        self.m.vault.consigner(f["demandeur"], "Feux verts", ligne)
        self.m.publier("arbre")

    def lire(self, sha: str) -> dict:
        sha = sha_valide(sha)
        if sha not in self.registre:
            raise NonTrouve(langues.t("serveur.feux_verts.aucune_demande", sha=sha))
        return self.registre[sha]

    def demander(self, sha: str, objet: str, controleur: str, de: str, sauts: int = 0) -> dict:
        sha = sha_valide(sha)
        if not de:
            raise Invalide(langues.t("serveur.feux_verts.sans_demandeur"))
        if not objet.strip():
            raise Invalide(langues.t("serveur.feux_verts.objet_vide"))
        if controleur == de:
            raise Conflit(langues.t("serveur.feux_verts.propre_feu"))
        demandeur, ctrl = self.m.vault.tache(de), self.m.vault.tache(controleur)
        if self.registre.get(sha, {}).get("etat") == "accorde":
            raise Conflit(langues.t("serveur.feux_verts.deja_accorde", sha=sha))
        quand = _maintenant()
        message = (f"[Demande de feu vert de la tâche « {demandeur.titre} » ({de})]\n"
                   f"Version : {sha}\nObjet : {objet.strip()}\n"
                   f"Réponds par `orch feu-vert accorder {sha} \"<motif>\"` ou "
                   f"`orch feu-vert refuser {sha} \"<motif>\"`.")
        self.m.soumettre(ctrl.id, message, de, sauts)  # INV-MSG-1
        f = {"sha": sha, "objet": " ".join(objet.split()), "demandeur": de,
             "controleur": ctrl.id, "etat": "en_attente", "motif": "", "demande_le": quand,
             "verdict_le": "", "auteur": ""}
        self.registre[sha] = f
        self._sauver()
        self._tracer(f, de, quand)
        return f

    def trancher(self, sha: str, geste: str, motif: str, de: str, sauts: int = 0) -> dict:
        f = self.lire(sha)
        if geste not in VERDICTS:
            raise Invalide(langues.t("serveur.feux_verts.verdict_inconnu", geste=geste))
        if de != f["controleur"]:  # INV-FEU-1 : seul le contrôleur désigné tranche.
            raise Interdit(langues.t("serveur.feux_verts.controleur_seul", controleur=f["controleur"]))
        if f["etat"] != "en_attente":
            raise Conflit(langues.t("serveur.feux_verts.deja_tranche", etat=f["etat"]))
        if not motif.strip():
            raise Invalide(langues.t("serveur.feux_verts.motif_vide"))
        quand = _maintenant()
        f.update(etat=VERDICTS[geste], motif=" ".join(motif.split()), verdict_le=quand, auteur=de)
        self._sauver()
        self._tracer(f, de, quand)
        try:
            self.m.soumettre(f["demandeur"], f"[{LIBELLES[f['etat']]} pour {f['sha']} par {de}]"
                             f"\nMotif : {f['motif']}", de, sauts)
        except (Conflit, Invalide, NonTrouve) as e:  # le verdict reste consigné
            log.warning("verdict de feu vert non transmis à %s : %s", f["demandeur"], e)
        return f

    def accorde(self, sha: str) -> bool:
        """INV-FEU-1 : vrai seulement pour un feu vert accordé à ce sha exact."""
        return self.registre.get(sha_valide(sha), {}).get("etat") == "accorde"
