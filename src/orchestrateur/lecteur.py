"""Lecteur de fichiers : quels fichiers GoldenBrain lit lui-même, lesquels il confie à l'application du poste.

Rôle : tenir le registre extension → mode (`lecteur` | `application`) et genre d'affichage ; résoudre et valider
un chemin (racines autorisées, pas de traversée, liens symboliques résolus) ; renseigner un fichier (nom, taille,
date, mode) ; en lire une page de texte ; fournir le fichier brut avec les en-têtes d'isolement ; l'ouvrir dans
l'application par défaut du poste ou montrer son dossier.
Frontières : lecture seule du disque ; la seule action est `resultat.ouvrir_systeme` ; aucun tour d'agent. Les
racines sont : le vault, les arbres de travail des tâches, les dossiers ajoutés dans Réglages (`[lecteur]`), et
chaque fichier déclaré comme livrable ; depuis un appareil distant : le vault et les livrables seulement.
Invariants portés : INV-LECTEUR-1 (jamais hors racines ni d'exécution ; poste seulement pour l'application).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from . import depot, langues, livrables, resultat
from .vault import Conflit, ErreurOrch, Invalide, NonTrouve

GENRES = {
    "md": "md markdown",
    "texte": "txt text log ini cfg conf rst nfo",
    "csv": "csv tsv",
    "donnees": "json jsonl yaml yml toml xml",
    "code": "py pyw js mjs ts tsx jsx css scss sh bash zsh bat cmd ps1 c h cpp hpp java go rs rb php sql lua kt swift cs vue",
    "html": "html htm xhtml svg",
    "image": "png jpg jpeg gif webp bmp avif ico",
    "pdf": "pdf",
}
REGISTRE = {ext: genre for genre, exts in GENRES.items() for ext in exts.split()}  # extension → genre (le registre, en une table)
TEXTUELS = {"md", "texte", "csv", "donnees", "code"}
TYPES_BRUTS = {"html": "text/html; charset=utf-8", "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
               "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp", "avif": "image/avif", "ico": "image/x-icon", "pdf": "application/pdf"}
PAGE = 256 * 1024          # octets par page de texte : « charger la suite » relit la page d'après
BRUT_MAX = 64 * 1024 * 1024
DELAI_RACINES = 30.0       # s : durée de validité du relevé des racines
_cache: dict[str, tuple[float, tuple[list[Path], set[Path]]]] = {}


class HorsRacines(ErreurOrch):
    code = 403


def ext_de(p) -> str:
    return Path(p).suffix.lower().lstrip(".")


def mode_de(reglage, ext: str) -> tuple[str, str]:
    """(mode, genre) d'une extension : Réglages d'abord, puis le registre ; inconnue → application ; sans extension → texte."""
    if ext in reglage.application:
        return "application", ""
    if ext in reglage.lecteur:
        return "lecteur", REGISTRE.get(ext, "texte")
    if not ext:
        return "lecteur", "texte"
    return ("lecteur", REGISTRE[ext]) if ext in REGISTRE else ("application", "")


def registre(reglage) -> dict[str, str]:
    """Table complète extension → mode, telle que Réglages la montre (écarts compris)."""
    exts = set(REGISTRE) | set(reglage.lecteur) | set(reglage.application)
    return {e: mode_de(reglage, e)[0] for e in sorted(exts)}


# --- racines et chemins ------------------------------------------------------------------------------------

def _racines(moteur, distant: bool) -> tuple[list[Path], set[Path]]:
    """(dossiers lisibles, fichiers livrables) ; relevé gardé quelques secondes (il parcourt les tâches)."""
    vault = moteur.vault
    cle = f"{vault.racine}|{int(distant)}|{moteur.config.lecteur.dossiers}"
    if (c := _cache.get(cle)) and time.monotonic() - c[0] < DELAI_RACINES:
        return c[1]
    dossiers = [Path(vault.racine).resolve()]
    fichiers: set[Path] = set()
    if not distant:
        dossiers += [Path(d).expanduser().resolve() for d in moteur.config.lecteur.dossiers if Path(d).expanduser().is_dir()]
    for ident in vault.index()[0]:
        if not distant and (d := depot.dossier_de_travail(vault, ident)[0]) and (r := Path(d).resolve()) not in dossiers:
            dossiers.append(r)
        try:
            for x in livrables.propres(moteur, ident, False)["livrables"]:
                if x["type"] == "fichier":
                    fichiers.add(Path(x["cible"]).resolve())
        except ErreurOrch:
            continue
    _cache[cle] = (time.monotonic(), (dossiers, fichiers))
    return dossiers, fichiers


def _ignore(p: Path, base: Path) -> bool:
    return bool(set(p.relative_to(base).parts) & resultat.IGNORES)


def resoudre(moteur, chemin: str, distant: bool = False) -> Path:
    """Chemin réel d'un fichier lisible. INV-LECTEUR-1 : ni `..` ni octet nul, lien symbolique résolu avant le
    contrôle, et le résultat sous une racine autorisée (ou être un livrable déclaré) — sinon 403, jamais servi."""
    brut = str(chemin or "").strip()
    if not brut or len(brut) > 2000 or "\x00" in brut:
        raise Invalide(langues.t("serveur.lecteur.chemin_invalide"))
    if ".." in Path(brut.replace("\\", "/")).parts:
        raise Invalide(langues.t("serveur.lecteur.traversee"))
    p = Path(brut)
    vault = Path(moteur.vault.racine)
    try:
        reel = (p if p.is_absolute() else vault / p).resolve()
    except (OSError, RuntimeError) as e:
        raise Invalide(langues.t("serveur.lecteur.chemin_invalide")) from e
    dossiers, fichiers = _racines(moteur, distant)
    sous = next((b for b in dossiers if reel.is_relative_to(b)), None)
    if (sous is None or _ignore(reel, sous)) and reel not in fichiers:
        raise HorsRacines(langues.t("serveur.lecteur.hors_racines"))
    if not reel.is_file():
        raise NonTrouve(langues.t("serveur.lecteur.introuvable", nom=reel.name))
    return reel


def _binaire(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def _executable(p: Path) -> bool:
    """Ce que le système lancerait au lieu de l'afficher (INV-RESULTAT-1) : extension de programme ou bit d'exécution."""
    if p.suffix.lower() in resultat.EXECUTABLES:
        return True
    return sys.platform != "win32" and not p.suffix and bool(p.stat().st_mode & 0o111)


def info(moteur, chemin: str, distant: bool = False) -> dict:
    p = resoudre(moteur, chemin, distant)
    st = p.stat()
    ext = ext_de(p)
    mode, genre = mode_de(moteur.config.lecteur, ext)
    if mode == "lecteur" and genre in TEXTUELS and _binaire(p):
        mode, genre = "application", ""  # un « texte » qui n'en est pas : jamais affiché
    if mode == "lecteur" and genre in ("html", "image", "pdf") and st.st_size > BRUT_MAX:
        mode, genre = "application", ""
    vault = Path(moteur.vault.racine).resolve()
    return {"nom": p.name, "chemin": str(p), "vault": p.relative_to(vault).as_posix() if p.is_relative_to(vault) else "",
            "taille": st.st_size, "date": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"),
            "ext": ext, "mode": mode, "genre": genre, "executable": _executable(p),
            "application": not distant, "brut": genre in ("html", "image", "pdf") and (ext != "svg" or genre == "html")}


# --- lecture -----------------------------------------------------------------------------------------------

def lire(moteur, chemin: str, distant: bool = False, debut: int = 0, limite: int = PAGE) -> dict:
    """Une page de texte à partir de l'octet `debut` ; coupée à la dernière fin de ligne (rien de tronqué en plein
    caractère ni en plein rendu) ; `suite` dit s'il en reste."""
    i = info(moteur, chemin, distant)
    if i["mode"] != "lecteur" or i["genre"] not in TEXTUELS:
        raise Invalide(langues.t("serveur.lecteur.non_texte", nom=i["nom"]))
    debut, limite = max(0, int(debut)), min(max(1024, int(limite)), 4 * PAGE)
    taille = i["taille"]
    with Path(i["chemin"]).open("rb") as f:
        f.seek(debut)
        brut = f.read(limite)
    if debut + len(brut) < taille and (n := brut.rfind(b"\n")) >= 0:
        brut = brut[:n + 1]
    texte = brut.decode("utf-8", errors="replace")
    if debut == 0:
        texte = texte.removeprefix("﻿")
    fin = debut + len(brut)
    return {**i, "texte": texte, "debut": debut, "fin": fin, "suite": fin < taille}


