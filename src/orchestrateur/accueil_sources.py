"""Accueil — lecteurs des sources, du moins intrusif au plus intrusif, chacun en lecture seule.

Rôle : rendre, pour chaque source que l'arrivant a cochée, des données brutes : historiques de
conversations (Claude Code, Codex : session, dossier de travail, dates, titre, volume, état apparent),
projets d'un dossier désigné, dossiers et cases à cocher d'un vault déjà là.
Frontières : n'écrit rien nulle part ; ne parle à aucun modèle ; ne lit que ce qu'une source cochée
désigne (jamais le disque en entier) ; ne suit aucun lien symbolique ; chaque lecture est bornée.
Invariants portés : INV-ACCUEIL-1 (lecture seule, locale, par source consentie).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
HARNAIS_LUS = ("claude", "codex")   # les autres : à mesure que leur stockage est connu
MAX_LIGNES = 4000                    # lignes lues par conversation
MAX_FICHIERS = 1500                  # conversations considérées par harnais
EN_COURS_S = 600
MARQUEURS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "README.md")
IGNORES = {"node_modules", "__pycache__", "venv", ".venv", "dist", "build", "target", "Archives", "_meta"}
CASE = re.compile(r"^\s*[-*]\s+\[ \]\s+(.{4,160}?)\s*$")


@dataclass
class Conv:
    harnais: str
    session: str
    dossier: str
    debut: str
    fin: str
    titre: str
    volume: int      # messages de l'utilisateur
    etat: str        # en_cours | terminee | abandonnee


def maison() -> Path:
    """Dossier personnel ; `ORCH_ACCUEIL_HOME` le remplace (essai sur un poste factice)."""
    return Path(os.environ.get("ORCH_ACCUEIL_HOME") or Path.home())


def _texte(contenu) -> str:
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return " ".join(b.get("text", "") for b in contenu if isinstance(b, dict)
                        and b.get("type") in ("text", "input_text"))
    return ""


def _reel(texte: str) -> str | None:
    """Message écrit par l'humain : ni balise système, ni commande, ni interruption."""
    t = " ".join((texte or "").split())
    return t if t and not t.startswith(("<", "[Request interrupted", "Caveat:")) else None


def _jour(ts) -> str:
    return str(ts or "")[:10]


def _lignes(chemin: Path):
    with chemin.open(encoding="utf-8", errors="replace") as f:
        for i, ligne in enumerate(f):
            if i >= MAX_LIGNES:
                return
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            if isinstance(d, dict):
                yield d


def _etat(chemin: Path, dernier: str) -> str:
    if time.time() - chemin.stat().st_mtime < EN_COURS_S:
        return "en_cours"
    return "terminee" if dernier == "assistant" else "abandonnee"


def _conv_claude(chemin: Path) -> Conv | None:
    cwd, titres, dates, dernier = "", [], [], ""
    for d in _lignes(chemin):
        cwd = cwd or str(d.get("cwd") or "")
        if d.get("ts") or d.get("timestamp"):
            dates.append(_jour(d.get("timestamp")))
        if d.get("isSidechain") or d.get("isMeta"):
            continue
        m = d.get("message") or {}
        if d.get("type") == "user" and (t := _reel(_texte(m.get("content")))):
            titres.append(t)
            dernier = "user"
        elif d.get("type") == "assistant":
            dernier = "assistant"
    if not titres or not cwd:
        return None
    dates = [x for x in dates if x]
    return Conv("claude", chemin.stem, cwd, min(dates, default=""), max(dates, default=""),
                titres[0][:90], len(titres), _etat(chemin, dernier))


def _conv_codex(chemin: Path) -> Conv | None:
    cwd, sid, debut, dates, dernier = "", "", "", [], ""
    evenements, reponses = [], []
    for d in _lignes(chemin):
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        if d.get("timestamp"):
            dates.append(_jour(d["timestamp"]))
        if d.get("type") == "session_meta":
            cwd, sid, debut = str(p.get("cwd") or ""), str(p.get("id") or ""), _jour(p.get("timestamp"))
        elif d.get("type") == "event_msg" and p.get("type") == "user_message":
            if t := _reel(str(p.get("message") or "")):
                evenements.append(t)
                dernier = "user"
        elif d.get("type") == "event_msg" and p.get("type") == "agent_message":
            dernier = "assistant"
        elif d.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user":
            if t := _reel(_texte(p.get("content"))):
                reponses.append(t)
    titres = evenements or reponses  # les deux formes disent la même chose : jamais comptées deux fois
    if not titres or not cwd or not sid:
        return None
    dates = [x for x in dates if x]
    return Conv("codex", sid, cwd, debut or min(dates, default=""), max(dates, default=""),
                titres[0][:90], len(titres), _etat(chemin, dernier))


