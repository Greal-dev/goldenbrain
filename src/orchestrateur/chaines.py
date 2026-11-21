"""Modèles de chaîne : suites de phases réutilisables, écrites en Markdown (en-tête YAML).

Rôle : lire, valider et enregistrer les modèles de chaîne. Deux sources : les modèles intégrés du dépôt
(`chaines/`, traduits sous `chaines/<langue>/`) et ceux de l'utilisateur, dans le vault (`_meta/chaines/`),
qui l'emportent à identifiant égal. Un modèle : titre, résumé, contexte commun (le corps), phases (titre,
consigne, documents d'entrée, livrable, assistant et modèle d'IA, validation humaine après la phase),
et facultativement un dossier surveillé du vault avec le projet où lancer la chaîne.
Frontières : ne crée aucune tâche et n'exécute rien (`chaines_execution.py`) ; n'écrit que dans le
dossier des chaînes du vault ; un fichier illisible est écarté, jamais fatal.
Invariants portés : INV-CHAINE-2, INV-LANGUE-1.
"""

from __future__ import annotations

import logging
from pathlib import Path, PureWindowsPath

import yaml

from . import fiches, langues
from .vault import Invalide, NonTrouve, slugifier

INTEGRES = Path(__file__).resolve().parents[2] / "chaines"
DOSSIER_VAULT = "_meta/chaines"
MAX_FICHIERS, MAX_OCTETS, MAX_PHASES = 40, 60_000, 20
CHAMPS_PHASE = {"titre": 120, "consigne": 8000, "entrees": 1000, "livrable": 1000, "harnais": 40, "modele": 60}
log = logging.getLogger(__name__)


def _texte(v, borne: int) -> str:
    return str(v if v is not None else "").strip()[:borne]


def phase_valide(p) -> dict:
    """Une phase normalisée ; titre et consigne obligatoires (INV-CHAINE-2)."""
    if not isinstance(p, dict):
        raise Invalide(langues.t("serveur.chaines.phase_invalide"))
    ph = {k: _texte(p.get(k), b) for k, b in CHAMPS_PHASE.items()}
    if not ph["titre"] or not ph["consigne"]:
        raise Invalide(langues.t("serveur.chaines.phase_incomplete"))
    ph["validation"] = bool(p.get("validation"))
    return ph


def normaliser(d: dict) -> dict:
    """Modèle normalisé `{titre, resume, contexte, phases, surveiller, conteneur}` ; Invalide sinon."""
    titre = _texte(d.get("titre"), 120)
    phases = d.get("phases")
    if not titre:
        raise Invalide(langues.t("serveur.chaines.titre_requis"))
    if not isinstance(phases, list) or not phases:
        raise Invalide(langues.t("serveur.chaines.phases_requises"))
    if len(phases) > MAX_PHASES:
        raise Invalide(langues.t("serveur.chaines.trop_de_phases", n=MAX_PHASES))
    surveiller = _texte(d.get("surveiller"), 300).replace("\\", "/")
    if surveiller.startswith("/") or PureWindowsPath(surveiller).drive or ".." in Path(surveiller).parts:
        raise Invalide(langues.t("serveur.chaines.surveiller_relatif"))  # INV-CHAINE-4 : dans le vault seulement
    return {"titre": titre, "resume": _texte(d.get("resume"), 300), "contexte": _texte(d.get("contexte"), 8000),
            "phases": [phase_valide(p) for p in phases], "surveiller": surveiller.rstrip("/"),
            "conteneur": _texte(d.get("conteneur"), 300)}


def lire(fichier: Path, origine: str) -> dict | None:
    """Modèle `{id, origine, …}` lu d'un fichier, ou None s'il n'en est pas un (écarté, jamais fatal)."""
    try:
        if fichier.is_symlink() or fichier.stat().st_size > MAX_OCTETS:
            return None
        texte = fichier.read_text(encoding="utf-8")
        lignes_fm, _, _, corps = fiches.decouper(texte)  # par lignes : un « --- » dans une consigne n'est pas une borne
        fm = yaml.safe_load("".join(lignes_fm or [])) or {}
        if not isinstance(fm, dict):
            return None
        lignes = corps.strip().splitlines()
        contexte = "\n".join(lignes[1:] if lignes and lignes[0].startswith("# ") else lignes).strip()
        m = normaliser({**fm, "contexte": contexte})
    except (OSError, ValueError, yaml.YAMLError, Invalide) as e:
        log.warning("chaîne écartée %s : %s", fichier.name, e)
        return None
    ordre = fm.get("ordre")
    return {"id": fichier.stem, "origine": origine, "ordre": ordre if isinstance(ordre, int) else 999, **m}


def _integres(langue: str) -> dict[str, dict]:
    if not INTEGRES.is_dir():
        return {}
    sortie = {}
    for f in sorted(INTEGRES.glob("*.md"))[:MAX_FICHIERS]:
        autre = f.parent / langue / f.name  # INV-LANGUE-1 : version traduite si elle existe
        m = (lire(autre, "integre") if langue != langues.SOURCE and autre.is_file() else None) or lire(f, "integre")
        if m:
            sortie[m["id"]] = m
    return sortie


def dossier_vault(racine: Path) -> Path:
    return racine / DOSSIER_VAULT


def lister(racine: Path, langue: str | None = None) -> list[dict]:
    """INV-CHAINE-2 : modèles intégrés puis ceux du vault, qui les remplacent à identifiant égal."""
    modeles = _integres(langue or langues.courante())
    d = dossier_vault(racine)
    if d.is_dir():
        for f in sorted(d.glob("*.md"))[:MAX_FICHIERS]:
            if m := lire(f, "vault"):
                modeles[m["id"]] = m
    return sorted(modeles.values(), key=lambda m: (m["ordre"], m["titre"].casefold()))


def modele(racine: Path, ident: str) -> dict:
    for m in lister(racine):
        if m["id"] == ident:
            return m
    raise NonTrouve(langues.t("serveur.chaines.inconnue", id=ident))


def rendre(m: dict) -> str:
    """Texte Markdown d'un modèle : en-tête YAML (phases comprises), corps = contexte commun."""
    fm = {"type": "chaine", "titre": m["titre"], "resume": m["resume"]}
    fm |= {k: m[k] for k in ("surveiller", "conteneur") if m.get(k)}
    fm["phases"] = [{k: v for k, v in p.items() if v not in ("", None)} for p in m["phases"]]
    entete = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=100)
    corps = f"# {m['titre']}\n\n{m['contexte']}".rstrip()
    return f"---\n{entete}---\n\n{corps}\n"


def enregistrer(racine: Path, donnees: dict, ident: str = "") -> dict:
    """Écrit le modèle dans le vault (`_meta/chaines/<id>.md`) ; un modèle intégré modifié y est copié."""
    m = normaliser(donnees)
    ident = slugifier(ident or m["titre"])
    d = dossier_vault(racine)
    d.mkdir(parents=True, exist_ok=True)
    fiches.ecrire_atomique(d / f"{ident}.md", rendre(m))
    return {"id": ident, "origine": "vault", "ordre": 999, **m}


def retirer(racine: Path, ident: str) -> None:
    """Retire un modèle du vault (geste de l'utilisateur) ; un modèle intégré ne se retire pas."""
    f = dossier_vault(racine) / f"{slugifier(ident)}.md"
    if not f.is_file():
        raise NonTrouve(langues.t("serveur.chaines.inconnue", id=ident))
    f.unlink()