def brut(moteur, chemin: str, distant: bool = False, externe: bool = False) -> tuple[Path, str, dict]:
    """(fichier, type de contenu, en-têtes d'isolement). HTML et SVG : CSP `sandbox` sans script, aucune ressource
    extérieure — sauf si l'utilisateur l'a demandé pour ce fichier (`externe`), et alors jamais de script."""
    i = info(moteur, chemin, distant)
    if i["mode"] != "lecteur" or i["genre"] not in ("html", "image", "pdf"):
        raise Invalide(langues.t("serveur.lecteur.non_brut", nom=i["nom"]))
    ext = i["ext"] if i["ext"] in TYPES_BRUTS else "html"
    dehors = "*" if externe and i["genre"] == "html" else ""
    csp = {"html": f"sandbox; default-src 'none'; style-src {dehors} 'unsafe-inline'; img-src {dehors} data:; font-src {dehors} data:; "
                   f"media-src {dehors}; frame-ancestors 'self'",
           "image": "sandbox; default-src 'none'; img-src 'self'; frame-ancestors 'self'",
           "pdf": "default-src 'none'; frame-ancestors 'self'"}[i["genre"]]
    return Path(i["chemin"]), TYPES_BRUTS[ext], {"Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff",
                                                  "X-Frame-Options": "SAMEORIGIN", "Cache-Control": "no-store"}


