"""Voir le résultat : ce qu'une tâche a produit (fichiers, site local, dossier de travail) et son ouverture.

Rôle : relever, pour une tâche, les endroits où trouver ce que l'assistant IA a produit — champ Résultat
(et Essai, Fait) de la fiche, fichiers écrits au dernier tour, `index.html` et dossier de travail —, puis
ouvrir l'un d'eux avec l'application par défaut du système. Chaque élément est un `dict` {genre
(fichier | site | dossier), cible, libelle, origine, ouvrable}.
Frontières : lecture seule du vault et du disque ; la seule action est l'appel au système (`ouvrir_systeme`,
remplaçable en test). Une cible n'est jamais fournie par le client : il désigne un élément de la liste que
le serveur recalcule. Aucun appel réseau ; une adresse n'est retenue que si elle désigne ce poste.
Invariants portés : INV-RESULTAT-1 (poste seulement ; cibles bornées ; jamais d'exécution d'un programme).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from . import depot, langues
from .vault import Conflit, NonTrouve

# Libellés visibles : chaque entrée se résout à l'appel, dans la langue réglée (INV-LANGUE-1).
TEXTES = {
    "rien": lambda **p: langues.t("serveur.resultat.rien", **p),
    "ouvert": lambda **p: langues.t("serveur.resultat.ouvert", **p),
    "dossier_a_la_place": lambda **p: langues.t("serveur.resultat.dossier_a_la_place", **p),
    "echec": lambda **p: langues.t("serveur.resultat.echec", **p),
    "disparu": lambda **p: langues.t("serveur.resultat.disparu", **p),
    "site_fiche": lambda **p: langues.t("serveur.resultat.site_fiche", **p),
    "site_index": lambda **p: langues.t("serveur.resultat.site_index", **p),
    "fichier": lambda **p: langues.t("serveur.resultat.fichier", **p),
    "dossier_travail": lambda **p: langues.t("serveur.resultat.dossier_travail", **p),
    "dossier_fichier": lambda **p: langues.t("serveur.resultat.dossier_fichier", **p),
}

LIMITE_FICHIERS = 6      # fichiers du dernier tour retenus (les plus récents)
LIMITE_TOTAL = 12
CHAMPS_FICHE = ("resultat", "essai", "fait")
OUTILS_ECRITURE = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
IGNORES = {".git", "node_modules", "__pycache__", ".claude", ".venv", "venv"}
# Ce que le système exécuterait au lieu de l'afficher : jamais ouvert d'un clic (INV-RESULTAT-1).
EXECUTABLES = {".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta",
               ".lnk", ".scr", ".jar", ".reg", ".pif", ".cpl", ".sh", ".bash", ".run", ".appimage", ".desktop", ".command",
               ".py", ".pyw", ".pl", ".rb", ".php", ".dll", ".app", ".workflow"}
EXT_CONNUES = r"html?|md|txt|pdf|png|jpe?g|gif|svg|csv|xlsx?|docx?|pptx?|json|yaml|yml|css|ts|tsx|jsx|mp3|mp4|zip"
URL_RE = re.compile(r"https?://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])(?::\d{1,5})?(?:/[^\s`)>\]\"']*)?")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
JETON_RE = re.compile(rf"(?:~|[A-Za-z]:[\\/]|/)[^\s`\"'<>|*?]+|[\w][\w.\-]*(?:/[\w.\-]+)+/?|[\w][\w\-]*\.(?:{EXT_CONNUES})\b")


def ouvrir_systeme(cible: str, url: bool = False) -> None:
    """Ouvre `cible` avec l'application par défaut du système (navigateur pour une adresse)."""
    if url:
        webbrowser.open_new_tab(cible)
    elif sys.platform == "win32":
        os.startfile(cible)  # noqa: S606 — cible choisie parmi des éléments déjà filtrés
    elif sys.platform == "darwin":
        subprocess.Popen(["open", cible], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["xdg-open", cible], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _racines(vault, dossier: str | None) -> list[Path]:
    """Endroits où une cible peut se trouver : dossier de travail, vault, dossier personnel, temporaire."""
    bases = [Path(dossier)] if dossier else []
    bases += [Path(vault.racine), Path.home(), Path(tempfile.gettempdir())]
    return [b.resolve() for b in bases]


def _chemin(jeton: str, dossier: str | None, racines: list[Path]) -> Path | None:
    """Le jeton s'il désigne un fichier ou dossier existant sous une racine permise, sinon None."""
    jeton = jeton.strip().strip("`\"'").rstrip(".,;:)!?")
    if not jeton or jeton.startswith(("http://", "https://")):
        return None
    p = Path(os.path.expanduser(jeton))
    if not p.is_absolute() and dossier:
        p = Path(dossier) / p
    try:
        p = p.resolve()
        if p.exists() and any(p.is_relative_to(r) for r in racines) and not (set(p.parts) & IGNORES):
            return p
    except (OSError, ValueError):
        pass
    return None


def _adresses(textes: list[str]) -> list[str]:
    """Adresses de ce poste citées dans la fiche (serveur de développement), sans doublon."""
    vues: list[str] = []
    for texte in textes:
        for m in URL_RE.finditer(texte):
            url = m.group(0).rstrip(".,;:)")
            if urlsplit(url).hostname and url not in vues:
                vues.append(url)
    return vues


def _chemins_fiche(textes: list[str], dossier: str | None, racines: list[Path]) -> list[Path]:
    out: list[Path] = []
    for texte in textes:
        sans_url = URL_RE.sub(" ", texte)
        jetons = BACKTICK_RE.findall(sans_url) + JETON_RE.findall(BACKTICK_RE.sub(" ", sans_url))
        for j in jetons:
            if (p := _chemin(j, dossier, racines)) and p not in out:
                out.append(p)
    return out


def _fichiers_du_dernier_tour(moteur, ident: str, dossier: str | None, racines: list[Path]) -> list[Path]:
    """Fichiers écrits depuis le dernier message de l'utilisateur, relevés dans la séance de l'assistant
    (transcript du harnais, s'il en tient un lisible) ; les plus récents d'abord."""
    t = moteur.vault.tache(ident)
    session = str(t.fm.get("session") or "")
    nom = str(t.fm.get("harnais") or moteur.config.moteur.harnais_defaut)
    fabrique = moteur.registre.get(nom)
    if not session or not fabrique:
        return []
    try:
        h = fabrique(depot.conf_harnais(moteur.vault, moteur.config.harnais.get(nom, {}), ident))
        fichier = getattr(h, "chemin_transcript", lambda _s: "")(session)
        if not fichier:
            return []
        ecrits: list[str] = []
        for ligne in Path(fichier).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                brut = json.loads(ligne)
            except ValueError:
                continue
            blocs = (brut.get("message") or {}).get("content") if isinstance(brut, dict) else None
            if not isinstance(blocs, list):
                continue
            if brut.get("type") == "user" and any(b.get("type") == "text" for b in blocs if isinstance(b, dict)):
                ecrits = []  # nouveau tour : on ne garde que ce qui suit
            elif brut.get("type") == "assistant":
                for b in blocs:
                    cle = OUTILS_ECRITURE.get(b.get("name", "")) if isinstance(b, dict) and b.get("type") == "tool_use" else None
                    if cle and isinstance(v := (b.get("input") or {}).get(cle), str):
                        ecrits.append(v)
    except (OSError, ValueError, TypeError, AttributeError):
        return []
    out: list[Path] = []
    for brut in reversed(ecrits):
        if (p := _chemin(brut, dossier, racines)) and p.is_file() and p != t.chemin.resolve() and p not in out:
            out.append(p)
    return out[:LIMITE_FICHIERS]


def _element_fichier(p: Path, origine: str) -> dict:
    ouvrable = p.is_dir() or p.suffix.lower() not in EXECUTABLES
    if p.is_dir():
        return {"genre": "dossier", "cible": str(p), "libelle": TEXTES["dossier_travail"](nom=p.name or str(p))
                if origine == "dossier" else TEXTES["fichier"](nom=p.name), "origine": origine, "ouvrable": True}
    genre = "site" if p.name.lower() == "index.html" else "fichier"
    libelle = TEXTES["site_index" if genre == "site" else "fichier"](nom=p.name)
    return {"genre": genre, "cible": str(p), "libelle": libelle, "origine": origine, "ouvrable": ouvrable}


def chercher(moteur, ident: str) -> dict:
    """INV-RESULTAT-1 : {elements, message} — message non vide si rien n'est trouvé."""
    vault = moteur.vault
    fiche = vault.tache(ident).fiche
    dossier, _ = depot.dossier_de_travail(vault, ident)
    racines = _racines(vault, dossier)
    textes = [str(fiche.get(c) or "") for c in CHAMPS_FICHE]
    elements: list[dict] = []

    def ajouter(e: dict) -> None:
        if all(e["cible"] != x["cible"] for x in elements):
            elements.append(e)

    for url in _adresses(textes):
        ajouter({"genre": "site", "cible": url, "libelle": TEXTES["site_fiche"](cible=url.split("//", 1)[1]),
                 "origine": "fiche", "ouvrable": True})
    for p in _chemins_fiche(textes, dossier, racines):
        ajouter(_element_fichier(p, "fiche"))
    if dossier and (index := Path(dossier) / "index.html").is_file():
        ajouter(_element_fichier(index.resolve(), "dossier"))
    for p in _fichiers_du_dernier_tour(moteur, ident, dossier, racines):
        ajouter(_element_fichier(p, "dernier_tour"))
    if dossier:
        ajouter(_element_fichier(Path(dossier).resolve(), "dossier"))
    elements = elements[:LIMITE_TOTAL]
    return {"elements": elements, "message": "" if elements else TEXTES["rien"]()}


def ouvrir(moteur, ident: str, cible: str) -> dict:
    """Ouvre l'élément `cible` de la liste recalculée ; {ouvert, message}. Un fichier qui pourrait s'exécuter
    n'est jamais lancé : son dossier est ouvert à la place."""
    element = next((e for e in chercher(moteur, ident)["elements"] if e["cible"] == cible), None)
    if element is None:
        raise NonTrouve(TEXTES["disparu"]())
    message = TEXTES["ouvert"](libelle=element["libelle"])
    a_ouvrir = element["cible"]
    if not element["ouvrable"]:
        a_ouvrir = str(Path(a_ouvrir).parent)
        message = TEXTES["dossier_a_la_place"]()
    try:
        ouvrir_systeme(a_ouvrir, url=element["genre"] == "site" and a_ouvrir.startswith("http"))
    except (OSError, webbrowser.Error) as e:
        raise Conflit(TEXTES["echec"](libelle=element["libelle"])) from e
    return {"ouvert": element, "message": message}
