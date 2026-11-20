"""Codespace GitHub par `gh` : lister, résoudre une déclaration, envelopper la commande d'un harnais.

Rôle : seul endroit où `gh` est appelé ; un harnais `distant` (section de conf portant `distant`)
fait passer son argv par `envelopper` et s'exécute dans le codespace par `gh codespace ssh`.
Frontières : aucune E/S vault ; aucun jeton lu ni stocké (l'authentification est celle de `gh`) ;
ni création ni suppression de codespace.
Invariants portés : INV-CODESPACE-1 (`gh` sans shell local, noms validés, commande distante
citée argument par argument).
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import shutil
import time

from .. import langues

NOM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
DEPOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
INSTALLATION = {"claude": "npm install -g @anthropic-ai/claude-code",
                "codex": "npm install -g @openai/codex"}
ENV_TRANSMIS = ("ORCH_TACHE", "ORCH_SAUTS", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")  # ORCH_URL désigne le poste : injoignable du codespace
GH = "gh"  # posé depuis `Config.gh` au démarrage de l'API
DELAI_S = 30
FRAICHEUR_S = 15
_cache: tuple[float, list[dict]] | None = None


class ErreurCodespace(Exception):
    pass


def commande_gh() -> list[str]:
    """Argv de tête de `gh` (les tests le remplacent par un faux `gh`)."""
    exe = shutil.which(GH)
    if not exe:
        raise ErreurCodespace(langues.t("serveur.distant.gh_introuvable"))
    return [exe]


def declaration_valide(decl) -> str:
    """Nom de codespace ou dépôt `propriétaire/nom` ; toute autre valeur est refusée."""
    decl = str(decl or "").strip()
    if not (NOM.fullmatch(decl) or DEPOT.fullmatch(decl)):
        raise ErreurCodespace(langues.t("serveur.distant.declaration_invalide", decl=repr(decl)))
    return decl


async def gh(*args: str, delai: float = DELAI_S) -> str:
    # INV-CODESPACE-1 : liste d'arguments, jamais de shell local.
    proc = await asyncio.create_subprocess_exec(
        *commande_gh(), *args, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        sortie, erreurs = await asyncio.wait_for(proc.communicate(), delai)
    except TimeoutError:
        proc.kill()
        raise ErreurCodespace(langues.t("serveur.distant.delai", commande=args[1] if len(args) > 1 else "")) from None
    if proc.returncode:
        raise ErreurCodespace(erreurs.decode("utf-8", "replace").strip()[-500:]
                              or f"gh : code {proc.returncode}")
    return sortie.decode("utf-8", "replace")


async def lister(frais: bool = False) -> list[dict]:
    """Codespaces du compte `gh` (nom, état, dépôt), gardés quelques secondes."""
    global _cache
    if not frais and _cache and time.monotonic() - _cache[0] < FRAICHEUR_S:
        return _cache[1]
    brut = json.loads(await gh("codespace", "list", "--json", "name,state,repository,displayName"))
    liste = [{"nom": str(c.get("name") or ""), "etat": str(c.get("state") or ""),
              "depot": str(c.get("repository") or ""), "titre": str(c.get("displayName") or "")}
             for c in brut if isinstance(c, dict) and NOM.fullmatch(str(c.get("name") or ""))]
    _cache = (time.monotonic(), liste)
    return liste


def choisir(decl: str, liste: list[dict]) -> dict | None:
    """Le codespace de ce nom, sinon le premier du dépôt déclaré."""
    return next((c for c in liste if c["nom"] == decl), None) or next(
        (c for c in liste if "/" in decl and c["depot"].lower() == decl.lower()), None)


async def resoudre(decl: str) -> dict:
    decl = declaration_valide(decl)
    c = choisir(decl, await lister())
    if not c:
        raise ErreurCodespace(langues.t("serveur.distant.aucun_pour", decl=decl))
    return c


def script_distant(argv: list[str], env: dict[str, str], dossier: str, harnais: str,
                   nom: str) -> str:
    """Commande à faire exécuter par le shell de connexion du codespace.

    INV-CODESPACE-1 : chaque argument est cité (`shlex.quote`) — la consigne et les options ne
    sont jamais réinterprétées par le shell distant.
    """
    q = shlex.quote
    absent = langues.t("serveur.distant.absent", exe=argv[0], nom=nom, installer=INSTALLATION.get(harnais, argv[0]))
    variables = " ".join(f"{k}={q(v)}" for k, v in env.items() if k in ENV_TRANSMIS)
    script = (f"command -v {q(argv[0])} >/dev/null 2>&1 || {{ echo {q(absent)} >&2; exit 127; }}; "
              f"cd {q(dossier)} 2>/dev/null; exec env {variables} {shlex.join(argv)}")
    return "bash -lc " + q(script)  # shell de connexion : PATH de npm/nvm du codespace


async def envelopper(argv: list[str], distant: dict | None, env: dict[str, str]) -> list[str]:
    """Argv local qui lance `argv` (tête non résolue : `claude`, `codex`) dans le codespace."""
    if not distant:
        return argv
    c = await resoudre(distant["codespace"])
    dossier = "/workspaces/" + c["depot"].rsplit("/", 1)[-1] if c["depot"] else "~"
    return [*commande_gh(), "codespace", "ssh", "-c", c["nom"], "--",
            script_distant(argv, env, dossier, str(distant.get("harnais") or ""), c["nom"])]


def indice(erreur: str, distant: dict | None) -> str:
    """Erreur d'un harnais distant non connecté : on dit comment le connecter (essai réel du 15/11)."""
    if not distant or not any(m in erreur.lower() for m in ("not logged in", "/login", "login")):
        return erreur
    option = "-R" if "/" in distant["codespace"] else "-c"
    return langues.t("serveur.distant.non_connecte", erreur=erreur, option=option, codespace=distant["codespace"])


def commande_terminal(commande: str, distant: dict) -> str:
    """Reprise à la main dans le codespace (console du poste)."""
    decl = declaration_valide(distant["codespace"])
    cible = f"-R {decl}" if "/" in decl else f"-c {decl}"
    return f"gh codespace ssh {cible} -- -t {shlex.quote(commande)}"
