"""Instantané du compagnon mobile : une projection en lecture seule, à liste blanche, de l'essentiel.

Rôle : réunir en un seul document léger (arbre, décisions en attente, travaux en cours) ce que
l'application du téléphone affiche et peut garder hors ligne ; en calculer l'empreinte (ETag).
Frontières : lecture seule, aucune écriture vault ; ne lit que ce que les modules `vault`,
`decisions` et `api_travaux` rendent déjà ; aucun HTTP (route : `api_compagnon`).
Invariants portés : INV-COMPAGNON-1 (liste blanche de champs posée ICI, côté serveur : ni corps de
fiche, ni conversation, ni note, ni chemin, ni jeton ne figurent dans l'instantané ; taille bornée).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from . import api_travaux, decisions

NOEUDS_MAX = 800            # au-delà, l'arbre est tronqué (et `tronque` le dit)
DECISIONS_MAX = 50
QUESTION_MAX = 160
RESUME_MAX = 140   # résumé du résultat d'une tâche à valider : seulement si [distant] resume (INV-COMPAGNON-1)
GENRES = ("reponse", "validation", "echeance")   # les décisions d'une tâche ; ni agents ni préconisations
CHAMPS_NOEUD = ("id", "type", "titre", "statut", "etat_execution", "a_valider", "echeance", "priorite", "retard", "ouvertes")
TTL_S = 7 * 86400           # durée de vie du stockage local, comptée depuis `genere`


def _court(texte, n: int) -> str:
    texte = " ".join(str(texte or "").split())
    return texte if len(texte) <= n else texte[: n - 1].rstrip() + "…"


def _arbre(moteur) -> tuple[list[dict], bool]:
    plat: list[dict] = []

    def descendre(noeuds, parent):
        for n in noeuds:
            if len(plat) >= NOEUDS_MAX:
                return True
            plat.append({"parent": parent, **{k: n[k] for k in CHAMPS_NOEUD if k in n}})
            if descendre(n.get("enfants") or [], f"{n['type']}:{n['id']}"):
                return True
        return False

    tronque = descendre(moteur.vault.arbre(False, moteur.etat_de), None)
    return plat, tronque


def _decisions(moteur, resume: bool = False) -> list[dict]:
    lignes = [lg for lg in decisions.rassembler(moteur)["decisions"] if lg["genre"] in GENRES][:DECISIONS_MAX]
    sortie = [{"id": lg["id"], "genre": lg["genre"], "libelle": lg["libelle"], "tache": lg["tache"], "titre": lg["titre"],
               "projet": lg["projet"], "question": _court(lg["question"], QUESTION_MAX),
               "echeance": lg["echeance"], "retard": lg["retard"]} for lg in lignes]
    if resume:   # champ absent (et non vide) quand le réglage est éteint : rien ne sort du poste
        for s, lg in zip(sortie, lignes):
            if lg["genre"] == "validation" and lg.get("fait"):
                s["resume"] = _court(lg["fait"], RESUME_MAX)
    return sortie


def _travaux(moteur) -> dict:
    t = api_travaux.travaux(moteur)
    return {"tours": [{"tache": x["tache"], "titre": x["titre"], "projet": x["projet"], "depuis": x.get("depuis")}
                      for x in t["tours"]],
            "en_file": len(t["file"])}


def instantane(moteur, resume: bool = False) -> dict:
    """Le contenu de l'instantané, sans horodatage (l'empreinte n'en dépend donc pas)."""
    noeuds, tronque = _arbre(moteur)
    return {"arbre": noeuds, "tronque": tronque, "decisions": _decisions(moteur, resume), "travaux": _travaux(moteur)}


def empreinte(contenu: dict) -> str:
    brut = json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:32]


def horodatage() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
