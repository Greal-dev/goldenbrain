"""Appairage d'un exécuteur : un code court, valable quelques minutes, échangé contre un jeton.

Rôle : le chef affiche un code (`ABCD-EFGH`) ; l'exécuteur le saisit, le chef lui remet alors son
jeton (créé par `Executeurs.creer_jeton`) et le code meurt. Évite de recopier un jeton de 43
caractères d'un PC à l'autre.
Frontières : aucun HTTP (routes : `api_executeurs`), aucune persistance (les codes vivent en
mémoire : un redémarrage du chef les annule), aucune règle de jeton (déléguée à `creer_jeton`).
Invariants portés : INV-APPAIRAGE-1 (code à usage unique, durée courte, tentatives limitées, seule
l'empreinte du code est gardée, jamais journalisé).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from . import langues
from .vault import ErreurOrch, Invalide

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sans 0 O 1 I L : lisible à voix haute
LONGUEUR = 8
VALIDITE_S = 600        # dix minutes
ECHECS_MAX = 5          # échecs consécutifs avant verrou
VERROU_S = 60
CODES_MAX = 10          # codes ouverts en même temps


class TropDEssais(ErreurOrch):
    code = 429


def normaliser(code: str) -> str:
    """Majuscules, sans tiret ni espace : `abcd-efgh` et `ABCD EFGH` valent `ABCDEFGH`."""
    return "".join(c for c in (code or "").upper() if c in ALPHABET)


def afficher(brut: str) -> str:
    return f"{brut[:LONGUEUR // 2]}-{brut[LONGUEUR // 2:]}"


def _empreinte(brut: str) -> str:
    return hashlib.sha256(brut.encode("ascii")).hexdigest()


class Appairage:
    def __init__(self, creer_jeton, valider_nom, horloge=time.monotonic):
        self._creer_jeton, self._valider_nom, self._horloge = creer_jeton, valider_nom, horloge
        self._ouverts: dict[str, tuple[str, float]] = {}   # empreinte -> (nom, expiration)
        self._echecs = 0
        self._verrou = 0.0

    def _purger(self) -> None:
        maintenant = self._horloge()
        for h in [h for h, (_, fin) in self._ouverts.items() if fin <= maintenant]:
            del self._ouverts[h]

    def ouvrir(self, nom: str) -> dict:
        """Code neuf pour `nom` (remplace le précédent du même nom) : `{code, nom, valide_s}`."""
        self._valider_nom(nom)
        self._purger()
        self._ouverts = {h: v for h, v in self._ouverts.items() if v[0] != nom}
        if len(self._ouverts) >= CODES_MAX:
            raise Invalide(langues.t("serveur.appairage.trop_de_codes"))
        brut = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR))
        self._ouverts[_empreinte(brut)] = (nom, self._horloge() + VALIDITE_S)
        return {"code": afficher(brut), "nom": nom, "valide_s": VALIDITE_S}

    def echanger(self, code: str) -> dict:
        """Code valide → `{nom, jeton}` et le code est consommé ; sinon refus (verrou après échecs)."""
        maintenant = self._horloge()
        if maintenant < self._verrou:
            raise TropDEssais(langues.t("serveur.appairage.trop_d_essais", secondes=int(self._verrou - maintenant) + 1))
        self._purger()
        brut = normaliser(code)
        trouve = None
        if len(brut) == LONGUEUR:
            e = _empreinte(brut)
            for h in self._ouverts:
                if hmac.compare_digest(e, h):  # temps constant, comme les jetons
                    trouve = h
        if trouve is None:
            self._echecs += 1
            if self._echecs >= ECHECS_MAX:
                self._echecs, self._verrou = 0, maintenant + VERROU_S
            raise Invalide(langues.t("serveur.appairage.code_invalide"))
        nom, _ = self._ouverts.pop(trouve)
        self._echecs = 0
        return {"nom": nom, "jeton": self._creer_jeton(nom)}

    def ouverts(self) -> list[dict]:
        """Codes encore valables, sans le code : `{nom, reste_s}` (pour l'interface du chef)."""
        self._purger()
        maintenant = self._horloge()
        return [{"nom": nom, "reste_s": int(fin - maintenant)} for nom, fin in self._ouverts.values()]
