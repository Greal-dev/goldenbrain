"""Mise à jour de GoldenBrain depuis la branche de diffusion : contrôle, avance rapide, commande.

Rôle : dire de combien de commits le dépôt local est en retard sur `<distant>/<branche>`, et
l'avancer en avance rapide seulement ; sert la route `/api/mise-a-jour` et `mettre-a-jour.cmd`.
Frontières : `git` par liste d'arguments, jamais de shell ; ni fusion, ni réécriture
d'historique, ni `stash` ; ne touche que les fichiers suivis par git (donc jamais `config.toml`,
`etat/`, `journal/`, `equipe/`, ignorés) ; aucune action hors d'un dépôt git.
Canal (INV-MAJ-4) : « stable » suit `[mise_a_jour] branche`, « bêta » suit `beta` ; changer de canal
bascule le checkout d'une branche de diffusion à l'autre, jamais depuis une autre branche.
Invariants portés : INV-MAJ-1 (avance rapide seule, refus clair), INV-MAJ-2 (git sans shell), INV-MAJ-4.
"""

from __future__ import annotations

import json
import os
import re
import dataclasses
import subprocess
import sys
import urllib.error
import urllib.request

from . import langues
from .config import RACINE_DEPOT, ConfigMiseAJour
from .vault import ErreurOrch

DELAI_GIT_S = 60
FICHIER_RETOUR = ".maj_retour"  # racine du dépôt (non suivi) : version à rétablir si le serveur relancé ne démarre pas (lancer.sh)
EMPREINTE = re.compile(r"[0-9a-f]{7,40}")
SUR = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")
CANAUX = ("stable", "beta")
BRANCHE_BETA = "beta"  # branche du dépôt public qui reçoit les versions en essai (INV-MAJ-4)


class Refus(ErreurOrch):
    """Mise à jour refusée pour une raison que l'utilisateur peut lever (409 dans l'API)."""
    code = 409


def _git(depot, *args: str, delai: float = DELAI_GIT_S) -> str:
    # INV-MAJ-2 : liste d'arguments, jamais de shell ; pas d'invite d'identifiants qui bloquerait.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        r = subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=delai, env=env)
    except FileNotFoundError as e:
        raise ErreurOrch(langues.t("serveur.mise_a_jour.git_introuvable")) from e
    except subprocess.TimeoutExpired as e:
        raise ErreurOrch(langues.t("serveur.mise_a_jour.git_muet", delai=int(delai),
                                       commande=" ".join(args[:2]))) from e
    if r.returncode:
        raise ErreurOrch((r.stderr or r.stdout).strip() or langues.t("serveur.mise_a_jour.git_echec", commande=args[0]))
    return r.stdout.rstrip()  # pas de strip() gauche : « git status --porcelain » commence par une espace


def _noms_sains(c: ConfigMiseAJour) -> None:
    # Un nom qui commencerait par « - » passerait pour une option de git.
    for n in (c.branche, c.distant):
        if not SUR.fullmatch(n or ""):
            raise ErreurOrch(langues.t("serveur.mise_a_jour.nom_invalide", nom=repr(n)))


def suivie(c: ConfigMiseAJour, canal: str) -> tuple[ConfigMiseAJour, tuple[str, ...]]:
    """INV-MAJ-4 : configuration du canal choisi, et les branches de diffusion entre lesquelles on bascule."""
    if canal not in CANAUX:
        raise ErreurOrch(langues.t("serveur.mise_a_jour.canal_inconnu", canal=repr(canal), canaux=", ".join(CANAUX)))
    effective = dataclasses.replace(c, branche=BRANCHE_BETA) if canal == "beta" else c
    return effective, (c.branche, BRANCHE_BETA)


def est_depot(depot) -> bool:
    return (depot / ".git").exists()


def etat(depot, c: ConfigMiseAJour, recuperer: bool = True, canaux: tuple[str, ...] = ()) -> dict:
    """Version locale, version distante, retard. `recuperer` : `git fetch` d'abord. `bascule` : le checkout
    est sur l'autre branche de diffusion (`canaux`) — le canal choisi attend d'être rejoint (INV-MAJ-4)."""
    _noms_sains(c)
    if not est_depot(depot):
        return {"depot": False, "branche": c.branche}
    ref = f"{c.distant}/{c.branche}"
    if recuperer:
        # Refspec explicite : met à jour `<distant>/<branche>` même sans suivi configuré.
        _git(depot, "fetch", "--quiet", c.distant, f"+refs/heads/{c.branche}:refs/remotes/{ref}")
    locale = _git(depot, "rev-parse", "--short", "HEAD")
    distante = _git(depot, "rev-parse", "--short", ref)
    retard = int(_git(depot, "rev-list", "--count", f"HEAD..{ref}"))
    avance = int(_git(depot, "rev-list", "--count", f"{ref}..HEAD"))
    courante = _git(depot, "rev-parse", "--abbrev-ref", "HEAD")
    modifies = [l[3:] for l in _git(depot, "status", "--porcelain", "--untracked-files=no").splitlines()]
    bascule = courante != c.branche and courante in canaux
    return {"depot": True, "branche": c.branche, "distant": c.distant, "branche_courante": courante,
            "locale": locale, "distante": distante, "retard": max(retard, 1) if bascule else retard,
            "avance": avance, "modifies": modifies, "bascule": bascule}


