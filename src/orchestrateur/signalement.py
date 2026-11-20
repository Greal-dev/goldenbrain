"""« Signaler un problème / Proposer une idée » : adresses de formulaire GitHub pré-remplies.

Rôle : composer les adresses des formulaires de ticket du dépôt public (`.github/ISSUE_TEMPLATE/`),
pré-remplies avec la version, le canal et le système, et celle de la page « Devenir testeur ».
Frontières : n'envoie rien — l'interface ouvre l'adresse dans le navigateur, l'utilisateur relit et
envoie lui-même ; aucune lecture du vault, de `config.toml` ni de l'environnement de l'utilisateur.
Invariants portés : INV-SIGNAL-1 (rien de personnel dans l'adresse : empreinte et date du commit,
canal, nom et version du système, version de Python — jamais un chemin, un nom ou un contenu).
"""

from __future__ import annotations

import platform
import urllib.parse

from . import mise_a_jour
from .vault import ErreurOrch

DEPOT_PUBLIC = "https://github.com/Greal-dev/goldenbrain".removeprefix("https://github.com/")  # les tickets vont au projet, même depuis une copie ou une branche
FORMULAIRES = {"anomalie": "anomalie.yml", "idee": "evolution.yml"}


def version(depot) -> str:
    """Empreinte courte et date du commit servi ; « inconnue » hors d'un dépôt git."""
    try:
        return mise_a_jour._git(depot, "log", "-1", "--format=%h (%cs)", delai=5)
    except ErreurOrch:
        return "inconnue"


def systeme() -> str:
    nom = platform.system()
    if nom == "Darwin":
        nom, rel = "macOS", platform.mac_ver()[0]
    else:
        rel = platform.release()
    return f"{nom} {rel} · Python {platform.python_version()}".strip()


def adresse(formulaire: str, champs: dict[str, str], depot_public: str = DEPOT_PUBLIC) -> str:
    requete = urllib.parse.urlencode({"template": FORMULAIRES[formulaire], **champs})
    return f"https://github.com/{depot_public}/issues/new?{requete}"


def adresses(depot, canal: str) -> dict:
    """INV-SIGNAL-1 : seuls ces trois champs partent dans l'adresse ; `id` des champs = ceux des formulaires."""
    champs = {"version": f"{version(depot)} · canal {canal}", "systeme": systeme()}
    base = f"https://github.com/{DEPOT_PUBLIC}"
    return {"anomalie": adresse("anomalie", champs), "idee": adresse("idee", {"version": champs["version"]}),
            "testeur": f"{base}/blob/main/BETA.md", "discussions": f"{base}/discussions", "champs": champs}
