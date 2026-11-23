"""Commandes locales de `orch` qui n'appellent pas le serveur : `natif`, `m365`, `agents-cc` (rendu).

Rôle : sortir de `cli.py` (plafond de 500 lignes) ce qui n'emploie pas `appeler`.
Frontières : stdlib seule ; `m365` importé tard ; n'importe ni le moteur ni le vault.
Invariants portés : INV-NATIF-1, INV-M365-1, INV-M365-3.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def natif(fichier: str) -> int:
    """INV-NATIF-1 : écrit son PID (que GoldenBrain surveille) puis exécute le harnais au premier
    plan de l'onglet ; sa fin, onglet fermé compris, est la fermeture de l'interface native."""
    spec = json.loads(open(fichier, encoding="utf-8").read())
    with open(os.path.splitext(fichier)[0] + ".pid", "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    env = {**os.environ, **spec.get("env", {})}
    if spec.get("argv"):
        return subprocess.run(spec["argv"], cwd=spec.get("dossier"), env=env).returncode
    return subprocess.run(spec["commande"], cwd=spec.get("dossier"), env=env,
                          shell=True).returncode


def _m365(a) -> int:
    """Appel direct à Microsoft 365, sans le serveur GoldenBrain (INV-M365-1, INV-M365-3)."""
    from . import m365  # import tardif : la commande ne charge le connecteur que si on l'emploie
    try:
        conf = m365.charger()
        if a.action == "connecter":
            m365.connecter(conf)
            return 0
        sortie = (m365.rendre_reponse(m365.demander(conf, a.question)) if a.action == "demander"
                  else m365.rendre_contexte(m365.contexte(conf, a.question, a.source, a.nombre)))
    except (m365.ErreurM365, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print("\n".join(sortie))
    return 0


def _agents_cc(r: dict) -> list[str]:
    """Un groupe par ligne : nom, état, nombre de sessions, rattachement proposé."""
    if not r["actif"]:
        return ["relevé débrayé : réglez [agents_cc] dossier dans config.toml"]
    sortie = [f"{len(r['groupes'])} agent(s) regroupé(s) — dernier relevé {r['derniere'] or 'jamais'}"]
    for g in r["groupes"]:
        cible = (f" -> {g['tache']}" if g["tache"] else "") + (" (ignoré)" if g["ignore"] else "")
        sortie.append(f"{g['nom']} [{g['etat']}] {len(g['historique']) + 1} session(s) : {g['action']}{cible}"
                      f" — {g['motif']}")
    return sortie


