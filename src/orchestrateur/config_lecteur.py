"""Réglage du lecteur de fichiers : `[lecteur]` de `config.toml`.

Rôle : porter les dossiers lisibles ajoutés par l'utilisateur et les écarts au registre extension → mode
(`lecteur` ouvre dans GoldenBrain, `application` confie le fichier à l'application du poste).
Frontières : données seules, sans import du paquet (`config` l'importe) ; la logique est dans `lecteur`.
Invariants portés : INV-LECTEUR-1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EXT = re.compile(r"[a-z0-9]{1,12}")


@dataclass
class ConfigLecteur:
    """`dossiers` : racines lisibles en plus du vault et des arbres de travail ; `lecteur` / `application` :
    extensions (sans point) forcées vers l'un ou l'autre mode."""
    dossiers: list[str] = field(default_factory=list)
    lecteur: list[str] = field(default_factory=list)
    application: list[str] = field(default_factory=list)

    def __post_init__(self):
        for nom in ("dossiers", "lecteur", "application"):
            v = getattr(self, nom)
            if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v) or len(v) > 200:
                raise ValueError(f"lecteur.{nom} : liste de textes non vides")
        self.lecteur = [x.lower().lstrip(".") for x in self.lecteur]
        self.application = [x.lower().lstrip(".") for x in self.application]
        if not all(EXT.fullmatch(x) for x in self.lecteur + self.application):
            raise ValueError("lecteur : extensions de 1 à 12 lettres ou chiffres")
        if set(self.lecteur) & set(self.application):
            raise ValueError("lecteur : une extension ne peut être dans les deux modes")
        if any("\x00" in x or len(x) > 1000 for x in self.dossiers):
            raise ValueError("lecteur.dossiers : chemin invalide")
