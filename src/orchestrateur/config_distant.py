"""Configuration de l'écoute distante : exécuteurs (`[executeurs]`) et appareils (`[distant]`).

Rôle : valider au chargement ce qui ouvre GoldenBrain hors de la boucle locale.
Frontières : aucune entrée/sortie ; aucune décision d'accès (garde : `api_executeurs`, `api_appareils`).
Invariants portés : INV-DISTANT-1 (jamais toutes les interfaces), INV-DISTANT-7 (appareils désactivés
par défaut ; gestes à risque interdits par défaut ; certificat et clé vont ensemble).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

GESTES = ("interdire", "confirmer")
NOM_HOTE = re.compile(r"[A-Za-z0-9.-]{1,253}")


@dataclass
class ConfigExecuteurs:
    """Exécuteurs distants (INV-DISTANT-1) : `ecoute` = adresse d'une interface du poste (ex. l'adresse
    Tailscale) ouverte EN PLUS de 127.0.0.1 ; vide = boucle locale seule. Jamais toutes les interfaces."""
    ecoute: str = ""
    delai_perte_s: float = 45  # sans signe de vie depuis ce délai, l'exécuteur est « perdu »

    def __post_init__(self):
        if self.ecoute:
            # Une adresse IPv4 littérale, normalisée : un nom d'hôte ou une forme abrégée (« 0 », « 0x0 »)
            # ne serait pas reconnu par la garde (adresse du socket ≠ chaîne posée) — revue du 2026-11-18.
            try:
                ip = ipaddress.IPv4Address(self.ecoute.strip())
            except ValueError:
                raise ValueError("executeurs.ecoute : une adresse IPv4 précise (ex. l'adresse Tailscale 100.x.y.z)") from None
            if ip.is_unspecified or ip.is_multicast:
                raise ValueError("executeurs.ecoute : jamais toutes les interfaces ; donner une adresse précise")
            self.ecoute = str(ip)
        if not (isinstance(self.delai_perte_s, (int, float)) and self.delai_perte_s > 0):
            raise ValueError("executeurs.delai_perte_s : valeur hors bornes")


@dataclass
class ConfigDistant:
    """Téléphones appairés (INV-DISTANT-5 à 8) sur l'adresse `executeurs.ecoute`. `appareils` : admis ou non ;
    `gestes` : arrêt, redémarrage, suppression depuis un appareil — `interdire` ou `confirmer` ;
    `nom_hote` : nom accepté en plus de l'adresse (celui du certificat Tailscale, `machine.reseau.ts.net`) ;
    `certificat` / `cle` : fichiers de `tailscale cert` ; posés, l'adresse distante sert en HTTPS ;
    `resume` : autorise la sortie du poste d'un résumé court (140 caractères) du résultat d'une tâche à valider (désactivé par défaut) ;
    `hors_ligne` : autorise le stockage local de l'instantané du compagnon (désactivé par défaut)."""
    appareils: bool = False
    gestes: str = "interdire"
    nom_hote: str = ""
    certificat: str = ""
    cle: str = ""
    resume: bool = False         # le compagnon affiche un résumé court du résultat des tâches à valider (INV-COMPAGNON-1)
    hors_ligne: bool = False     # le compagnon peut garder un instantané léger sur l'appareil (INV-PWA-2)

    def __post_init__(self):
        if self.gestes not in GESTES:
            raise ValueError("distant.gestes : « interdire » ou « confirmer »")
        if self.nom_hote and not NOM_HOTE.fullmatch(self.nom_hote):
            raise ValueError("distant.nom_hote : nom d'hôte seul (sans schéma ni port)")
        if bool(self.certificat) != bool(self.cle):
            raise ValueError("distant.certificat et distant.cle vont ensemble")
