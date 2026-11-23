"""Rattachement d'un lot de tâches sous une tâche parente : garde-fous communs à la proposition et à son exécution.

Rôle : décider si `taches` peuvent passer sous `parent` (ou revenir à la racine de leur projet, `RACINE`), refuser
sinon avec une phrase lisible, puis appliquer le geste. Même contrôle à la proposition et à l'acceptation : l'arbre
a pu bouger entre les deux.
Frontières : pas de HTTP ; n'écrit que la clé `parent` des fiches, jamais de déplacement de dossier.
Invariants portés : INV-RATTACHER-1, INV-PLAFOND-1, INV-NATURE-1, INV-VERROU-1.
"""

from __future__ import annotations

from . import langues, rangement
from .vault import Conflit, Invalide

RACINE = "racine"  # valeur de proposition : détacher, la tâche revient à la racine de son projet


def normaliser(taches: list[str]) -> list[str]:
    ids = list(dict.fromkeys(str(x).strip() for x in taches if str(x).strip()))
    if not ids:
        raise Invalide(langues.t("serveur.rattacher.aucune_tache"))
    return ids


def verifier(vault, cfg, occupation, taches: list[str], parent: str) -> list[str]:
    """Rend les identifiants à rattacher (déjà en place : ignorés) ou lève `Invalide` / `Conflit`.
    `occupation(id)` dit si un agent travaille la tâche (INV-VERROU-1)."""
    ids = normaliser(taches)
    index = vault.index()[0]
    cibles = [vault.tache(i) for i in ids]  # NonTrouve si inconnue
    for t in cibles:
        if occupation(t.id):  # une tâche en cours d'exécution ne change pas de place sous ses pieds
            raise Conflit(langues.t("serveur.rattacher.occupee", tache=t.titre))
    if parent == RACINE:
        return [t.id for t in cibles if t.parent_brut]
    mere = vault.tache(parent)
    for t in cibles:
        if t.id == mere.id or mere.id in vault.descendance(t.id):  # cycle : le parent descendrait de la tâche
            raise Conflit(langues.t("serveur.rattacher.cycle", tache=t.titre, parent=mere.titre))
        if t.conteneur != mere.conteneur:  # le routage suit le projet : déplacer d'abord, rattacher ensuite
            raise Conflit(langues.t("serveur.rattacher.autre_projet", tache=t.titre, parent=mere.titre))
    parents = vault._parents(index)
    nouveaux = [t for t in cibles if parents[t.id] != mere.id]
    if not nouveaux:
        return []
    freres = rangement._freres(vault, mere.id, None)
    arrivent = [t for t in nouveaux if vault.ouverte(t) and not t.pilotage]
    if len(freres) + len(arrivent) > cfg.plafond:  # INV-PLAFOND-1
        raise Conflit(langues.t("serveur.rattacher.plafond", parent=mere.titre, plafond=cfg.plafond,
                                ouvertes=len(freres), arrivent=len(arrivent)))
    if cfg.natures_separees:  # INV-NATURE-1
        lot = {rangement.nature_de(t) for t in arrivent} - {""}
        base = {rangement.nature_de(t) for t in freres} - {""}
        if len(lot) > 1 or (len(freres) >= 2 and len(base) == 1 and lot - base):
            raise Conflit(langues.t("serveur.rattacher.natures", parent=mere.titre))
    return [t.id for t in nouveaux]


def appliquer(vault, cfg, occupation, taches: list[str], parent: str) -> int:
    """Rattache (ou détache) le lot ; rend le nombre de tâches déplacées. Tout est contrôlé avant la première écriture."""
    ids = verifier(vault, cfg, occupation, taches, parent)
    for i in ids:
        vault.modifier(i, {"parent": None if parent == RACINE else parent})
    return len(ids)
