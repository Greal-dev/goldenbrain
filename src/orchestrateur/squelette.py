"""Vault de départ : les dossiers d'un second cerveau et sa note « Lisez-moi », proposés à un vault vide.

Rôle : dire si le vault est vide (aucune note Markdown hors dossiers cachés), lister ce qui manquerait
(dossiers de premier niveau, `Lisez-moi.md`) et, après validation de l'accueil, le créer en ajout.
Frontières : ne propose rien à un vault qui porte déjà des notes (un vault Obsidian se reprend en place,
tel quel) ; ne modifie jamais un fichier existant ; appelé par `accueil` (proposition) et
`accueil_ecriture` (écriture après validation).
Invariants portés : INV-ACCUEIL-5 (vault de départ proposé au seul vault vide, écrit en ajout après validation).
"""

from __future__ import annotations

import os
from pathlib import Path

from . import fiches

LISEZ_MOI = "Lisez-moi.md"


def dossiers(cfg) -> list[str]:
    """Dossiers de premier niveau d'un second cerveau : rôles, projets, arrivée, ressources, archives."""
    return [cfg.casquettes, cfg.projets, "Inbox", "Ressources", "Archives"]


def vide(racine: Path, arrivee: str = "") -> bool:
    """Vrai si la racine n'existe pas ou ne porte aucune note `.md` (dossiers cachés et dossier d'arrivée exclus).

    Le dossier d'arrivée (`[vault] arrivee`) reçoit les tâches que GoldenBrain crée lui-même (démonstration des
    premiers pas, manager) : sans cette exclusion, la démonstration privait l'arrivant du vault de départ (recette 20/11).
    """
    if not racine.is_dir():
        return True
    for d, noms, fichiers in os.walk(racine):
        noms[:] = [n for n in noms if not n.startswith(".") and not (arrivee and Path(d) == racine and n == arrivee)]
        if any(f.endswith(".md") for f in fichiers):
            return False
    return True


def obsidian(racine: Path) -> bool:
    return (racine / ".obsidian").is_dir()


def propose(vault) -> dict | None:
    """Ce que le vault de départ ajouterait ; None si le vault porte déjà des notes. N'écrit rien."""
    racine = vault.racine
    if not vide(racine, vault.cfg.arrivee):
        return None
    return {"dossiers": [d for d in dossiers(vault.cfg) if not (racine / d).is_dir()],
            "notes": [LISEZ_MOI] if not (racine / LISEZ_MOI).exists() else []}


def creer(vault) -> dict:
    """INV-ACCUEIL-5 : crée ce qui manque, seulement si le vault est encore vide ; rien n'est récrit."""
    faits = {"dossiers": 0, "notes": 0}
    if (p := propose(vault)) is None:
        return faits
    for d in p["dossiers"]:
        (vault.racine / d).mkdir(parents=True, exist_ok=True)
        faits["dossiers"] += 1
    cible = vault.racine / LISEZ_MOI
    vault.racine.mkdir(parents=True, exist_ok=True)
    if p["notes"] and not cible.exists():
        fiches.ecrire_atomique(cible, texte(vault.cfg))
        faits["notes"] += 1
    return faits


def texte(cfg) -> str:
    return f"""---
type: note
titre: Lisez-moi
source: accueil
tags: [accueil]
---

# Lisez-moi — votre second cerveau

Ce dossier est votre **second cerveau** : un ensemble de notes ordinaires (fichiers Markdown) que vous
lisez et modifiez dans GoldenBrain, ou dans tout autre éditeur (Obsidian, par exemple). Rien n'est
enfermé : ce sont vos fichiers.

## La méthode en une phrase

**Rôles → projets → tâches** : chaque tâche vit dans un projet, chaque projet sert un de vos grands rôles.

## Les dossiers

- **{cfg.casquettes}/** : vos grands rôles (« casquettes ») — travail, famille, association… Chaque rôle
  porte ses projets, et un projet peut se regrouper avec d'autres dans une opération.
- **{cfg.projets}/** : les projets qui naissent d'une tâche devenue trop grosse.
- **Inbox/** : la boîte d'arrivée. Tout ce qui arrive vite (idée, lien, photo) s'y dépose sans réfléchir ;
  on range plus tard.
- **Ressources/** : ce qui sert à plusieurs projets (fiches pratiques, modèles, contacts, documentation).
- **Archives/** : ce qui est fini ou en sommeil. On n'y efface rien, on y range.

## Ce que contient un projet

- **contexte.md** : la fiche du projet — son objectif, ses repères, et les consignes pour l'IA.
  L'IA la lit **avant chaque tâche** du projet : plus elle est juste, meilleures sont les réponses.
- **taches/** : une note par tâche confiée à l'IA ou à vous-même.
- **notes/** : les notes de connaissance du projet.

## Relier les notes

Écrivez `[[Nom d'une note]]` pour lier deux notes. GoldenBrain affiche les liens entrants, les mentions
non liées et le graphe des notes ; le jardinier IA propose des liens et des rangements, sans jamais rien
écrire sans votre accord.

## Bonnes pratiques

1. **Capturer vite, ranger plus tard** : en cas de doute, Inbox/.
2. **Une tâche = un résultat attendu** (« Rédiger le courrier à la mairie »), pas un thème.
3. **Tenir contexte.md à jour** : deux ou trois lignes suffisent.
4. **Archiver plutôt que supprimer.**

Le guide complet : dans GoldenBrain, bouton « ? » puis « Organiser votre second cerveau ».
"""
