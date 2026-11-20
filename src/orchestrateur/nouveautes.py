"""Journal des nouveautés : entrées grand public tirées de l'historique git, `CHANGELOG.md`, « Quoi de neuf ».

Rôle : extraire d'un intervalle d'enregistrements les nouveautés lisibles par tous, les ranger en une section
de version dans `CHANGELOG.md`, et dire ce qu'apporte une mise à jour en attente (avis « Quoi de neuf »).
Frontières : `git` par liste d'arguments (`mise_a_jour._git`) ; n'écrit aucun fichier (le script
`scripts/nouveautes.py` écrit, la CI publie) ; ne contacte aucun service.
Invariants portés : INV-NOUV-1 (source des entrées : ligne `Nouveauté:` d'un message d'enregistrement, à
défaut le titre d'un enregistrement qui change le guide ; jamais une fusion ; aucune entrée ne porte un
motif de `.sensible`, INV-PUB-1).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .mise_a_jour import _git
from .vault import ErreurOrch

FICHIER = "CHANGELOG.md"
GUIDE = "docs/GUIDE.md"
MARQUE = re.compile(r"^\s*nouveaut[ée]s?\s*:\s*(.+?)\s*$", re.I | re.M)
TITRE_VERSION = re.compile(r"^## Version (\S+)\s*$", re.M)
JARGON = re.compile(r"\s*\((?:[^()]*\b(?:INV|WCAG|US|lot)\b[^()]*)\)")  # renvois internes, pas pour le public
ENTETE = ("# Nouveautés de GoldenBrain\n\n"
          "Ce journal est tenu automatiquement : chaque version publiée y ajoute ce qu'elle change pour vous, "
          "la plus récente en tête.\n")
SEP_CHAMP, SEP_ENREG = "\x1f", "\x1e"
PLAFOND = 40  # au-delà, l'avis renvoie au journal complet


def motifs_sensibles(depot: Path) -> list[re.Pattern]:
    """INV-PUB-1 : motifs personnels de `.sensible` (non suivi), mêmes règles que la porte."""
    f = Path(depot) / ".sensible"
    if not f.is_file():
        return []
    lignes = (l.strip() for l in f.read_text(encoding="utf-8").splitlines())
    return [re.compile(l, re.I) for l in lignes if l and not l.startswith("#")]


def _propre(phrase: str) -> str:
    phrase = JARGON.sub("", phrase).strip().rstrip(".")
    return phrase[:1].upper() + phrase[1:]


def entrees(depot: Path, depuis: str | None, jusqua: str) -> list[str]:
    """INV-NOUV-1 : nouveautés de `depuis..jusqua` (tout l'historique si `depuis` est vide), dans l'ordre."""
    plage = f"{depuis}..{jusqua}" if depuis else jusqua
    brut = _git(depot, "log", "--no-merges", "--reverse", f"--format=%H{SEP_CHAMP}%s{SEP_CHAMP}%b{SEP_ENREG}", plage)
    guide = set(_git(depot, "log", "--no-merges", "--format=%H", plage, "--", GUIDE).split())
    sensibles = motifs_sensibles(depot)
    vues: list[str] = []
    for enreg in brut.split(SEP_ENREG):
        if not enreg.strip():
            continue
        sha, sujet, corps = (enreg.strip("\n").split(SEP_CHAMP) + ["", ""])[:3]
        marquees = MARQUE.findall(corps)
        candidates = marquees or ([sujet] if sha in guide else [])
        for c in map(_propre, candidates):
            if c and c not in vues and not any(m.search(c) for m in sensibles):
                vues.append(c)
    return vues


def versions(texte: str) -> list[str]:
    return TITRE_VERSION.findall(texte or "")


def prochaine_version(texte: str, jour: dt.date) -> str:
    """Version datée (AAAA.MM.JJ) ; une deuxième publication du même jour prend le suffixe .2, etc."""
    base, deja = jour.strftime("%Y.%m.%d"), set(versions(texte))
    if base not in deja:
        return base
    n = 2
    while f"{base}.{n}" in deja:
        n += 1
    return f"{base}.{n}"


def section(version: str, items: list[str]) -> str:
    corps = "\n".join(f"- {e}" for e in items) or "- Corrections et améliorations internes."
    return f"## Version {version}\n\n{corps}\n"


def ajouter(texte: str, sec: str) -> str:
    """Pose `sec` en tête des versions, sous l'en-tête (créé s'il manque)."""
    texte = texte or ENTETE
    m = TITRE_VERSION.search(texte)
    if not m:
        return texte.rstrip("\n") + "\n\n" + sec
    return texte[:m.start()] + sec + "\n" + texte[m.start():]


def sections(texte: str) -> list[dict]:
    """[{version, entrees}] dans l'ordre du fichier (la plus récente d'abord)."""
    titres = list(TITRE_VERSION.finditer(texte or ""))
    res = []
    for i, m in enumerate(titres):
        fin = titres[i + 1].start() if i + 1 < len(titres) else len(texte)
        items = [l[2:].strip() for l in texte[m.end():fin].splitlines() if l.startswith("- ")]
        res.append({"version": m.group(1), "entrees": items})
    return res


def _fichier_a(depot: Path, ref: str) -> str | None:
    try:
        return _git(depot, "show", f"{ref}:{FICHIER}")
    except ErreurOrch:
        return None


def quoi_de_neuf(depot: Path, ref: str) -> list[dict]:
    """Ce qu'apporte `ref` par rapport à HEAD : les versions de son journal absentes du journal local,
    sinon (dépôt sans journal) les entrées de l'historique HEAD..ref. Jamais d'exception : l'avis de mise
    à jour ne doit pas tomber pour une nouveauté illisible."""
    try:
        distant = _fichier_a(depot, ref)
        if distant is not None:
            locales = set(versions(_fichier_a(depot, "HEAD") or ""))
            res = [s for s in sections(distant) if s["version"] not in locales]
        else:
            items = entrees(depot, "HEAD", ref)
            res = [{"version": None, "entrees": items}] if items else []
    except ErreurOrch:
        return []
    reste = PLAFOND
    for s in res:
        s["entrees"], reste = s["entrees"][:max(reste, 0)], reste - len(s["entrees"])
    return [s for s in res if s["entrees"]]
