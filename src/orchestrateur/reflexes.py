"""Réflexes GoldenBrain dans les consignes de l'agent du client (CLAUDE.md, AGENTS.md, GEMINI.md…).

Rôle : rédiger le bloc de réflexes (rattacher le travail à une tâche, tracer les documents, lier, consigner
le résultat) dans la langue de l'utilisateur ; situer le fichier de consignes de chaque assistant (global :
dossier personnel ; projet : un dossier donné) ; dire l'état du bloc (absent, à jour, ancien, retouché) ;
montrer le changement en diff ; installer, mettre à jour ou retirer le bloc ; retenir un « plus tard ».
Frontières : stdlib et `langues` seulement (la commande `orch` l'importe sans serveur) ; ne touche que le texte
compris entre ses deux marqueurs, jamais le reste du fichier ; n'écrit que sur un geste explicite de
l'utilisateur (bouton de l'interface, `orch reflexes … --accord`).
Invariants portés : INV-REFLEXES-1.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from . import langues
from .config import RACINE_DEPOT

VERSION = 11  # à relever quand le texte du bloc change : les blocs posés deviennent « ancien »
FIN = "<!-- goldenbrain:reflexes fin -->"
DEBUT = re.compile(r"^<!-- goldenbrain:reflexes debut v(\d+) -->\r?$", re.M)
LIGNE_FIN = re.compile(r"^" + re.escape(FIN) + r"(?=\r?$)", re.M)
# Assistant → (dossier de configuration qui révèle sa présence, fichier global, fichier de projet).
CIBLES = {
    "claude": (".claude", ".claude/CLAUDE.md", "CLAUDE.md"),
    "codex": (".codex", ".codex/AGENTS.md", "AGENTS.md"),
    "opencode": (".config/opencode", ".config/opencode/AGENTS.md", "AGENTS.md"),
    "agy": (".gemini", ".gemini/GEMINI.md", "GEMINI.md"),
    "copilot": (".copilot", ".copilot/copilot-instructions.md", ".github/copilot-instructions.md"),
}
LIBELLES = {"claude": "Claude Code", "codex": "Codex", "opencode": "OpenCode",
            "agy": "Antigravity / Gemini", "copilot": "Copilot"}
CLES = ("titre", "avertissement", "tache", "ranger", "tracer", "lier", "resultat", "decision", "etiquettes", "etape", "conclure")


def maison() -> Path:
    """Dossier personnel ; `ORCH_ACCUEIL_HOME` le remplace (poste factice des essais)."""
    return Path(os.environ.get("ORCH_ACCUEIL_HOME") or Path.home())


def commande() -> str:
    return f'"{sys.executable}" "{RACINE_DEPOT / "orch.py"}"'


def bloc(langue: str | None = None, eol: str = "\n") -> str:
    """Le bloc complet, marqueurs compris, sans fin de ligne finale."""
    lignes = [langues.t(f"serveur.reflexes.bloc_{c}", langue, orch=commande()) for c in CLES]
    corps = [f"## {lignes[0]}", "", lignes[1], ""] + [f"{i}. {x}" for i, x in enumerate(lignes[2:], 1)]
    return eol.join([f"<!-- goldenbrain:reflexes debut v{VERSION} -->", *corps, FIN])


def bornes(texte: str) -> tuple[int, int, int] | None:
    """(début, fin, version) du dernier bloc complet : marqueurs seuls sur leur ligne (INV-REFLEXES-1)."""
    for m in reversed(list(DEBUT.finditer(texte))):
        f = LIGNE_FIN.search(texte, m.end())
        if f:
            return m.start(), f.end(), int(m.group(1))
    return None


def fichier(harnais: str, dossier: str | None = None) -> Path:
    _, glob, projet = CIBLES[harnais]
    return Path(dossier) / projet if dossier else maison() / glob


def lire(chemin: Path) -> str:
    try:
        return chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def etat_texte(texte: str, langue: str | None = None) -> tuple[str, int]:
    """absent | a_jour | ancien | retouche (même version, texte modifié à la main : dérive)."""
    b = bornes(texte)
    if not b:
        return "absent", 0
    if b[2] < VERSION:
        return "ancien", b[2]
    attendu = bloc(langue, "\n")
    return ("a_jour" if texte[b[0]:b[1]].replace("\r\n", "\n") == attendu else "retouche"), b[2]


def transformer(texte: str, action: str, langue: str | None = None) -> str:
    """Texte après `installer` (pose ou remplace le bloc) ou `retirer` ; rien d'autre ne bouge."""
    eol = "\r\n" if "\r\n" in texte else "\n"
    b = bornes(texte)
    if action == "retirer":
        if not b:
            return texte
        avant, apres = texte[:b[0]], texte[b[1]:]
        if not avant.strip():
            return apres.lstrip("\r\n")
        return avant.rstrip("\r\n") + (eol + eol + apres.lstrip("\r\n") if apres.strip() else eol)
    nouveau = bloc(langue, eol)
    if b:
        return texte[:b[0]] + nouveau + texte[b[1]:]
    if not texte.strip():
        return nouveau + eol
    return texte.rstrip("\r\n") + eol + eol + nouveau + eol


def apercu(chemin: Path, action: str, langue: str | None = None) -> str:
    """Diff unifié du changement proposé ; vide si rien ne change."""
    avant = lire(chemin)
    apres = transformer(avant, action, langue)
    return "".join(difflib.unified_diff(avant.splitlines(True), apres.splitlines(True),
                                        str(chemin), str(chemin) + " (GoldenBrain)"))


def appliquer(chemin: Path, action: str, langue: str | None = None) -> bool:
    """INV-REFLEXES-1 : appelé seulement après l'accord explicite de l'utilisateur. Vrai si le fichier change."""
    avant = lire(chemin)
    if chemin.exists() and not avant and chemin.stat().st_size:
        raise ValueError(langues.t("serveur.reflexes.illisible", fichier=str(chemin)))
    apres = transformer(avant, action, langue)
    if apres == avant:
        return False
    cible = chemin.resolve()  # un fichier de consignes en lien symbolique (dotfiles) reste un lien
    cible.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=cible.parent, prefix=".orch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(apres.encode("utf-8"))
        if cible.exists():
            os.chmod(tmp, cible.stat().st_mode & 0o777)
        os.replace(tmp, cible)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def releve(langue: str | None = None, reportes: dict | None = None, dossier: str | None = None) -> list[dict]:
    """Une ligne par assistant : présent sur le poste, fichier, état du bloc, proposition à faire."""
    sortie = []
    for h, (conf, _, _) in CIBLES.items():
        chemin = fichier(h, dossier)
        present = (maison() / conf).is_dir()
        etat, version = etat_texte(lire(chemin), langue)
        differe = (reportes or {}).get(h) == VERSION
        sortie.append({"id": h, "libelle": LIBELLES[h], "present": present, "fichier": str(chemin),
                       "etat": etat, "version": version, "version_courante": VERSION,
                       "propose": present and etat != "a_jour" and not differe})
    return sortie


def lire_reportes(chemin: Path) -> dict:
    try:
        return dict(json.loads(chemin.read_text(encoding="utf-8")).get("plus_tard") or {})
    except (OSError, ValueError, AttributeError):
        return {}
