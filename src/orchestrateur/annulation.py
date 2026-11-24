"""Annulation d'un geste de routine appliqué d'office (INV-PROP-1).

Rôle : relever, avant le geste, l'état qu'il va changer (`etat_avant`), puis le restaurer (`defaire`).
Frontières : appelé par `propositions` ; passe par les gestes du vault, jamais par une écriture directe ;
ne supprime rien (la tâche née d'un ticket est abandonnée, pas effacée).
Invariants portés : INV-PROP-1, INV-VAULT-1.
"""

from __future__ import annotations

from . import langues, liens, rattachement, temps
from .vault import Conflit

FERMEES = ("fait", "cloture", "abandonne")


def etat_avant(vault, p: dict) -> dict:
    """Ce qu'il faudra restaurer si l'utilisateur annule le geste."""
    t = vault.tache(p["tache"])
    if p["type"] == "deplacer":
        return {"conteneur": t.conteneur, "parent": t.parent_brut}
    if p["type"] == "renommer":
        return {"titre": t.titre}
    if p["type"] == "echeance":
        return {"echeance": str(t.fm.get("echeance") or "")}
    if p["type"] == "rattacher":
        return {"parents": {i: vault.tache(i).parent_brut or rattachement.RACINE for i in p.get("taches") or [p["tache"]]}}
    return {}


def defaire(moteur, p: dict) -> None:
    vault, tache, avant = moteur.vault, p["tache"], p.get("avant") or {}
    if p["type"] == "lier":
        sens, _, cible = str(p["valeur"]).partition(":")
        liens.delier(vault, tache, sens, cible.strip())
    elif p["type"] == "deplacer":
        vault.deplacer_conteneur(tache, avant["conteneur"])
        if avant.get("parent"):
            vault.deplacer_parent(tache, avant["parent"])
    elif p["type"] == "renommer":
        vault.renommer(tache, avant["titre"])
    elif p["type"] == "echeance":
        vault.poser_temps(tache, temps.valider(avant.get("echeance", ""), None))
    elif p["type"] == "rattacher":
        lots: dict[str, list[str]] = {}
        for ident, parent in (avant.get("parents") or {}).items():
            lots.setdefault(parent, []).append(ident)
        for parent, ids in lots.items():
            rattachement.appliquer(vault, moteur.config.rangement, moteur.occupation, ids, parent)
    elif p["type"] == "ticket":
        nees = [x for x in vault.index()[0].values()
                if x.parent_brut == tache and x.titre == p["valeur"] and x.statut not in FERMEES]
        if not nees:
            raise Conflit(langues.t("serveur.propositions.non_annulable", n=p["n"]))
        vault.poser_statut(nees[0].id, "abandonne", humain=True)
    else:
        raise Conflit(langues.t("serveur.propositions.non_annulable", n=p["n"]))
