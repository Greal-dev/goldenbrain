"""Traduction des messages du serveur destinés à l'utilisateur (INV-LANGUE-1).

Rôle : `t(cle, **params)` rend le texte de `cle` dans la langue réglée (`[interface] langue`), à partir des
dictionnaires partagés avec l'interface (`web/langues/<code>.json`, source `fr`).
Frontières : ne traduit que des textes montrés à l'utilisateur ; identifiants, clés de configuration, statuts
du vault et noms de commandes ne passent jamais par ici. Aucune écriture.
Invariants portés : INV-LANGUE-1 (une seule source de libellés : les quatre dictionnaires, aux clés identiques).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from .config import RACINE_DEPOT

DOSSIER = RACINE_DEPOT / "web" / "langues"
LANGUES = {"fr": "français", "en": "English", "de": "Deutsch", "es": "español"}
SOURCE = "fr"
_courante = SOURCE  # serveur mono-utilisateur : une langue réglée pour tout le processus
PARAM = re.compile(r"\{(\w+)\}")


@lru_cache(maxsize=len(LANGUES))
def dictionnaire(code: str) -> dict[str, str]:
    return json.loads((DOSSIER / f"{code}.json").read_text(encoding="utf-8"))


def regler(code: str | None) -> None:
    """Langue des messages ; vide ou inconnue : français (langue source)."""
    global _courante
    _courante = code if code in LANGUES else SOURCE


def courante() -> str:
    return _courante


def t(cle: str, langue: str | None = None, /, **params) -> str:
    """Texte de `cle` dans `langue` (défaut : langue réglée), `{nom}` remplacés ; clé absente : la clé.
    `langue` est positionnel seul : un paramètre de texte peut s’ppeler `langue`."""
    code = langue if langue in LANGUES else _courante
    texte = dictionnaire(code).get(cle) or dictionnaire(SOURCE).get(cle) or cle
    return PARAM.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), texte)


def consigne_langue(langue: str | None = None) -> str:
    """Ligne ajoutée aux consignes d'agent : répondre dans la langue de l'utilisateur."""
    return t("serveur.consigne.langue", langue, langue=LANGUES[langue if langue in LANGUES else _courante])
