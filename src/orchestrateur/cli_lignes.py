"""Commande `orch ligne` et rendu des refus de rangement, à l'usage de l'agent du client.

Rôle : `orch ligne <id> "<texte>"` ajoute une ligne (travail court, sans livrable ni branche propres) à une
tâche ; `--cocher N` s'assure que la ligne n° N est faite, `--decocher N` qu'elle ne l'est pas (1 = la première ; idempotents) ; `rendre_rangement` dit à l'agent quoi
faire quand la création est refusée parce qu'un parent est plein ou qu'une autre nature s'y mélangerait.
Frontières : passe par l'API (`POST /api/taches/{id}/lignes[/basculer]`, `POST /api/taches/{id}/livrables[/attendre]`), rien d'importé du moteur ni du vault.
Invariants portés : INV-LIGNES-1, INV-PLAFOND-1, INV-NATURE-1.
"""

from __future__ import annotations

import os

from .cli_erreurs import ErreurCli

COMMANDES = ("ligne", "livrable")


def ajouter(sous) -> None:
    li = sous.add_parser("ligne", help="ajouter une ligne (travail court, sans livrable ni branche propres) à une tâche")
    li.add_argument("id")
    li.add_argument("texte", nargs="?", default="", help="ce qui est fait ou à faire, en une ligne")
    li.add_argument("--document", default="", help="document lié (chemin ou lien)")
    li.add_argument("--fait", action="store_true", help="la ligne est déjà faite")
    li.add_argument("--cocher", type=int, default=0, help="s'assurer que la ligne n° N est faite (1 = la première)")
    li.add_argument("--decocher", type=int, default=0, help="s'assurer que la ligne n° N n'est pas faite")
    lv = sous.add_parser("livrable", help="déclarer un livrable (document, fichier, adresse, branche, commit) d'une tâche, "
                                          "ou en annoncer un attendu")
    lv.add_argument("id")
    lv.add_argument("cible", nargs="?", default="", help="chemin, adresse http(s), branche:<nom>, commit:<sha> ou publie:<adresse>")
    lv.add_argument("--titre", default="", help="nom lisible (sinon déduit de la cible)")
    lv.add_argument("--type", default="", choices=("", "note", "fichier", "url", "publie", "branche", "commit"))
    lv.add_argument("--attendu", default="", metavar="TITRE", help="annoncer un livrable attendu, à produire plus tard")


def _livrable(a, appeler, quoter) -> list[str]:
    base = f"/taches/{quoter(a.id)}/livrables"
    if a.attendu.strip():
        appeler("POST", f"{base}/attendre", {"titre": a.attendu})
        return [f"{a.id} : livrable attendu annoncé « {a.attendu.strip()} »"]
    if not a.cible.strip():
        raise ErreurCli("cible attendue : orch livrable <id> <chemin|adresse|branche:x|commit:sha> [--titre …] (ou --attendu \"titre\")")
    cible = a.cible
    if not cible.lower().startswith(("http://", "https://", "publie:", "branche:", "commit:")) and os.path.exists(cible):
        cible = os.path.abspath(cible)  # le serveur ne connaît pas le dossier courant
    r = appeler("POST", base, {"cible": cible, "titre": a.titre, "type": a.type})
    return [f"{a.id} : {r['total']} livrable(s)"]


def executer(a, appeler, quoter, source: str = "") -> list[str]:
    if getattr(a, "commande", "") == "livrable":
        return _livrable(a, appeler, quoter)
    base = f"/taches/{quoter(a.id)}/lignes"
    if a.cocher or a.decocher:  # B12 : idempotent (on lit l'état, on ne bascule que si nécessaire) ; le texte n'est pas ignoré
        if a.texte.strip() or (a.cocher and a.decocher):
            raise ErreurCli("--cocher / --decocher ne se combinent ni avec un texte ni entre eux : "
                            "une ligne s'ajoute (orch ligne <id> \"<texte>\") ou se coche, pas les deux")
        n, voulu = (a.cocher, True) if a.cocher else (a.decocher, False)
        lignes = appeler("GET", f"/taches/{quoter(a.id)}")["fiche"]["lignes"]
        if not 1 <= n <= len(lignes):
            raise ErreurCli(f"ligne n° {n} introuvable : {a.id} en compte {len(lignes)}")
        r = {"lignes": lignes}
        if bool(lignes[n - 1]["fait"]) != voulu:
            r = appeler("POST", f"{base}/basculer", {"index": n - 1})
    elif a.texte.strip():
        lien = os.path.abspath(a.document) if a.document else ""  # le serveur ne connaît pas le dossier courant
        r = appeler("POST", base, {"texte": a.texte, "lien": lien, "fait": a.fait})
    else:
        raise ErreurCli("texte attendu : orch ligne <id> \"<ce qui est fait ou à faire>\" (ou --cocher N)")  # B11
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
    lignes.append("Ne passe outre (--hors-rangement) que si aucun de ces rangements ne convient.")  # B3
    return "\n".join(lignes)
