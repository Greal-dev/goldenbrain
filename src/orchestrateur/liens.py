"""Liens fonctionnels entre tâches : `alimente` (orienté), `prerequis` (orienté, bloquant) et
`voir_aussi` (symétrique).

Rôle : lire les deux clés (tolérant), calculer « alimenté par » et les voisins, contrôler et
écrire un lien, compter les liens d'un nœud de l'arbre.
Frontières : n'écrit que par `Vault.modifier` (clés gérées, INV-VAULT-1) ; ne lance aucun tour.
Invariants portés : INV-VAULT-1 (liste en ligne, clé retirée si vide), INV-LIEN-1 (fournit au
moteur les tâches alimentées), INV-ORDO-1 (`prerequis` stocké côté tâche qui attend ; aucun
cycle de prérequis), INV-INTEG-2 (lien d'office vers la tâche d'intégration du projet).
"""

from __future__ import annotations

from . import depot, langues
from .vault import Conflit, Invalide, NonTrouve, Tache, Vault, nettoyer_lien

TYPES = ("alimente", "prerequis", "voir_aussi")


def ids(fm: dict, cle: str) -> list[str]:
    """Identifiants d'une clé de lien, sans doublon ; orphelins compris (ils restent au fichier)."""
    plats, pile = [], [fm.get(cle)]
    while pile:
        # `[[[a]], [[b]]]` en YAML en ligne donne des listes imbriquées : on aplatit.
        x = pile.pop(0)
        if isinstance(x, list):
            pile[:0] = x
        else:
            plats.append(x)
    sortie = []
    for x in plats:
        if (i := nettoyer_lien(str(x) if isinstance(x, (int, float)) else x)) and i not in sortie:
            sortie.append(i)
    return sortie


def graphe(taches: dict[str, Tache]) -> tuple[dict, dict, dict]:
    """(aval, amont, voisins) : listes d'identifiants existants, sans soi ni doublon."""
    aval: dict[str, list] = {}
    amont: dict[str, list] = {}
    voisins: dict[str, list] = {}

    def ajouter(d: dict, a: str, b: str) -> None:
        if b not in (lst := d.setdefault(a, [])):
            lst.append(b)

    for k, t in taches.items():
        for c in ids(t.fm, "alimente"):
            if c in taches and c != k:
                ajouter(aval, k, c)
                ajouter(amont, c, k)
        for c in ids(t.fm, "voir_aussi"):
            if c in taches and c != k:
                ajouter(voisins, k, c)
                ajouter(voisins, c, k)
    return aval, amont, voisins


def prerequis(taches: dict[str, Tache]) -> tuple[dict, dict]:
    """(requiert, requis_par) : `B: prerequis: [A]` = B ne démarre pas avant la fin de A."""
    requiert: dict[str, list] = {}
    requis_par: dict[str, list] = {}
    for k, t in taches.items():
        for c in ids(t.fm, "prerequis"):
            if c in taches and c != k:
                requiert.setdefault(k, []).append(c)
                requis_par.setdefault(c, []).append(k)
    return requiert, requis_par


def refs(taches: dict[str, Tache], ident: str) -> dict:
    aval, amont, voisins = graphe(taches)
    requiert, requis_par = prerequis(taches)

    def ref(k: str) -> dict:
        return {"id": k, "titre": taches[k].titre, "statut": taches[k].statut}

    return {"alimente": [ref(k) for k in aval.get(ident, [])],
            "alimente_par": [ref(k) for k in amont.get(ident, [])],
            "prerequis": [ref(k) for k in requiert.get(ident, [])],
            "requis_par": [ref(k) for k in requis_par.get(ident, [])],
            "voir_aussi": [ref(k) for k in voisins.get(ident, [])]}


