"""Publie une version de GoldenBrain sur GitHub : installateurs construits, note en quatre langues.

Rôle : appelé par la CI locale après chaque publication verte vers le dépôt public. Construit le
paquet .deb, l'installateur Windows et les deux applications macOS (scripts/construire_*.py) depuis
la branche de diffusion du dépôt public, rédige la note de version (anglais, français, espagnol,
allemand : lien d'installation, puis nouveautés depuis la version précédente), et crée la version
GitHub avec ses fichiers.
Frontières : n'envoie rien sans `--envoyer` (publication externe = accord écrit de l'utilisateur,
donné le 2026-11-20 pour la publication à chaque version) ; sans effet si la dernière version
publiée porte déjà l'enregistrement courant du dépôt public ; ne pousse aucune branche.
Les nouveautés se lisent dans l'historique de `--depot` (INV-NOUV-1) : la version précédente y est
retrouvée par son arbre, que le dépôt public reprend tel quel. La traduction est confiée à une
commande facultative (`--traducteur`) ; à défaut ou en cas d'échec, la liste française est reprise.
Invariants portés : INV-NOUV-1, INV-PUB-1 (une traduction qui porte un motif de `.sensible` est écartée).
Usage : python scripts/publier_version.py [--traducteur "<commande, {langue} remplacé>"] [--envoyer]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
from pathlib import Path

import construction as c

sys.path.insert(0, str(c.RACINE / "src"))
from orchestrateur import nouveautes  # noqa: E402

DEPOT_DISTANT = c.DEPOT_PUBLIC.removeprefix("https://github.com/").removesuffix(".git")  # propriétaire/dépôt
# (code, langue nommée pour le traducteur, installation, titre des nouveautés, nouveautés vides), dans l'ordre affiché.
LANGUES = [
    ("en", "English",
     "**Install**: Windows `GoldenBrain-installation.exe` · Debian, Ubuntu `{deb}` · macOS "
     "`GoldenBrain-macos-arm64.zip` (Intel Macs: `GoldenBrain-macos-x86_64.zip`). The installers are not "
     "signed: see the README for the first launch.",
     "What's new", "Internal fixes and improvements."),
    ("fr", "French",
     "**Installer** : Windows `GoldenBrain-installation.exe` · Debian, Ubuntu `{deb}` · macOS "
     "`GoldenBrain-macos-arm64.zip` (Mac Intel : `GoldenBrain-macos-x86_64.zip`). Les installateurs ne sont "
     "pas signés : voir le README pour le premier lancement.",
     "Nouveautés", "Corrections et améliorations internes."),
    ("es", "Spanish",
     "**Instalar**: Windows `GoldenBrain-installation.exe` · Debian, Ubuntu `{deb}` · macOS "
     "`GoldenBrain-macos-arm64.zip` (Mac Intel: `GoldenBrain-macos-x86_64.zip`). Los instaladores no están "
     "firmados: consulte el README para el primer inicio.",
     "Novedades", "Correcciones y mejoras internas."),
    ("de", "German",
     "**Installieren**: Windows `GoldenBrain-installation.exe` · Debian, Ubuntu `{deb}` · macOS "
     "`GoldenBrain-macos-arm64.zip` (Intel-Macs: `GoldenBrain-macos-x86_64.zip`). Die Installationsprogramme "
     "sind nicht signiert: siehe README für den ersten Start.",
     "Neuerungen", "Interne Korrekturen und Verbesserungen."),
]
# Repris tel quel en français faute de traduction : le dire dans la langue du titre (jamais du français muet).
NON_TRADUIT = {"en": "*Not translated yet: the notes below are in French.*",
               "es": "*Aún sin traducir: las notas siguientes están en francés.*",
               "de": "*Noch nicht übersetzt: Die folgenden Hinweise sind auf Französisch.*"}
TITRES = {"en": "English", "fr": "Français", "es": "Español", "de": "Deutsch"}


def executer(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(list(args), cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def prochaine_etiquette(etiquettes: list[str], jour: dt.date) -> str:
    """Même règle que CHANGELOG.md : AAAA.MM.JJ, puis .2, .3 le même jour."""
    deja = "".join(f"## Version {e.removeprefix('v')}\n" for e in etiquettes)
    return "v" + nouveautes.prochaine_version(deja, jour)


def commit_par_arbre(depot: Path, arbre: str, jusqua: str) -> str | None:
    """Enregistrement de `depot` dont l'arbre est `arbre` (le dépôt public ne reprend que l'arbre)."""
    for ligne in executer("git", "log", "--format=%H %T", jusqua, cwd=depot).splitlines():
        sha, t = ligne.split()
        if t == arbre:
            return sha
    return None


def traducteur(commande: str, depot: Path):
    """Fonction (langue, texte) → texte traduit, ou None si la commande échoue ou sort de son rôle."""
    sensibles = nouveautes.motifs_sensibles(depot)

    def traduire(langue: str, texte: str) -> str | None:
        args = [a.replace("{langue}", langue) for a in shlex.split(commande)]
        try:
            r = subprocess.run(args, input=texte, capture_output=True, text=True, encoding="utf-8", timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            return None
        lignes = [l.rstrip() for l in r.stdout.splitlines() if l.strip()]
        if r.returncode or not lignes or not all(l.startswith("- ") for l in lignes):
            return None
        sortie = "\n".join(lignes)
        # INV-PUB-1 : la traduction ne doit rien ajouter de personnel à ce que la porte a laissé passer.
        return None if any(m.search(sortie) for m in sensibles) else sortie

    return traduire


def note(entrees: list[str], deb: str, traduire=None) -> str:
    """Note de version : une section par langue, dans l'ordre de LANGUES."""
    francais = "\n".join(f"- {e}" for e in entrees)
    parties = []
    for code, nom, installer, titre, vide in LANGUES:
        liste = francais
        if entrees and code != "fr":
            traduite = traduire(nom, francais) if traduire else None
            liste = traduite or f"{NON_TRADUIT[code]}\n\n{francais}"
        parties.append(f"## {TITRES[code]}\n\n{installer.format(deb=deb)}\n\n### {titre}\n\n{liste or '- ' + vide}\n")
    return "\n".join(parties)


