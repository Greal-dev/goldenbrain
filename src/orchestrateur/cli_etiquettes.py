"""Commandes `orch etiqueter` et `orch etiquettes`, et rendu des étiquettes dans `orch lire` / `orch arbre`.

Rôle : poser ou retirer des étiquettes libres sur une tâche (`orch etiqueter <id> +mot -mot`), lister les
étiquettes existantes avec leur consigne (`orch etiquettes`), dire à l'agent quelles étiquettes porte sa tâche, quelles
consignes les accompagnent et quelles autres tâches les partagent.
Frontières : passe par l'API (`POST /api/taches/{id}/etiquettes`, `GET /api/etiquettes`) ; rien du moteur.
Invariants portés : INV-ETIQUETTE-2 (un agent ne crée pas d'étiquette : refus renvoyé par le serveur, avec la
marche à suivre `orch proposer etiquette`).
"""

from __future__ import annotations

from .cli_erreurs import ErreurCli

COMMANDES = ("etiqueter", "etiquettes")


def ajouter(sous) -> None:
    e = sous.add_parser("etiqueter", help="poser (+mot) ou retirer (-mot) des étiquettes d'une tâche ; un agent ne crée "
                                          "pas d'étiquette : il en pose une existante ou la propose (proposer etiquette)")
    e.add_argument("id")
    e.add_argument("changements", nargs="+", metavar="+mot|-mot")
    sous.add_parser("etiquettes", help="étiquettes existantes, leur usage et leur consigne pour l'IA")


def executer(a, appeler, quoter, source: str = "") -> list[str]:
    if a.commande == "etiquettes":
        liste = appeler("GET", "/etiquettes")["etiquettes"]
        return [f"#{x['mot']} ({x['n']} tâche(s))" + (f" — consigne : {x['consigne']}" if x["consigne"] else "")
                for x in liste] or ["(aucune étiquette)"]
    ajouts, retraits = [], []
    for c in a.changements:
        if c[:1] not in "+-" or len(c) < 2:
            raise ErreurCli(f"« {c} » : écrire +mot pour poser, -mot pour retirer (orch etiqueter <id> +client -urgent)")
        (ajouts if c[0] == "+" else retraits).append(c[1:])
    r = appeler("POST", f"/taches/{quoter(a.id)}/etiquettes", {"ajouter": ajouts, "retirer": retraits})
    return [f"{a.id} : " + (" ".join(f"#{m}" for m in r["etiquettes"]) or "(aucune étiquette)")]


def rendre(t: dict) -> list[str]:
    """Lignes de `orch lire` : étiquettes, consignes, tâches qui partagent une étiquette."""
    if not t.get("etiquettes"):
        return []
    lignes = ["", "## Étiquettes", " ".join(f"#{m}" for m in t["etiquettes"])]
    for m, c in (t.get("consignes_etiquettes") or {}).items():
        lignes.append(f"consigne de #{m} (à respecter) : {c}")
    if t.get("liees_etiquette"):
        lignes.append("autres tâches qui partagent une étiquette (lis leur fiche avant d'agir sur ce périmètre ; "
                      "tes liens vont de préférence vers elles) :")
        lignes += [f"- {x['id']} [{x['statut'] or '?'}] {x['titre']}" + (f" — {x['situation']}" if x["situation"] else "")
                   + f" ({' '.join('#' + m for m in x['etiquettes'])})" for x in t["liees_etiquette"]]
    return lignes