def annoter(noeuds: list[dict], taches: dict[str, Tache]) -> list[dict]:
    """Pose `liens` (nombre total) sur chaque nœud de tâche de l'arbre."""
    graphes = (*graphe(taches), prerequis(taches)[0])

    def parcourir(ns: list[dict]) -> None:
        for n in ns:
            if n["type"] == "tache":
                n["liens"] = sum(len(g.get(n["id"], [])) for g in graphes)
            parcourir(n["enfants"])

    parcourir(noeuds)
    return noeuds


def _atteint(aval: dict, depart: str, but: str) -> bool:
    vus, pile = set(), [depart]
    while pile:
        if (k := pile.pop()) == but:
            return True
        if k not in vus:
            vus.add(k)
            pile += aval.get(k, [])
    return False


def _type(type_: str) -> str:
    if type_ not in TYPES:
        raise Invalide(langues.t("serveur.liens.type_attendu", types=", ".join(TYPES)))
    return type_


def existe(vault: Vault, ident: str, type_: str, cible: str) -> bool:
    """Le lien est-il déjà posé (pour `voir_aussi`, de l'un ou l'autre côté) ?"""
    _type(type_)
    t = vault.tache(ident)
    return cible in ids(t.fm, type_) or (type_ == "voir_aussi" and cible in graphe(vault.index()[0])[2].get(ident, []))


def lier(vault: Vault, ident: str, type_: str, cible: str) -> None:
    _type(type_)
    t = vault.tache(ident)
    vault.tache(cible)
    if cible == ident:
        raise Conflit(langues.t("serveur.liens.a_elle_meme"))
    aval, _, voisins = graphe(vault.index()[0])
    deja = ids(t.fm, type_)
    if cible in deja or (type_ == "voir_aussi" and cible in voisins.get(ident, [])):
        raise Conflit(langues.t("serveur.liens.deja_present", ident=ident, type=type_, cible=cible))
    if type_ == "alimente" and _atteint(aval, cible, ident):
        raise Conflit(langues.t("serveur.liens.cycle_alimente", cible=cible, ident=ident))
    if type_ == "prerequis" and _atteint(prerequis(taches := vault.index()[0])[0], cible, ident):
        # INV-ORDO-1 : deux tâches qui s'attendent ne démarreraient jamais.
        raise Conflit(langues.t("serveur.liens.cycle_prerequis", cible=taches[cible].titre, ident=taches[ident].titre))
    vault.modifier(ident, {type_: [*deja, cible]})


def delier(vault: Vault, ident: str, type_: str, cible: str) -> None:
    _type(type_)
    vault.tache(ident)
    taches = vault.index()[0]
    sens = [(ident, cible)]
    if type_ == "voir_aussi":  # symétrique : retiré quel que soit le côté qui le stocke
        sens.append((cible, ident))
    for source, autre in sens:
        if (t := taches.get(source)) and autre in (deja := ids(t.fm, type_)):
            # INV-VAULT-1 : clé retirée quand la liste devient vide.
            vault.modifier(source, {type_: [x for x in deja if x != autre] or None})
            return
    raise NonTrouve(langues.t("serveur.liens.inexistant", ident=ident, type=type_, cible=cible))


def alimentees(taches: dict[str, Tache], ident: str) -> list[str]:
    return graphe(taches)[0].get(ident, [])


def relier_integration(vault: Vault, ident: str) -> str | None:
    """INV-INTEG-2 : une tâche créée dans un projet qui déclare sa tâche d'intégration l'alimente
    d'office, sans quoi la branche livrée n'est jamais intégrée. Sauf l'intégration elle-même et
    l'enfant d'une tâche qui l'alimente déjà (sa parente porte le lien ; un message par tour suffit).
    Un lien impossible (cible absente, cycle) n'empêche jamais la création."""
    try:
        cible = depot.integration(vault, ident)
        t = vault.tache(ident)
        parent = t.parent_brut or ""
        if not cible or cible == ident or (parent and (parent == cible or cible in ids(vault.tache(parent).fm, "alimente"))):
            return None
        lier(vault, ident, "alimente", cible)
    except (Conflit, NonTrouve, Invalide):
        return None
    return cible
