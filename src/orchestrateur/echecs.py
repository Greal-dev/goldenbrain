"""Échec d'un tour : message du système, lisible, qui reprend le motif du harnais.

Rôle : traduire le motif brut d'un tour en échec en un texte pour la conversation, et reconnaître
un quota épuisé (avec l'heure de reprise quand le harnais la donne).
Frontières : fonctions pures ; l'écriture au journal et dans la fiche est faite par `moteur.py`.
Invariants portés : INV-EXEC-8 (un échec de tour est visible, jamais relancé : INV-EXEC-1).
"""

from __future__ import annotations

import datetime as dt
import re

from . import langues

QUOTA = re.compile(r"usage.?limit|quota|rate.?limit|\b429\b|resource.?exhausted|too many requests"
                   r"|credits?\b.*(exhaust|insufficient|run out)", re.I)
# Réseau coupé ou fournisseur injoignable (INV-RESEAU-1) : motifs relevés dans les sorties des harnais.
RESEAU = re.compile(r"\bENOTFOUND|ECONNREFUSED|ECONNRESET|ECONNABORTED|ETIMEDOUT|EAI_AGAIN|ENETUNREACH|EHOSTUNREACH"
                    r"|getaddrinfo|can.?t reach the api|unable to connect|failed to connect|fetch failed|socket hang up"
                    r"|connection (?:refused|reset|aborted|closed|error|timed out)|network (?:error|is unreachable|unreachable)"
                    r"|name resolution|dns|offline|ConnectError|ConnectTimeout|check your internet", re.I)
# Exécutable du harnais absent du poste : `processus.resoudre`, `roles.disponible`. « FileNotFoundError »
# contient « ENOTFOUND » : d'où le `\b` du motif réseau, et cette cause testée avant lui.
INTROUVABLE = re.compile(r"exécutable introuvable|FileNotFoundError|harnais indisponible", re.I)
# « try again at 3:14 PM. », « resets 3pm », « retry in 2 hours » : l'heure ou le délai de reprise.
REPRISE = re.compile(r"(?:try again|retry|resets?)\s*(?:at|in|after|on)?\s+(\d[^.\n]{0,40}?)\s*(?:[.\n]|$)",
                     re.I)


def est_quota(motif: str) -> bool:
    return bool(QUOTA.search(motif or ""))


def est_introuvable(motif: str) -> bool:
    return bool(INTROUVABLE.search(motif or ""))


def message(motif: str) -> str:
    """Texte du message du système ; le motif du harnais est repris tel quel (tronqué)."""
    motif = " ".join((motif or langues.t("serveur.echecs.erreur_assistant")).split())[:600]
    if est_quota(motif):
        r = REPRISE.search(motif)
        if r:
            return langues.t("serveur.echecs.quota_reprise", reprise=r[1], motif=motif)
        return langues.t("serveur.echecs.quota", motif=motif)
    return langues.t("serveur.echecs.echec", motif=motif)


def heure_reprise(motif: str, maintenant: dt.datetime) -> dt.datetime | None:
    """Instant de reprise annoncé par le harnais (« try again at 3:14 PM », « retry in 2 hours »)."""
    motif = motif or ""
    if m := re.search(r"(?:try again|retry|resets?)\s+in\s+(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m)\b",
                      motif, re.I):
        n = int(m[1])
        return maintenant + (dt.timedelta(hours=n) if m[2][0].lower() == "h"
                             else dt.timedelta(minutes=n))
    m = re.search(r"(?:try again|retry|resets?)\s*(?:at|on|after)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                  motif, re.I)
    if not m or not (m[2] or m[3]):
        return None  # « resets 3 » : sans minutes ni am/pm, l'heure reste ambiguë
    heure, minute = int(m[1]), int(m[2] or 0)
    if m[3]:
        if not 1 <= heure <= 12:
            return None
        heure = heure % 12 + (12 if m[3].lower() == "pm" else 0)
    if heure > 23 or minute > 59:
        return None
    cible = maintenant.replace(hour=heure, minute=minute, second=0, microsecond=0)
    return cible if cible > maintenant else cible + dt.timedelta(days=1)
