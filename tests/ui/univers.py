"""Vault temporaire et configuration des tests d'interface.

Rôle : `construire(dossier, port)` écrit un petit vault (projet Alpha : mère > enfant > petit,
projet Beta, tâche close) et un `config.toml` qui le désigne ; renvoie le chemin de la config.
Frontières : n'écrit que sous `dossier` (jamais le vrai vault). Un scénario qui a besoin d'un autre
univers appelle `ecrire` pour ajouter ses fichiers avant d'agir.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT_SONDE = _port_libre()  # point d'accès du fournisseur factice sondé par INV-RESEAU-1 : fermé tant qu'un scénario ne l'ouvre pas


def ecrire(racine: Path, rel: str, texte: str) -> Path:
    p = racine / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texte.encode("utf-8"))
    return p


def tache(titre: str, statut: str = "a-faire", extra: str = "") -> str:
    return f"---\ntype: tache\nstatut: {statut}\n{extra}tags: []\n---\n\n# {titre}\n\nCorps de {titre}.\n"


def git(depot: Path, *args: str, heures: float = 0) -> None:
    quand = f"@{int(time.time() - heures * 3600)} +0000"
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_AUTHOR_DATE": quand, "GIT_COMMITTER_DATE": quand}
    subprocess.run(["git", "-C", str(depot), *args], check=True, capture_output=True, env=env)


def depot_git(dossier: Path) -> Path:
    """Petit dépôt git (INV-INTEG-1) : `gb/integration`, et `gb/ui-retard` terminée depuis 5 h, non fusionnée."""
    d = dossier / "depot-git"
    d.mkdir()
    git(d, "init", "-q", "-b", "gb/integration")
    git(d, "commit", "-q", "--allow-empty", "-m", "base", heures=50)
    git(d, "checkout", "-q", "-b", "gb/ui-retard")
    git(d, "commit", "-q", "--allow-empty", "-m", "travail", heures=5)
    git(d, "checkout", "-q", "gb/integration")
    return d


def construire(dossier: Path, port: int, telegram_api: str = "") -> Path:
    depot = depot_git(dossier)
    vault = dossier / "vault"
    ecrire(vault, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\n---\n")
    ecrire(vault, "Projets/C1-Alpha/taches/mere.md", tache("Mère"))
    ecrire(vault, "Projets/C1-Alpha/taches/enfant.md", tache("Enfant", extra='parent: "[[mere]]"\n'))
    ecrire(vault, "Projets/C1-Alpha/taches/petit.md", tache("Petit", extra="parent: enfant\n"))
    ecrire(vault, "Projets/C2-Beta/contexte.md", "---\ntype: contexte\ncasquette: C2-Patrimoine\nnom: Beta\n---\n")
    ecrire(vault, "Projets/C2-Beta/taches/bail.md", tache("Bail de Beta"))
    ecrire(vault, "_meta/taches/fermee.md", tache("Fermée", statut="fait"))
    config = dossier / "config.toml"
    config.write_text(f"""[serveur]
port = {port}

[vault]
racine = "{vault.as_posix()}"
taches = ["Projets/*/taches/*.md", "Casquettes/*/*/taches/*.md", "Casquettes/*/*/*/taches/*.md", "_meta/taches/*.md"]
exclure = ["_meta/templates/*"]
index_ttl_s = 0  # les scénarios écrivent des fiches puis relisent aussitôt ; scenario_reactivite le remet à 2 (défaut réel)

[moteur]
harnais_defaut = "faux"

[harnais.faux]

[reseau]
intervalle_court_s = 1
duree_courte_s = 600
intervalle_long_s = 1
delai_sonde_s = 1
hotes = {{ faux = ["127.0.0.1:{PORT_SONDE}"] }}

[integration]
depot = "{depot.as_posix()}"
cache_s = 1

[conseil]
actif = false

[agents_cc]
dossier = "{(dossier / 'jobs').as_posix()}"
rythme = "a-la-demande"

[vigie]
silence_s = 3
intervalle_s = 1

[consigne]
gabarit = "Tâche {{titre}} ({{chemin}})"
""" + (f'\n[telegram]\napi = "{telegram_api}"\n' if telegram_api else ""), encoding="utf-8")
    return config