def _fichiers(harnais: str, home: Path) -> list[Path]:
    if harnais == "claude":
        base, trouves = home / ".claude" / "projects", []
        if base.is_dir():
            for d in base.iterdir():
                if d.is_dir() and not d.is_symlink():
                    trouves += [f for f in d.glob("*.jsonl") if not f.is_symlink()]
    else:
        base = home / ".codex" / "sessions"
        trouves = [f for f in base.rglob("rollout-*.jsonl") if not f.is_symlink()] if base.is_dir() else []
    return sorted(trouves, key=lambda f: f.stat().st_mtime, reverse=True)[:MAX_FICHIERS]


def disponibles(home: Path | None = None) -> dict[str, int]:
    """Nombre de conversations trouvées par harnais (noms de fichiers seulement, rien n'est lu)."""
    home = home or maison()
    return {h: len(_fichiers(h, home)) for h in HARNAIS_LUS}


def conversations(harnais: list[str], depuis_jours: int = 90, home: Path | None = None) -> list[Conv]:
    home, limite, out = home or maison(), time.time() - depuis_jours * 86400, []
    for h in harnais:
        if h not in HARNAIS_LUS:
            continue
        lire = _conv_claude if h == "claude" else _conv_codex
        for f in _fichiers(h, home):
            try:
                if f.stat().st_mtime >= limite and (c := lire(f)):
                    out.append(c)
            except OSError as e:
                log.warning("conversation illisible, ignorée : %s (%s)", f.name, e)
    return out


def racine_depot(dossier: str) -> str:
    """Racine du dépôt qui contient `dossier` (le plus proche `.git`), sinon le dossier lui-même."""
    p = Path(dossier)
    for x in (p, *p.parents):
        if (x / ".git").exists():
            return str(x)
        if x == x.parent:
            break
    return str(p)


def _resume(dossier: Path) -> str:
    try:
        for ligne in (dossier / "README.md").read_text(encoding="utf-8", errors="replace").splitlines()[:30]:
            t = ligne.strip()
            if t and not t.startswith(("#", "!", "[", "<", "-", "=", "`")):
                return t[:140]
    except OSError:
        pass
    return ""


def _marque(d: Path) -> bool:
    return any((d / m).exists() for m in MARQUEURS)


def projets_du_dossier(chemin: str, limite: int = 60) -> list[dict]:
    """Projets que désigne un dossier : lui-même s'il en est un, sinon ses sous-dossiers qui en sont."""
    racine = Path(chemin).expanduser()
    if not racine.is_dir() or racine.is_symlink():
        return []
    if _marque(racine):
        return [{"nom": racine.name, "dossier": str(racine), "resume": _resume(racine)}]
    sous = sorted(d for d in racine.iterdir() if d.is_dir() and not d.is_symlink()
                  and not d.name.startswith(".") and d.name not in IGNORES)
    marques = [d for d in sous if _marque(d)]
    return [{"nom": d.name, "dossier": str(d), "resume": _resume(d)} for d in (marques or sous)[:limite]]


def vault_existant(chemin: Path, limite_cases: int = 40) -> list[dict]:
    """Dossiers de premier niveau d'un vault déjà là, avec leurs cases `- [ ]` ouvertes (lecture seule)."""
    out = []
    for d in sorted(x for x in chemin.iterdir() if x.is_dir() and not x.is_symlink()
                    and not x.name.startswith(".") and x.name not in IGNORES):
        notes = [f for f in d.rglob("*.md") if not f.is_symlink() and "taches" not in f.parts][:200]
        cases = []
        for f in notes:
            try:
                for ligne in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    if (m := CASE.match(ligne)) and len(cases) < limite_cases:
                        cases.append({"titre": m.group(1), "note": f.relative_to(chemin).as_posix()})
            except OSError:
                continue
        if notes:
            out.append({"nom": d.name, "dossier": d.relative_to(chemin).as_posix(), "notes": len(notes), "cases": cases})
    return out


def jour_de(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None