# --- application du poste ----------------------------------------------------------------------------------

def _application(p: Path) -> str:
    """Nom de l'application par défaut quand le système le dit (Linux : xdg-mime) ; vide sinon."""
    if not sys.platform.startswith("linux"):
        return ""
    try:
        def q(*a):
            return subprocess.run(a, capture_output=True, text=True, encoding="utf-8", timeout=2, check=False).stdout.strip()
        mime = q("xdg-mime", "query", "filetype", str(p))
        bureau = q("xdg-mime", "query", "default", mime) if mime else ""
    except (OSError, subprocess.SubprocessError):
        return ""
    return bureau.removesuffix(".desktop").rsplit(".", 1)[-1].replace("-", " ") if bureau else ""


def ouvrir_application(moteur, chemin: str) -> dict:
    """Geste du poste seul (la route refuse le distant et les agents). Un programme ou un script n'est jamais lancé :
    son dossier s'ouvre à la place. Un dossier non lisible n'a pas de chemin ici : on part d'un fichier résolu."""
    p = resoudre(moteur, chemin, False)
    cible, message = p, ""
    if _executable(p):
        cible, message = p.parent, langues.t("serveur.resultat.dossier_a_la_place")
    try:
        resultat.ouvrir_systeme(str(cible))
    except (OSError, webbrowser.Error) as e:
        raise Conflit(langues.t("serveur.resultat.echec", libelle=p.name)) from e
    if not message:
        app = _application(p)
        message = langues.t("serveur.lecteur.ouvert_dans", nom=p.name, application=app) if app else langues.t("serveur.lecteur.ouvert", nom=p.name)
    return {"message": message}


def afficher_dossier(moteur, chemin: str) -> dict:
    p = resoudre(moteur, chemin, False)
    try:
        resultat.ouvrir_systeme(str(p.parent))
    except (OSError, webbrowser.Error) as e:
        raise Conflit(langues.t("serveur.resultat.echec", libelle=p.parent.name)) from e
    return {"message": langues.t("serveur.lecteur.dossier_ouvert", nom=p.parent.name)}


def vider_cache() -> None:
    _cache.clear()  # après un changement de réglage ou en test
