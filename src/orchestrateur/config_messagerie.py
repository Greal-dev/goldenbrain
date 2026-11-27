"""Réglage de la messagerie : `[messagerie]` de `config.toml` (une boîte Gmail par IMAP/SMTP).

Rôle : porter l'adresse, les serveurs IMAP et SMTP, les délais et l'emplacement du mot de passe
d'application ; un compte par section, le modèle reste celui d'un compte (`Compte` de `mail_imap`) pour
en accueillir d'autres plus tard.
Frontières : données seules, sans import du paquet (`config` l'importe) ; jamais de mot de passe ici :
il vit dans le coffre du poste (`coffre`), fichier `mdp_fichier` ou variable `mdp_variable`.
Invariants portés : INV-MAIL-1 (mot de passe hors de config.toml ; transport chiffré hors boucle locale).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HOTE = re.compile(r"[A-Za-z0-9.-]{1,253}:\d{1,5}")
LOCAUX = ("127.0.0.1", "localhost", "::1")


@dataclass
class ConfigMessagerie:
    adresse: str = ""                       # adresse Gmail ; vide = messagerie non réglée
    imap: str = "imap.gmail.com:993"
    smtp: str = "smtp.gmail.com:465"
    tls: bool = True                        # faux admis pour un serveur de la boucle locale seulement (essais)
    mdp_variable: str = "GOLDENBRAIN_MESSAGERIE_MDP"
    mdp_fichier: str = ""                   # vide = <donnees>/etat/messagerie.mdp (DPAPI ou 0600)
    delai_s: float = 20                     # délai borné de chaque échange réseau
    par_page: int = 50

    def __post_init__(self):
        self.adresse = str(self.adresse).strip()
        if any(c in self.adresse for c in "\r\n\x00 ") or (self.adresse and self.adresse.count("@") != 1):
            raise ValueError("messagerie.adresse : adresse électronique attendue")
        for nom in ("imap", "smtp"):
            if not HOTE.fullmatch(getattr(self, nom)):
                raise ValueError(f"messagerie.{nom} : « hôte:port » attendu")
        # INV-MAIL-1 : le mot de passe ne circule en clair que vers la boucle locale (faux serveur d'essai).
        if not self.tls and any(self.hote(n)[0] not in LOCAUX for n in ("imap", "smtp")):
            raise ValueError("messagerie.tls : désactivable pour un serveur local seulement")
        if not 1 <= float(self.delai_s) <= 120 or not 5 <= int(self.par_page) <= 200:
            raise ValueError("messagerie : délai de 1 à 120 s, page de 5 à 200 messages")

    def hote(self, nom: str) -> tuple[str, int]:
        h, p = getattr(self, nom).rsplit(":", 1)
        return h, int(p)
