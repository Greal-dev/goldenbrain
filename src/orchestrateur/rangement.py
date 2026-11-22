"""Rangement de l'arbre : natures de tâches (développement, opération, pilotage) et plafond par parent.

Rôle : déduire la nature d'une tâche (clé `genre`), compter les tâches ouvertes directement sous un parent
(tâche ou projet), proposer à la création de ranger plutôt qu'empiler (ligne d'une tâche existante, sous-groupe,
nouveau regroupement), lister les parents en excès pour le jardinier.
Frontières : lecture seule de l'index ; aucune écriture ici (la création et la clé `genre` sont posées par
`api_rapprochement.creer` et `api_lignes`) ; la ressemblance vient de `rapprochement` (INV-RAPPROCHEMENT-1).
Invariants portés : INV-PLAFOND-1, INV-NATURE-1.
"""

from __future__ import annotations

from . import langues
from .config_rangement import ConfigRangement

NATURES = ("developpement", "operation", "pilotage")
# Préfixes de mots normalisés qui révèlent la nature ; le titre pèse deux fois la description.
INDICES = {
    "developpement": ("code", "branche", "bug", "test", "api", "interface", "ecran", "module", "integr", "refactor",
                      "implement", "endpoint", "migrat", "script", "commit", "fusion", "porte", "installat",
                      "dictionnaire", "traduction", "css", "fonction", "perform", "serveur", "depot", "commande",
                      "reglage", "optimis", "architect", "harnais", "langue", "guide", "mise en page", "agent"),
    "operation": ("mail", "courriel", "compte", "routine", "demarche", "relanc", "envoy", "contact", "appel",
                  "inscri", "factur", "paiement", "rendez", "telephone", "carte", "bancaire", "sauvegarde",
                  "import", "quittance", "livraison", "recette", "veille", "suivre", "suivi", "mettre a jour",
                  "mise a jour", "reparer", "changer", "chiffrer", "nettoy"),
    "pilotage": ("strateg", "communic", "nom", "nommer", "licence", "decision", "decid", "diffusion", "commerc",
                 "post", "linkedin", "positionn", "offre", "prix", "roadmap", "vision", "orientation", "arbitr",
                 "choisir", "marque", "webinaire", "conference", "tarif", "audit", "revue", "publi"),
}


def deduire(titre: str, description: str = "") -> str:
    """Nature la plus indiquée par le titre et la description ; vide en l'absence d'indice net (jamais devinée)."""
    from .recherche import normaliser  # import tardif : `recherche` importe `vault`, qui importe ce module
    scores = dict.fromkeys(NATURES, 0)
    for poids, texte in ((2, titre), (1, description)):
        norme = f" {normaliser(texte or '')} "
        for nature, indices in INDICES.items():
            scores[nature] += poids * sum(f" {i}" in norme for i in indices)
    best = max(scores.values())
    gagnantes = [n for n, v in scores.items() if v == best]
    return gagnantes[0] if best > 0 and len(gagnantes) == 1 else ""


def valide(genre: str | None) -> str:
    """`genre` posé, vide s'il est inconnu."""
    g = str(genre or "").strip().lower()
    return g if g in NATURES else ""


def nature_de(t) -> str:
    """Nature posée dans la fiche, sinon déduite du titre (une tâche ancienne en a donc une, non écrite)."""
    return valide(t.fm.get("genre")) or deduire(t.titre)


def libelle(nature: str) -> str:
    return langues.t(f"serveur.rangement.nature_{nature}") if nature in NATURES else ""


def _freres(vault, parent: str | None, conteneur: str | None) -> list:
    """Tâches ouvertes (hors pilotage) directement sous `parent`, ou à la racine du projet `conteneur`."""
    taches = vault.index()[0]
    parents = vault._parents(taches)
    return [t for k, t in taches.items()
            if not t.pilotage and vault.ouverte(t)
            and (parents[k] == parent if parent else parents[k] is None and t.conteneur == conteneur)]


def _cible(vault, parent: str | None, conteneur: str | None):
    """(parent, conteneur) effectifs ; (None, None) quand rien ne se range (arrivée : on y trie, on n'y range pas)."""
    if parent:
        return parent, None
    cont = conteneur or vault.cfg.arrivee
    return (None, None) if cont == vault.cfg.arrivee else (None, cont)


def propositions(vault, cfg: ConfigRangement, titre: str, description: str = "", conteneur: str | None = None,
                 parent: str | None = None, genre: str = "") -> dict | None:
    """Friction de rangement à la création, ou None. `raison` : `plafond` (parent plein, INV-PLAFOND-1) ou
    `nature` (un parent d'une seule nature recevrait une autre, INV-NATURE-1)."""
    from . import rapprochement  # import tardif (cycle `vault`)
    p, c = _cible(vault, parent, conteneur)
    if p is None and c is None:
        return None
    freres = _freres(vault, p, c)
    plein = len(freres) >= cfg.plafond
    natures = {nature_de(t) for t in freres} - {""}
    melange = bool(cfg.natures_separees and genre and len(freres) >= 2 and len(natures) == 1 and genre not in natures)
    if not plein and not melange:
        return None
    ids = {t.id for t in freres}
    taches = vault.index()[0]
    props = []
    if p:  # le travail est peut-être une simple ligne de la tâche mère
        props.append({"geste": "ligne", "tache": p, "titre": taches[p].titre})
    proches = rapprochement.proches(vault, titre, description, conteneur, exclure=(p,), limite=50)
    props += [{"geste": "ligne", "tache": x["id"], "titre": x["titre"]}
              for x in proches if x["id"] in ids and x["ouverte"]][:3]
    parents = vault._parents(taches)
    avec_enfants = {k for k, q in parents.items() if q in ids}
    props += [{"geste": "sous_groupe", "tache": t.id, "titre": t.titre} for t in freres
              if t.id in avec_enfants and genre and nature_de(t) == genre][:2]
    nom_parent = taches[p].titre if p else vault.conteneur(c).titre
    props.append({"geste": "nouveau_groupe", "titre": f"{libelle(genre) or langues.t('serveur.rangement.groupe')} — {nom_parent}"})
    return {"raison": "plafond" if plein else "nature", "plafond": cfg.plafond, "ouvertes": len(freres),
            "genre": genre, "parent": p, "conteneur": c, "propositions": props}


def excedents(vault, cfg: ConfigRangement) -> list[dict]:
    """Parents (tâches et projets) au-dessus du plafond, du plus chargé au moins chargé : matière du jardinier."""
    taches = vault.index()[0]
    parents = vault._parents(taches)
    groupes: dict[tuple, list] = {}
    for k, t in taches.items():
        if t.pilotage or not vault.ouverte(t):
            continue
        cle = ("t", parents[k]) if parents[k] else ("c", t.conteneur)
        groupes.setdefault(cle, []).append(t)
    sortie = []
    for (genre_cle, ident), liste in groupes.items():
        if len(liste) <= cfg.plafond or ident == vault.cfg.arrivee:
            continue
        titre = taches[ident].titre if genre_cle == "t" else ident
        sortie.append({"id": ident, "titre": titre, "ouvertes": len(liste),
                       "natures": sorted({nature_de(t) for t in liste} - {""})})
    return sorted(sortie, key=lambda e: -e["ouvertes"])
