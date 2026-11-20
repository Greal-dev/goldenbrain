"""Programme d'une routine : analyse d'une écriture lisible ou cron, prochaine échéance.

Rôle : transformer `programme:` (« chaque jour 08:00 », « lundi,jeudi 09:30 », « en semaine 18:00 »,
« toutes les 2 h de 8 h à 20 h », « toutes les 15 min », ou cron à cinq champs) en ensembles de
minutes, heures, jours, mois, jours de semaine, et calculer la première échéance après un instant.
Frontières : calcul pur, heure locale naïve du poste (aucun fuseau), aucune écriture ni horloge.
Invariants portés : INV-ROUTINE-2 (programme invalide refusé à l'écriture, jamais deviné).
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass

from . import langues
from .vault import Invalide

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
HORIZON_JOURS = 366 * 8  # un 29 février tombe au plus tous les 8 ans (années séculaires)


@dataclass(frozen=True)
class Programme:
    minutes: frozenset[int]
    heures: frozenset[int]
    jours_mois: frozenset[int] | None = None  # None = tout jour
    mois: frozenset[int] | None = None
    jours_semaine: frozenset[int] | None = None  # 0 = lundi
    fin: tuple[int, int] | None = None  # « de A h à B h » : rien après B:00

    def accepte_jour(self, d: dt.date) -> bool:
        if self.mois is not None and d.month not in self.mois:
            return False
        jm, js = self.jours_mois, self.jours_semaine
        if jm is not None and js is not None:  # cron : les deux restreints, l'un OU l'autre
            return d.day in jm or d.weekday() in js
        return (jm is None or d.day in jm) and (js is None or d.weekday() in js)


def _plat(texte: str) -> str:
    texte = unicodedata.normalize("NFD", texte.strip().casefold())
    return " ".join("".join(c for c in texte if not unicodedata.combining(c)).split())


def _heures_minutes(morceaux: str) -> list[tuple[int, int]]:
    sortie = []
    for m in morceaux.split(","):
        r = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:h]\s*(\d{2})?)?\s*", m)
        if not r or int(r[1]) > 23 or int(r[2] or 0) > 59:
            raise Invalide(langues.t("serveur.programme.heure_illisible", heure=repr(m.strip())))
        sortie.append((int(r[1]), int(r[2] or 0)))
    return sortie


def _horaires(jours: frozenset[int] | None, quand: str) -> Programme:
    hm = _heures_minutes(quand)
    if len({m for _, m in hm}) > 1:
        # Plusieurs heures aux minutes différentes ne tiennent pas dans un produit heures × minutes.
        raise Invalide(langues.t("serveur.programme.plusieurs_heures"))
    return Programme(frozenset({hm[0][1]}), frozenset(h for h, _ in hm), jours_semaine=jours)


def _intervalle(n: int, unite: str, de: str | None, a: str | None) -> Programme:
    debut = _heures_minutes(de)[0] if de else (0, 0)
    fin = _heures_minutes(a)[0] if a else None
    if n <= 0:
        raise Invalide(langues.t("serveur.programme.intervalle_nul"))
    if unite == "h":
        if n > 23:
            raise Invalide(langues.t("serveur.programme.toutes_h"))
        return Programme(frozenset({debut[1]}), frozenset(range(debut[0], (fin or (23, 0))[0] + 1, n)), fin=fin)
    if 60 % n:
        raise Invalide(langues.t("serveur.programme.toutes_min"))
    return Programme(frozenset(range(0, 60, n)), frozenset(range(debut[0], (fin or (23, 0))[0] + 1)), fin=fin)


def _champ(texte: str, bas: int, haut: int) -> frozenset[int] | None:
    if texte == "*":
        return None
    valeurs: set[int] = set()
    for morceau in texte.split(","):
        r = re.fullmatch(r"(\*|\d+)(?:-(\d+))?(?:/(\d+))?", morceau)
        if not r:
            raise Invalide(langues.t("serveur.programme.cron_illisible", champ=repr(morceau)))
        a = bas if r[1] == "*" else int(r[1])
        b = (haut if r[1] == "*" or r[3] else a) if r[2] is None else int(r[2])
        pas = int(r[3] or 1)
        if not (bas <= a <= b <= haut) or pas <= 0:
            raise Invalide(langues.t("serveur.programme.cron_bornes", champ=repr(morceau), bas=bas, haut=haut))
        valeurs.update(range(a, b + 1, pas))
    return frozenset(valeurs)


def _cron(champs: list[str]) -> Programme:
    mi, he, jm, mo, js = champs
    semaine = _champ(js, 0, 7)
    return Programme(_champ(mi, 0, 59) or frozenset(range(60)), _champ(he, 0, 23) or frozenset(range(24)),
                     _champ(jm, 1, 31), _champ(mo, 1, 12),
                     None if semaine is None else frozenset((j - 1) % 7 for j in semaine))  # cron : 0 = dimanche


def analyser(texte: str) -> Programme:
    """Programme lu ; `Invalide` avec la raison sinon (INV-ROUTINE-2)."""
    brut = (texte or "").strip()
    if not brut:
        raise Invalide(langues.t("serveur.programme.vide"))
    if len(champs := brut.split()) == 5 and re.fullmatch(r"[\d*,/\- ]+", brut):
        return _cron(champs)
    t = _plat(brut)
    if r := re.fullmatch(r"(?:chaque jour|tous les jours)(?: a)? (.+)", t):
        return _horaires(None, r[1])
    if r := re.fullmatch(r"en semaine(?: a)? (.+)", t):
        return _horaires(frozenset(range(5)), r[1])
    if r := re.fullmatch(r"toutes les (\d+) ?(h|heures?|min|minutes?)(?: de (.+?) a (.+))?", t):
        return _intervalle(int(r[1]), "h" if r[2].startswith("h") else "min", r[3], r[4])
    if r := re.fullmatch(r"(?:chaque |le |les )?([a-z, ]+?)s?(?: a)? (\d.*)", t):
        noms = [j.strip().removesuffix("s") for j in re.split(r"[, ]+| et ", r[1]) if j.strip() not in ("", "et")]
        if noms and all(j in JOURS for j in noms):
            return _horaires(frozenset(JOURS.index(j) for j in noms), r[2])
    raise Invalide(langues.t("serveur.programme.illisible", texte=repr(brut)))


def prochaine(p: Programme, apres: dt.datetime) -> dt.datetime | None:
    """Première échéance strictement après `apres` (à la minute) ; None si aucune à l'horizon."""
    base = apres.replace(second=0, microsecond=0)
    heures, minutes = sorted(p.heures), sorted(p.minutes)
    for n in range(HORIZON_JOURS):
        jour = base.date() + dt.timedelta(days=n)
        if not p.accepte_jour(jour):
            continue
        for h in heures:
            for m in minutes:
                if p.fin and (h, m) > p.fin:
                    break
                c = dt.datetime.combine(jour, dt.time(h, m))
                if c > apres:
                    return c
    return None
