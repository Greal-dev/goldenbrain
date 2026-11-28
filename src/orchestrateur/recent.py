"""Étiquette automatique « recent » : les tâches que l'utilisateur vient de créer ou de reprendre.

Rôle : poser et retirer l'étiquette `recent` (affichée « Récent ») à la place de l'utilisateur, pour que la vue
`#etiquette=recent` rassemble le travail suivi, par opposition aux tâches moins urgentes ou en attente.
Frontières : écrit par `etiquettes.appliquer` / `Vault.modifier` seulement (INV-VAULT-1) ; ne lance aucun tour ;
l'entrée par HTTP passe par `apres` (appelé par la garde de `api.py`), la création par `api_rapprochement.creer`,
la réouverture et la sortie par `Vault.poser_statut` (`pour_statut`).
Invariants portés : INV-RECENT-1 (entrée sur geste humain seulement, sortie à la clôture ou au bouton « Non prioritaire »).
"""

from __future__ import annotations

import logging
import re

from . import etiquettes
from .api_executeurs import ENTETE
from .vault import ErreurOrch

log = logging.getLogger(__name__)
MOT = "recent"
# Reprises humaines : message, relance, reprise immédiate, renvoi, complément demandé à la place d'une création.
GESTES = re.compile(r"^/api/(?:taches/([^/]+)/(?:messages|relancer|reprise|renvoyer)|rapprochement/taches/([^/]+)/completer)$")


def entrer(vault, ident: str) -> None:
    """Pose `recent` sur une tâche (hors conversation de conteneur). Jamais bloquant : le geste de l'utilisateur a déjà abouti."""
    try:
        if not vault.tache(ident).pilotage:
            etiquettes.appliquer(vault, ident, [MOT])
    except ErreurOrch as e:
        log.warning("étiquette %s non posée sur %s : %s", MOT, ident, e)


def pour_statut(fm: dict, etait_ouverte: bool, devient_ouverte: bool, humain: bool) -> dict:
    """Clés à écrire avec un changement de statut : retrait à la clôture, retour d'un humain qui rouvre une tâche close."""
    mots = etiquettes.de(fm)
    if not devient_ouverte:
        return {etiquettes.CLE: [m for m in mots if m != MOT] or None} if MOT in mots else {}
    if humain and not etait_ouverte and MOT not in mots and len(mots) < etiquettes.MAX_PAR_TACHE:
        return {etiquettes.CLE: [*mots, MOT]}
    return {}


def compter(vault) -> int:
    return sum(1 for t in vault.index()[0].values() if not t.pilotage and MOT in etiquettes.de(t.fm))


def apres(moteur, request, statut_http: int) -> None:
    """Chemin unique des reprises HTTP : appelé après chaque requête ; sans effet pour un agent (`X-Orch-Tache`, jeton d'exécuteur)."""
    if request.method != "POST" or statut_http >= 300 or request.headers.get("x-orch-tache") or request.headers.get(ENTETE):
        return
    if m := GESTES.match(request.url.path):
        entrer(moteur.vault, m.group(1) or m.group(2))
        moteur.publier("arbre")
