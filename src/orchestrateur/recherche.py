"""Recherche plein texte des tâches : titre, fiche, fil d'Ariane.

Rôle : trouver le voisinage d'une tâche (agents via `orch chercher`, interface).
Frontières : lit l'index en mémoire de `Vault` (fiche mise en cache avec le frontmatter) ;
aucune relecture de fichier, aucune écriture.
Invariants portés : aucun.
"""

from __future__ import annotations

import unicodedata

from . import temps
from .vault import Vault


def normaliser(texte: str) -> str:
    """Sans casse ni accents : « Échéance » et « echeance » se valent."""
    return "".join(c for c in unicodedata.normalize("NFKD", texte.casefold())
                   if not unicodedata.combining(c))


def _champs(fiche: dict) -> list[str]:
    return [fiche.get(k) or "" for k in ("situation", "fait", "reste", "prochain_pas")] + \
        [s.get("texte") or "" for s in fiche.get("sous_taches") or []]


def chercher(vault: Vault, q: str, limite: int = 20) -> list[dict]:
    mots = normaliser(q).split()
    if not mots:
        return []
    taches = vault.index()[0]
    parents = vault._parents(taches)
    trouves = []
    for k, t in taches.items():
        if t.pilotage:  # INV-PILOTAGE-1
            continue
        fil = vault.fil_ariane(k, parents)
        champs = _champs(t.fiche)
        if not all(m in normaliser(" ".join([t.titre, *fil, *champs])) for m in mots):
            continue
        extrait = next((c for c in champs if any(m in normaliser(c) for m in mots)),
                       t.fiche.get("situation") or "")
        dans_titre = all(m in normaliser(t.titre) for m in mots)
        trouves.append(((not vault.ouverte(t), not dans_titre, t.titre.casefold(), k),
                        {"id": k, "titre": t.titre, "statut": t.statut, "fil_ariane": fil,
                         "extrait": extrait[:200], **temps.vue(vault, t)}))
    trouves.sort(key=lambda x: x[0])
    return [r for _, r in trouves[:max(1, limite)]]
