"""Guide d'utilisation : registre des sections attendues, contrôle de complétude, route `GET /api/guide`.

Rôle : un seul fichier source, `docs/GUIDE.md`, lu par l'humain (interface, rendu par `web/md.js`), par
l'agent (`orch guide`, `GET /api/guide`) et vérifié par la porte (`scripts/check.py`).
Frontières : ne rend aucun HTML (l'interface rend le Markdown) ; n'écrit rien.
Invariants portés : INV-GUIDE-1 (chaque écran ou réglage du registre a sa section dans le guide, sous un
titre dont l'ancre est stable) ; INV-LANGUE-1 (GUIDE.<langue>.md, traduction du guide français, porte chaque
ancre du registre en `{#ancre}` au bout du titre traduit : le « ? » d'un écran tombe sur la même section).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from . import langues
from .config import RACINE_DEPOT

FICHIER = RACINE_DEPOT / "docs" / "GUIDE.md"

# INV-GUIDE-1 : ancre → titre exact de la section. Un écran ou un réglage visible ajouté à l'interface
# s'inscrit ici ; la porte échoue tant que le guide n'a pas sa section. Les ancres servent à l'aide
# contextuelle (« ? » d'un écran) : ne pas les renommer sans mettre à jour les appelants de `web/guide.js`.
SECTIONS: dict[str, str] = {
    "installer": "Installer",
    "en-un-clic": "En un clic",
    "linux": "Linux",
    "windows": "Windows",
    "service-au-demarrage-linux": "Service au démarrage (Linux)",
    "connecter-les-harnais": "Connecter les assistants IA",
    "premiers-pas": "Premiers pas",
    "organiser-votre-second-cerveau": "Organiser votre second cerveau",
    "fonctions-par-ecran": "Fonctions par écran",
    "reprise-de-vos-projets": "Reprise de vos projets",
    "arbre-et-listes": "Arbre et listes",
    "tache": "Tâche",
    "mode-discussion": "Mode discussion",
    "decisions": "Décisions",
    "aujourd-hui": "Aujourd'hui",
    "en-cours": "En cours",
    "compagnon": "Compagnon mobile",
    "notes": "Notes",
    "routines": "Routines",
    "chaines": "Chaînes",
    "equipe": "Équipe",
    "reglages": "Réglages",
    "mise-a-jour-d-un-clic": "Mise à jour d'un clic",
    "manager": "Manager",
    "telegram": "Telegram",
    "executeurs-distants": "Ordinateurs d'appoint",
    "depannage": "Dépannage",
    "pour-un-agent-ia": "Pour un agent IA",
}
TITRE = re.compile(r"^#{2,3}\s+(.+?)\s*#*\s*$", re.M)
EXPLICITE = re.compile(r"\s*\{#([\w-]+)\}$")  # ancre fixée au bout du titre (titre reformulé, guide traduit)
DATE = re.compile(r"^Mis à jour le \d{4}-\d{2}-\d{2}\.$", re.M)


def ancre(titre: str) -> str:
    """Même calcul que `ancre()` de `web/guide.js` : minuscules, sans accents, tirets."""
    sans = "".join(c for c in unicodedata.normalize("NFD", titre) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sans.lower()).strip("-")


def lire(fichier: Path = FICHIER) -> str:
    return fichier.read_text(encoding="utf-8")


def fichier(langue: str) -> Path:
    """Guide de la langue (`GUIDE.en.md`…) ; le français est la source `GUIDE.md`."""
    return FICHIER if langue == langues.SOURCE else FICHIER.with_suffix(f".{langue}.md")


def manquements_traduits() -> list[str]:
    """INV-LANGUE-1 : chaque guide traduit existe et porte toutes les ancres du registre."""
    erreurs = []
    for code in langues.LANGUES:
        f = fichier(code)
        if code == langues.SOURCE:
            continue
        if not f.is_file():
            erreurs.append(f"guide : docs/{f.name} absent")
            continue
        texte = lire(f)
        erreurs += [f"guide : docs/{f.name} n'a pas de titre portant {{#{a}}}" for a in SECTIONS if f"{{#{a}}}" not in texte]
    return erreurs


def manquements(texte: str, sections: dict[str, str] = SECTIONS) -> list[str]:
    """INV-GUIDE-1 : sections du registre absentes du guide, ancres instables, date de mise à jour absente."""
    titres = {}  # titre affiché → ancre : `{#ancre}` explicite (titre reformulé, ancre stable) ou calculée
    for brut in TITRE.findall(texte):
        m = EXPLICITE.search(brut)
        titre = (brut[:m.start()] if m else brut).replace("’", "'")
        titres[titre] = m.group(1) if m else ancre(titre)
    erreurs = [f"guide : section « {t} » absente (registre SECTIONS de guide.py)"
               for t in sections.values() if t not in titres]
    erreurs += [f"guide : l'ancre « {a} » ne correspond pas au titre « {t} »"
                for a, t in sections.items() if t in titres and titres[t] != a]
    if not DATE.search(texte):
        erreurs.append("guide : ligne « Mis à jour le AAAA-MM-JJ. » absente")
    return erreurs


def routes() -> APIRouter:
    r = APIRouter()

    @r.get("/api/guide", response_class=PlainTextResponse)
    async def guide(langue: str = ""):
        # INV-LANGUE-1 : guide de la langue demandée (sinon réglée) ; traduction absente → guide français.
        f = fichier(langue if langue in langues.LANGUES else langues.courante())
        return PlainTextResponse(lire(f if f.is_file() else FICHIER), media_type="text/markdown; charset=utf-8")

    return r
