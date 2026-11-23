"""Commande `orch chaine`, à l'usage de l'agent d'une phase de chaîne.

Rôle : montrer le plan de la chaîne de la tâche courante (`orch chaine`) et l'ajuster au dossier réel : sauter,
ajouter, dédoubler une phase à venir, ou réécrire sa consigne, toujours avec un motif.
Frontières : passe par l'API (`/api/chaines/...`) ; rien n'est importé du moteur ni du vault.
Invariants portés : INV-CHAINE-3 (motif obligatoire, ajustement journalisé côté serveur).
"""

from __future__ import annotations

from .cli_erreurs import ErreurCli

COMMANDES = ("chaine",)


def ajouter(sous) -> None:
    ch = sous.add_parser("chaine", help="plan de la chaîne de la tâche courante ; l'ajuster : sauter, ajouter, "
                                        "dedoubler une phase à venir, ou changer sa consigne (avec --motif)")
    ch.add_argument("action", nargs="?", default="plan", choices=("plan", "sauter", "ajouter", "dedoubler", "consigne"))
    ch.add_argument("valeurs", nargs="*", help="sauter <n> | ajouter <titre> <consigne> | dedoubler <n> | "
                                               "consigne <n> <texte>")
    ch.add_argument("--apres", default="", help="ajouter : numéro de la phase après laquelle insérer")
    ch.add_argument("--motif", default="", help="pourquoi le dossier réel le justifie (obligatoire pour ajuster)")
    ch.add_argument("--tache", default="", help="tâche de la chaîne (défaut : ORCH_TACHE)")


def _ligne(p: dict) -> str:
    marque = {"faite": "x", "en_cours": ">", "sautee": "-", "echec": "!"}.get(p["etat"], " ")
    return f"[{marque}] {p['num']}. {p['titre']} ({p['tache']}){' — validation humaine après' if p['validation'] else ''}"


def executer(a, appeler, quoter, source: str) -> list[str]:
    tache = a.tache or source
    if not tache:
        raise ErreurCli("ORCH_TACHE absent : précise --tache <id>")  # B11 : code 1
    if a.action == "plan":
        r = appeler("GET", f"/chaines/executions/{quoter(tache)}")
    else:
        v = list(a.valeurs)
        corps = {"de": tache, "action": a.action, "motif": a.motif}
        if a.action == "ajouter":
            corps |= {"n": a.apres, "titre": v[0] if v else "", "consigne": v[1] if len(v) > 1 else ""}
        else:
            corps |= {"n": v[0] if v else "", "consigne": v[1] if len(v) > 1 else ""}
        r = appeler("POST", "/chaines/ajuster", corps)
    return [f"chaîne « {r['titre']} » ({r['id']}) — {r['etat']}"] + [_ligne(p) for p in r["phases"]]
