"""Commandes `orch reflexes` et `orch tracer`, à l'usage de l'agent du client.

Rôle : `reflexes` montre l'état du bloc de réflexes GoldenBrain dans les consignes de chaque assistant et, pour
l'un d'eux, le changement proposé (diff) ; avec `--accord` seulement, l'écrit (installer, mettre à jour,
retirer). `tracer` consigne dans la fiche d'une tâche ce qui a été fait et les documents créés ou modifiés.
Frontières : `reflexes` travaille sur le poste où tourne l'agent, sans serveur (`reflexes.py`) ; `tracer` passe
par l'API (`POST /api/taches/{id}/traces`). Rien n'est importé du moteur ni du vault.
Invariants portés : INV-REFLEXES-1 (sans `--accord`, rien n'est écrit), INV-TRACE-1.
"""

from __future__ import annotations

import os

COMMANDES = ("reflexes", "tracer")
HARNAIS = ("claude", "codex", "opencode", "agy", "copilot")  # = reflexes.CIBLES, sans l'importer à chaque appel
ETATS = {"absent": "absent", "a_jour": "à jour", "ancien": "ancienne version", "retouche": "retouché à la main"}


def ajouter(sous) -> None:
    rf = sous.add_parser("reflexes", help="réflexes GoldenBrain dans les consignes de l'agent : état, aperçu, "
                                          "installer ou retirer (avec --accord de l'utilisateur)")
    rf.add_argument("action", nargs="?", default="etat", choices=("etat", "apercu", "installer", "retirer"))
    rf.add_argument("--harnais", choices=HARNAIS)
    rf.add_argument("--dossier", help="consignes d'un projet (ce dossier) plutôt que les consignes globales")
    rf.add_argument("--langue", default="fr", help="langue de l'utilisateur : fr, en, de, es")
    rf.add_argument("--accord", action="store_true", help="l'utilisateur a vu l'aperçu et accepté")
    tr = sous.add_parser("tracer", help="consigner dans la fiche d'une tâche ce qui a été fait et ses documents")
    tr.add_argument("id")
    tr.add_argument("texte", help="ce qui a été fait, ou le résultat")
    tr.add_argument("--document", action="append", default=[], help="fichier créé ou modifié (répétable)")


def _reflexes(a) -> list[str]:
    from . import reflexes  # import tardif : la commande des agents reste légère
    if a.action == "etat":
        sortie = [f"bloc de réflexes GoldenBrain, version {reflexes.VERSION}"]
        for x in reflexes.releve(a.langue, None, a.dossier):
            v = f" v{x['version']}" if x["version"] else ""
            sortie.append(f"- {x['id']} ({x['libelle']}){'' if x['present'] else ' — non installé'} : "
                          f"{ETATS[x['etat']]}{v} — {x['fichier']}")
        sortie.append("aperçu : orch reflexes apercu --harnais <id> ; écrire : orch reflexes installer "
                      "--harnais <id> --accord (après l'accord de l'utilisateur)")
        return sortie
    if not a.harnais:
        return [f"--harnais attendu : {', '.join(HARNAIS)}"]
    chemin = reflexes.fichier(a.harnais, a.dossier)
    action = "retirer" if a.action == "retirer" else "installer"
    if a.action == "apercu" or not a.accord:
        diff = reflexes.apercu(chemin, action, a.langue)
        entete = [] if a.action == "apercu" else [
            "rien n'est écrit sans --accord : montre ce changement à ton utilisateur ; s'il accepte, relance avec --accord"]
        return entete + [diff or f"aucun changement : {chemin}"]
    change = reflexes.appliquer(chemin, action, a.langue)
    return [f"{chemin} : {('bloc retiré' if action == 'retirer' else 'bloc posé') if change else 'déjà à jour'}"]


def executer(a, appeler, quoter, source: str = "") -> list[str]:
    if a.commande == "reflexes":
        return _reflexes(a)
    docs = [os.path.abspath(d) for d in a.document]  # le serveur ne connaît pas le dossier courant de l'agent
    r = appeler("POST", f"/taches/{quoter(a.id)}/traces", {"texte": a.texte, "documents": docs})
    return [f"tracé dans {r.get('id', a.id)} ({len(docs)} document(s))"]

