"""Commande `orch ligne` et rendu des refus de rangement, à l'usage de l'agent du client.

Rôle : `orch ligne <id> "<texte>"` ajoute une ligne (travail court, sans livrable ni branche propres) à une
tâche ; `--cocher N` coche ou décoche la ligne n° N (1 = la première) ; `rendre_rangement` dit à l'agent quoi
faire quand la création est refusée parce qu'un parent est plein ou qu'une autre nature s'y mélangerait.
Frontières : passe par l'API (`POST /api/taches/{id}/lignes[/basculer]`), rien d'importé du moteur ni du vault.
Invariants portés : INV-LIGNES-1, INV-PLAFOND-1, INV-NATURE-1.
"""

from __future__ import annotations

import os

COMMANDES = ("ligne",)


def ajouter(sous) -> None:
    li = sous.add_parser("ligne", help="ajouter une ligne (travail court, sans livrable ni branche propres) à une tâche")
    li.add_argument("id")
    li.add_argument("texte", nargs="?", default="", help="ce qui est fait ou à faire, en une ligne")
    li.add_argument("--document", default="", help="document lié (chemin ou lien)")
    li.add_argument("--fait", action="store_true", help="la ligne est déjà faite")
    li.add_argument("--cocher", type=int, default=0, help="cocher ou décocher la ligne n° N (1 = la première)")


def executer(a, appeler, quoter, source: str = "") -> list[str]:
    base = f"/taches/{quoter(a.id)}/lignes"
    if a.cocher:
        r = appeler("POST", f"{base}/basculer", {"index": a.cocher - 1})
    elif a.texte.strip():
        lien = os.path.abspath(a.document) if a.document else ""  # le serveur ne connaît pas le dossier courant
        r = appeler("POST", base, {"texte": a.texte, "lien": lien, "fait": a.fait})
    else:
        return ["texte attendu : orch ligne <id> \"<ce qui est fait ou à faire>\" (ou --cocher N)"]
    faites = sum(x["fait"] for x in r["lignes"])
    return [f"{a.id} : {len(r['lignes'])} ligne(s), {faites} faite(s)"]


def rendre_rangement(corps) -> str:
    """Refus 409 de rangement : les gestes proposés, en commandes."""
    rang = corps.get("rangement") if isinstance(corps, dict) else None
    if not rang:
        return ""
    raison = (f"{rang['ouvertes']} tâches ouvertes sous ce parent (plafond {rang['plafond']})"
              if rang["raison"] == "plafond" else "ce parent ne contient que des tâches d'une autre nature")
    lignes = [f"\nRangement demandé : {raison}."]
    for p in rang["propositions"]:
        if p["geste"] == "ligne":
            lignes.append(f"- travail court : orch ligne {p['tache']} \"<ce qui est fait>\"  (ligne de « {p['titre']} »)")
        elif p["geste"] == "sous_groupe":
            lignes.append(f"- ranger dans « {p['titre']} » : orch creer \"<titre>\" --parent {p['tache']} --description \"…\"")
        else:
            lignes.append(f"- nouveau regroupement « {p['titre']} » : orch creer \"{p['titre']}\" --description \"…\""
                          + (f" --parent {rang['parent']}" if rang.get("parent") else "")
                          + ", puis orch creer \"<titre>\" --parent <ce regroupement>")
    lignes.append("N'ajoute ici (--nouvelle) que si aucun de ces rangements ne convient.")
    return "\n".join(lignes)
