"""Rattachement d'une tâche à un codespace GitHub : déclaration, état, gestes, lieu d'exécution.

Rôle : lire la clé `codespace:` du `contexte.md` du conteneur d'une tâche, la clé `ou:` de la
tâche (`poste` par défaut, `codespace`), et en déduire la section de conf d'un tour distant ;
exposer l'état et les gestes (ouvrir dans VS Code, dans le navigateur, arrêter).
Frontières : `gh` n'est appelé que par `harnais/distant.py` ; ni création ni suppression de
codespace ; aucune écriture vault hors de la clé `ou:` (posée par `api_codespace.py`).
Invariants portés : INV-CODESPACE-1 (par `harnais/distant.py`), INV-CODESPACE-2 (une tâche
`ou: codespace` ne retombe jamais sur le poste).
"""

from __future__ import annotations

import subprocess
import sys

from . import fiches, langues
from .harnais import distant
from .vault import Invalide, Tache, Vault

LIEUX = ("poste", "codespace")
GESTES = {"code": [], "web": ["--web"]}


def declaration(vault: Vault, t: Tache) -> str:
    """Codespace déclaré par le projet de la tâche ("" si aucun ou invalide)."""
    try:
        fm = fiches.frontmatter(fiches.lire(vault.racine / t.conteneur / vault.cfg.contexte))
        return distant.declaration_valide(fm.get("codespace")) if fm.get("codespace") else ""
    except (OSError, distant.ErreurCodespace):
        return ""


def lieu(t: Tache) -> str:
    return "codespace" if str(t.fm.get("ou") or "") == "codespace" else "poste"


def conf_tour(conf: dict, nom: str, vault: Vault, t: Tache) -> dict:
    """Section de conf du harnais pour ce tour ; distante si la tâche s'exécute au codespace."""
    if lieu(t) != "codespace":
        return conf
    # INV-CODESPACE-2 : jamais de repli silencieux sur le poste.
    if not (decl := declaration(vault, t)):
        raise Invalide(langues.t("serveur.codespace.aucun_declare"))
    if nom not in distant.INSTALLATION:
        raise Invalide(langues.t("serveur.codespace.assistant_non_pris_en_charge", nom=nom,
                                 pris=", ".join(distant.INSTALLATION)))
    return {**conf, "distant": {"codespace": decl, "harnais": nom}}


async def etat(vault: Vault, t: Tache, frais: bool = False) -> dict:
    """Codespace de la tâche et son état ; une erreur de `gh` se rend, elle ne lève pas."""
    decl = declaration(vault, t)
    vue = {"declaration": decl, "ou": lieu(t), "nom": "", "etat": "", "depot": "", "erreur": ""}
    if not decl:
        return vue
    try:
        c = distant.choisir(decl, await distant.lister(frais))
    except (distant.ErreurCodespace, ValueError) as e:
        return {**vue, "erreur": str(e) or langues.t("serveur.codespace.reponse_illisible")}
    if not c:
        return {**vue, "erreur": langues.t("serveur.codespace.aucun_pour", decl=decl)}
    return {**vue, "nom": c["nom"], "etat": c["etat"], "depot": c["depot"]}


async def geste(vault: Vault, t: Tache, quoi: str) -> str:
    """Ouvre (VS Code ou navigateur, détaché : le démarrage peut être long) ou arrête."""
    if not (decl := declaration(vault, t)):
        raise Invalide(langues.t("serveur.codespace.projet_sans"))
    try:
        nom = (await distant.resoudre(decl))["nom"]
        if quoi == "arreter":
            await distant.gh("codespace", "stop", "-c", nom, delai=120)
            await distant.lister(frais=True)  # l'état affiché suit le geste
        elif quoi in GESTES:
            drapeaux = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            subprocess.Popen([*distant.commande_gh(), "codespace", "code", "-c", nom, *GESTES[quoi]],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=drapeaux)
        else:
            raise Invalide(langues.t("serveur.codespace.geste_inconnu", geste=quoi))
    except distant.ErreurCodespace as e:
        raise Invalide(str(e)) from None
    return nom