def _basculer(depot, c: ConfigMiseAJour) -> None:
    """INV-MAJ-4 : rejoint la branche du canal, puis l'avance rapide ; une copie locale divergente est refusée."""
    ref = f"{c.distant}/{c.branche}"
    try:
        _git(depot, "rev-parse", "--verify", "--quiet", f"refs/heads/{c.branche}")
    except ErreurOrch:  # première venue sur ce canal : branche locale neuve qui suit le distant
        _git(depot, "switch", "--quiet", "-c", c.branche, "--track", ref)
        return
    if int(_git(depot, "rev-list", "--count", f"{ref}..refs/heads/{c.branche}")):
        raise Refus(langues.t("serveur.mise_a_jour.locale_divergente", version=c.branche, ref=ref))
    _git(depot, "switch", "--quiet", c.branche)
    _git(depot, "merge", "--ff-only", "--quiet", ref)


def appliquer(depot, c: ConfigMiseAJour, canaux: tuple[str, ...] = ()) -> dict:
    """INV-MAJ-1 : avance le checkout en avance rapide seulement. Refus (`Refus`) s'il y a des
    modifications locales, une autre branche en cours, ou un historique divergent. INV-MAJ-4 : depuis
    l'autre branche de diffusion (`canaux`), bascule sur celle du canal choisi."""
    e = etat(depot, c, canaux=canaux)
    if not e["depot"]:
        raise Refus(langues.t("serveur.mise_a_jour.pas_depot"))
    if e["modifies"]:
        fichiers = ", ".join(e["modifies"][:5]) + (" …" if len(e["modifies"]) > 5 else "")
        raise Refus(langues.t("serveur.mise_a_jour.modifs_locales", fichiers=fichiers))
    if e["bascule"]:
        _basculer(depot, c)
        return {**etat(depot, c, recuperer=False, canaux=canaux), "appliquee": True}
    if e["branche_courante"] != c.branche:
        raise Refus(langues.t("serveur.mise_a_jour.autre_version", courante=e["branche_courante"],
                              attendue=c.branche))
    if e["retard"] and e["avance"]:
        raise Refus(langues.t("serveur.mise_a_jour.diverge", avance=e["avance"], ref=f"{c.distant}/{c.branche}",
                              retard=e["retard"]))
    if not e["retard"]:
        return {**e, "appliquee": False}
    _git(depot, "merge", "--ff-only", "--quiet", f"{c.distant}/{c.branche}")
    return {**etat(depot, c, recuperer=False), "appliquee": True}


def revenir(depot, sha: str) -> None:
    """INV-MAJ-3 : rétablit la version d'avant une mise à jour automatique. Sans risque pour le travail de
    l'utilisateur : `appliquer` n'avance qu'un dépôt sans modification locale suivie."""
    if not EMPREINTE.fullmatch(sha or ""):
        raise ErreurOrch(langues.t("serveur.mise_a_jour.version_invalide", sha=repr(sha)))
    _git(depot, "reset", "--hard", "--quiet", sha)


def verifier_import(depot) -> None:
    """INV-MAJ-3 : le code avancé se charge-t-il ? (interpréteur neuf, avant tout redémarrage)."""
    code = "import sys; sys.path.insert(0, sys.argv[1]); import orchestrateur.api"
    try:
        r = subprocess.run([sys.executable, "-c", code, str(depot / "src")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=DELAI_GIT_S, cwd=str(depot))
    except subprocess.TimeoutExpired as e:
        raise ErreurOrch(langues.t("serveur.mise_a_jour.chargement_infini")) from e
    if r.returncode:
        raise ErreurOrch((r.stderr.strip().splitlines() or [langues.t("serveur.mise_a_jour.chargement_echec")])[-1])


def redemarrer_serveur(port: int) -> str:
    """Demande le redémarrage du serveur local ; rend une phrase pour l'utilisateur."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/redemarrer", data=b'{"par": "mise_a_jour"}', method="POST",
                                 headers={"X-Orchestrateur": "1", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except urllib.error.HTTPError as e:
        if e.code in (409, 429):  # 429 : serveur lancé depuis moins de 60 s (INV-VERSION-2)
            try:
                motif = json.loads(e.read())["detail"]
            except (ValueError, KeyError):
                motif = "un tour tourne"
            return f"Serveur non redémarré ({motif}) : utilisez « Redémarrer » dans l'interface après."
        return f"Serveur non redémarré (HTTP {e.code}) : relancez lancer.cmd."
    except (urllib.error.URLError, OSError):
        return "Le serveur ne tourne pas : lancez lancer.cmd pour utiliser la nouvelle version."
    return "Serveur redémarré : rechargez la page."


def main() -> int:
    from .config import charger
    from .maj_auto import canal_enregistre
    try:
        config = charger()
        c, port = config.mise_a_jour, config.port
        c, canaux = suivie(c, canal_enregistre(config.donnees / "etat" / "maj_auto.json"))
    except (FileNotFoundError, KeyError):  # pas encore de config.toml : réglages par défaut
        (c, canaux), port = suivie(ConfigMiseAJour(), "stable"), 8300
    try:
        r = appliquer(RACINE_DEPOT, c, canaux)
    except Refus as e:
        print(f"Mise à jour refusée : {e}")
        return 1
    except ErreurOrch as e:
        print(f"Mise à jour impossible : {e}")
        return 2
    if not r["appliquee"]:
        print(f"Déjà à jour ({r['locale']}).")
        return 0
    print(f"Mis à jour : {r['locale']} ({c.distant}/{c.branche}).")
    print(redemarrer_serveur(port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