def deja_publiee(distant: str, source: str, branche: str) -> tuple[list[str], str | None, bool]:
    """(étiquettes publiées, dernière, True si la dernière porte déjà la tête de `branche`)."""
    brut = executer("gh", "release", "list", "--repo", distant, "--limit", "100", "--json", "tagName,isLatest")
    versions = json.loads(brut or "[]")
    etiquettes = [v["tagName"] for v in versions]
    derniere = next((v["tagName"] for v in versions if v["isLatest"]), etiquettes[0] if etiquettes else None)
    if not derniere:
        return etiquettes, None, False
    tete = executer("git", "ls-remote", source, f"refs/heads/{branche}").split()[:1]
    publie = executer("git", "ls-remote", source, f"refs/tags/{derniere}").split()[:1]
    return etiquettes, derniere, bool(tete) and tete == publie


def construire(source: str, branche: str) -> list[Path]:
    for script, *options in (("construire_deb.py",), ("construire_windows.py",),
                             ("construire_macos.py", "--arch", "arm64"), ("construire_macos.py", "--arch", "x86_64")):
        subprocess.run([sys.executable, str(c.RACINE / "scripts" / script), "--source", source,
                        "--branche", branche, *options], check=True)
    debs = sorted(c.CONSTRUCTION.glob("goldenbrain_*_amd64.deb"), key=lambda f: f.stat().st_mtime)
    fichiers = [debs[-1], c.CONSTRUCTION / "GoldenBrain-installation.exe",
                c.CONSTRUCTION / "GoldenBrain-macos-arm64.zip", c.CONSTRUCTION / "GoldenBrain-macos-x86_64.zip"]
    manquants = [f.name for f in fichiers if not f.is_file()]
    if manquants:
        raise c.ErreurConstruction(f"installateurs absents : {', '.join(manquants)}")
    return fichiers


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--depot-distant", default=DEPOT_DISTANT, help="propriétaire/dépôt sur GitHub")
    p.add_argument("--source", default=c.DEPOT_PUBLIC)
    p.add_argument("--branche", default=c.BRANCHE_DIFFUSION)
    p.add_argument("--depot", default=str(c.RACINE), help="dépôt dont l'historique porte les nouveautés")
    p.add_argument("--jusqua", default="HEAD", help="enregistrement de --depot publié par cette version")
    p.add_argument("--traducteur", help="commande qui lit la liste française et écrit sa traduction en {langue}")
    p.add_argument("--notes", help="note de version imposée (fichier), au lieu de la note rédigée")
    p.add_argument("--envoyer", action="store_true", help="créer réellement la version (sinon : afficher)")
    a = p.parse_args()
    depot = Path(a.depot)

    etiquettes, derniere, a_jour = deja_publiee(a.depot_distant, a.source, a.branche)
    if a_jour:
        print(f"{derniere} porte déjà la dernière version publiée : rien à faire")
        return
    fichiers = construire(a.source, a.branche)
    cible = executer("git", "-C", str(c.CONSTRUCTION / "deb" / "arbre" / "opt" / "goldenbrain" / "app"),
                     "rev-parse", "HEAD")
    entrees = []
    if derniere:
        sha = executer("git", "ls-remote", a.source, f"refs/tags/{derniere}").split()[0]
        arbre = executer("gh", "api", f"repos/{a.depot_distant}/commits/{sha}", "--jq", ".commit.tree.sha")
        depuis = commit_par_arbre(depot, arbre, a.jusqua)
        entrees = nouveautes.entrees(depot, depuis, a.jusqua) if depuis else []
    texte = (Path(a.notes).read_text(encoding="utf-8") if a.notes else
             note(entrees, fichiers[0].name, traducteur(a.traducteur, depot) if a.traducteur else None))
    etiquette = prochaine_etiquette(etiquettes, dt.date.today())
    fichier_note = c.CONSTRUCTION / "note-de-version.md"
    fichier_note.write_text(texte, encoding="utf-8")
    commande = ["gh", "release", "create", etiquette, "--repo", a.depot_distant, "--target", cible,
                "--title", f"GoldenBrain {etiquette.removeprefix('v')}", "--notes-file", str(fichier_note),
                "--latest", *map(str, fichiers)]
    if not a.envoyer:
        print(texte)
        print(shlex.join(commande))
        return
    subprocess.run(commande, check=True)
    print(f"version {etiquette} publiée")


if __name__ == "__main__":
    c.principal(main)
