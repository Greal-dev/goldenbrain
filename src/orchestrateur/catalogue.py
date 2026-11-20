"""Catalogue des moteurs : harnais disponibles, modèles proposés, découverte « auto » en cache.

Rôle : répondre à `GET /harnais` et valider un nom de modèle avant qu'il ne parte en argument.
Frontières : aucune E/S vault ; ne lance aucun tour (seule la découverte des modèles lance
un processus, hors de la boucle d'événements).
Invariants portés : aucun.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from .harnais.processus import resoudre
from . import langues
from .vault import Invalide

CACHE_S = 600
log = logging.getLogger(__name__)


def modele_valide(modele: str) -> str:
    # Le nom part en argument du harnais : jamais d'option déguisée (« -x ») ni d'espace.
    if modele and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-\[\]]{0,127}", modele):
        raise Invalide(langues.t("serveur.catalogue.modele_invalide", modele=modele))
    return modele


class Catalogue:
    def __init__(self, harnais: dict[str, dict], registre: dict):
        self.harnais = harnais
        self.registre = registre
        self._cache: dict[str, tuple[float, list[str]]] = {}

    async def _decouverts(self, nom: str, conf: dict) -> list[str]:
        instant, modeles = self._cache.get(nom, (0.0, []))
        if time.monotonic() - instant < CACHE_S and instant:
            return modeles
        decouvrir = getattr(self.registre[nom](conf), "decouvrir_modeles", None)
        try:
            modeles = await asyncio.to_thread(decouvrir) if decouvrir else []
        except Exception as e:  # une découverte en échec ne doit pas casser la liste
            log.warning("découverte des modèles de %s en échec : %s", nom, e)
            modeles = []
        self._cache[nom] = (time.monotonic(), modeles)
        return modeles

    async def lister(self) -> list[dict]:
        sortie = []
        for nom in self.registre:
            conf = self.harnais.get(nom, {})
            try:
                resoudre(conf.get("commande", nom))
                disponible, motif = True, ""
            except (FileNotFoundError, OSError) as e:
                disponible, motif = False, str(e)
            modeles = conf.get("modeles", [])
            if modeles == "auto":
                modeles = await self._decouverts(nom, conf) if disponible else []
            sortie.append({"nom": nom, "disponible": disponible, "motif": motif,
                           "modeles": [str(m) for m in modeles] if isinstance(modeles, list) else [],
                           "modele_defaut": str(conf.get("modele_defaut", ""))})
        return sortie
