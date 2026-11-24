"""Second cerveau d'un poste : où est le vault, l'a-t-on choisi, comment en changer sans toucher `config.toml` à la main.

Rôle : état « second cerveau configuré sur ce poste » (`<donnees>/etat/cerveau.json`), examen d'un dossier candidat
(existe, inscriptible, vide, déjà servi par une autre instance), navigation dans les dossiers du poste pour le
sélecteur de l'interface, écriture de la seule clé `[vault] racine` de `config.toml`.
Frontières : n'importe rien d'un vault ouvert ; n'écrit dans un dossier du vault candidat que pour le créer vide (et un fichier temporaire, aussitôt supprimé, pour éprouver l'écriture) ;
routes dans `api_cerveau.py` ; le parcours côté interface est `web/cerveau.js`.
Invariants portés : INV-CERVEAU-1 (état propre au poste, indépendant du contenu du vault), INV-CERVEAU-2 (changement de
dossier : examen, verrou d'instance, une clé écrite, redémarrage).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from . import fiches, langues
from .vault import Invalide
from .verrou_config import sous_verrou_config

NOTES_MAX = 2000  # on s'arrête de compter : l'écran dit « au moins N », pas un total exact
DOSSIERS_MAX = 400
CLE_RACINE = re.compile(r"^\s*racine\s*=")


def fichier(config) -> Path:
    return config.donnees / "etat" / "cerveau.json"


def etat(config) -> dict:
    """INV-CERVEAU-1 : `{"etat": ""|"fait"|"differe", "parcours": bool, "vault": str}`. Sans fichier, une installation qui a déjà
    vécu (états d'accueil ou de premiers pas présents) est tenue pour configurée : une mise à jour n'impose rien à qui est installé."""
    try:
        brut = json.loads(fichier(config).read_text(encoding="utf-8"))
        return {"etat": str(brut.get("etat") or ""), "parcours": bool(brut.get("parcours")), "vault": str(brut.get("vault") or "")}
    except (OSError, ValueError):
        pass
    dossier = config.donnees / "etat"
    herite = any((dossier / f).exists() for f in ("accueil.json", "premiers-pas.json"))
    return {"etat": "fait" if herite else "", "parcours": False, "vault": ""}


def poser(config, valeur: str, parcours: bool = False, vault: str = "") -> None:
    fichier(config).parent.mkdir(parents=True, exist_ok=True)
    fiches.ecrire_atomique(fichier(config), json.dumps({"etat": valeur, "parcours": parcours, "vault": vault or str(config.vault.racine)}))


def parcours_ouvert(config, vide: bool) -> bool:
    """Accueil et premiers pas se proposent seulement une fois le second cerveau réglé (jamais pendant « Plus tard »), et sur un
    vault vide ou au cours du parcours qui vient d'être déroulé (un vault existant se reprend aussi : audit du 23/11)."""
    e = etat(config)
    return e["etat"] == "fait" and (vide or e["parcours"])


def _ecrivable(p: Path) -> bool:
    """Un dossier absent est écrivable si son plus proche parent existant l'est (il sera créé)."""
    while not p.exists():
        if p.parent == p:
            return False
        p = p.parent
    if not (p.is_dir() and os.access(p, os.W_OK | os.X_OK)):
        return False
    essai = p / f".goldenbrain-essai-{os.getpid()}"  # sous Windows `os.access` ignore les droits réels (ACL, dossier protégé) : seul un essai d'écriture tranche
    try:
        with open(essai, "xb"):
            pass
        essai.unlink()
        return True
    except OSError:
        return False


def _normaliser(chemin: str) -> Path:
    brut = (chemin or "").strip()
    if not brut:
        raise Invalide(langues.t("serveur.cerveau.chemin_vide"))
    p = Path(brut).expanduser()
    if not p.is_absolute():
        raise Invalide(langues.t("serveur.cerveau.chemin_relatif", chemin=brut))
    return Path(os.path.normpath(p))


def _occupe(racine: Path) -> dict | None:
    """INV-CERVEAU-2 : une autre instance sert-elle déjà ce vault ? (même verrou que le démarrage ; libéré aussitôt)."""
    from .__main__ import fichier_verrou, prendre_verrou  # import tardif : `__main__` importe l'application
    try:
        f = prendre_verrou(fichier_verrou(racine), racine, 0)
    except SystemExit as e:
        return {"detail": str(e)}
    f.close()
    return None


def examiner(config, chemin: str) -> dict:
    """Ce qu'on peut dire d'un dossier candidat, sans rien écrire. `ok` = utilisable tel quel (ou créable)."""
    from . import squelette
    p = _normaliser(chemin)
    existe, dossier = p.exists(), p.is_dir()
    actuel = p.resolve() == config.vault.racine.resolve()
    r = {"chemin": str(p), "existe": existe, "dossier": dossier or not existe, "ecrivable": _ecrivable(p), "actuel": actuel,
         "vide": True, "notes": 0, "obsidian": (p / ".obsidian").is_dir(), "occupe": None, "erreur": ""}
    if existe and not dossier:
        r["erreur"] = langues.t("serveur.cerveau.pas_un_dossier", chemin=str(p))
    elif not r["ecrivable"]:
        r["erreur"] = langues.t("serveur.cerveau.non_ecrivable", chemin=str(p))
    elif dossier:
        r["vide"] = squelette.vide(p, config.vault.arrivee)
        r["notes"] = _compter(p)
        if not actuel:
            r["occupe"] = _occupe(p)
            if r["occupe"]:
                r["erreur"] = langues.t("serveur.cerveau.occupe", chemin=str(p))
    r["ok"] = not r["erreur"]
    return r


def _compter(racine: Path) -> int:
    n = 0
    for d, noms, fichiers in os.walk(racine):
        noms[:] = [x for x in noms if not x.startswith(".")]
        n += sum(1 for f in fichiers if f.endswith(".md"))
        if n >= NOTES_MAX:
            break
    return n


def _dossier(e: Path) -> bool:
    try:
        return e.is_dir()
    except OSError:  # racine d'un disque Windows : entrées système refusées au simple examen
        return False


def lister(chemin: str) -> dict:
    """Sous-dossiers visibles d'un dossier (sélecteur de l'interface) ; vide = dossier personnel. Poste seulement (INV-ACCUEIL-1)."""
    p = _normaliser(chemin) if (chemin or "").strip() else Path.home()
    try:
        enfants = sorted((e for e in p.iterdir() if not e.name.startswith(".") and _dossier(e)), key=lambda e: e.name.lower())
    except OSError:
        raise Invalide(langues.t("serveur.cerveau.illisible", chemin=str(p))) from None
    racines = [f"{c}:\\" for c in "CDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{c}:\\").exists()] if sys.platform == "win32" else ["/"]
    return {"chemin": str(p), "parent": str(p.parent) if p.parent != p else "", "maison": str(Path.home()), "racines": racines,
            "dossiers": [{"nom": e.name, "chemin": str(e)} for e in enfants[:DOSSIERS_MAX]], "tronque": len(enfants) > DOSSIERS_MAX}


@sous_verrou_config
def poser_racine(config_toml: Path, racine: str) -> None:
    """INV-CERVEAU-2 : remplace (ou ajoute) la seule clé `racine` de `[vault]` ; le reste du fichier est restitué tel quel."""
    texte = config_toml.read_bytes().decode("utf-8") if config_toml.is_file() else ""
    eol = "\r\n" if "\r\n" in texte else "\n"
    ligne = f"racine = {json.dumps(racine, ensure_ascii=False)}{eol}"  # chaîne TOML de base : barres obliques inverses échappées
    lignes = texte.splitlines(keepends=True)
    debut = next((i for i, x in enumerate(lignes) if x.strip() == "[vault]"), None)
    if debut is None:
        if lignes and not lignes[-1].endswith(("\n", "\r")):
            lignes[-1] += eol
        lignes += ([eol] if lignes else []) + [f"[vault]{eol}", ligne]
    else:
        fin = next((j for j in range(debut + 1, len(lignes)) if lignes[j].lstrip().startswith("[")), len(lignes))
        place = next((j for j in range(debut + 1, fin) if CLE_RACINE.match(lignes[j])), None)
        if place is None:
            lignes.insert(debut + 1, ligne)
        else:
            lignes[place] = ligne
    fiches.ecrire_atomique(config_toml, "".join(lignes))


def appliquer(config, chemin: str, creer: bool) -> dict:
    """Valide le dossier (créé s'il est neuf et demandé), écrit `[vault] racine` s'il change. `redemarrage` dit si le serveur doit
    repartir pour servir le nouveau vault : le verrou d'instance et tous les index se règlent au démarrage (INV-INSTANCE-1)."""
    r = examiner(config, chemin)
    if not r["ok"]:
        raise Invalide(r["erreur"])
    p = Path(r["chemin"])
    if not r["existe"]:
        if not creer:
            raise Invalide(langues.t("serveur.cerveau.absent", chemin=str(p)))
        p.mkdir(parents=True, exist_ok=True)
    change = not r["actuel"]
    if change:
        if config.chemin is None:
            raise Invalide(langues.t("serveur.cerveau.sans_config"))
        poser_racine(config.chemin, str(p))
    return {"chemin": str(p), "redemarrage": change, "cree": not r["existe"]}
