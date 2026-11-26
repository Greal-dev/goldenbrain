"""Vue par étiquette : tout ce qui porte un mot, avec le dernier résultat de chacun, en une seule lecture.

Rôle : assembler, pour une étiquette, les tâches et routines qui la portent (routines d'abord, ouvertes d'abord,
puis les fermées récentes) : fil d'Ariane, statut, première phrase du résultat de la fiche (sinon du « fait »),
date de mise à jour, autres étiquettes ; pour une routine : programme, pause, dernière et prochaine exécution.
Frontières : lecture seule — index du vault, `etiquettes`, `Routines.public` ; n'exécute rien (les exécutions
passent par `/api/routines/{id}/executer`). Les conversations de conteneur (INV-PILOTAGE-1) en sont exclues.
Invariants portés : INV-ETIQUETTE-4 (la vue d'une étiquette est en lecture seule ; mot inconnu = liste vide ;
fermées bornées à 30 jours et 40 lignes en tout, pour que la page reste lisible).
"""

from __future__ import annotations

import datetime as dt
import re

from . import etiquettes, routines
from .vault import aujourdhui

FERMEES_JOURS = 30
MAX_LIGNES = 40
MAX_RESULTAT = 1500


def premiere_phrase(texte: str) -> str:
    texte = " ".join(str(texte or "").split())
    m = re.search(r"[.!?…](?:\s|$)", texte)
    return texte[:m.end()].strip() if m else texte


def _jour(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def assembler(moteur, mot: str) -> dict:
    mot = etiquettes.normaliser(mot)
    vault = moteur.vault
    taches = vault.index()[0]
    parents = vault._parents(taches)
    limite = aujourdhui() - dt.timedelta(days=FERMEES_JOURS)
    lignes = []
    for ident, t in taches.items():
        if t.pilotage or mot not in etiquettes.de(t.fm):
            continue
        jour = _jour(t.fm.get("updated"))
        ouverte = vault.ouverte(t)
        if not ouverte and not (jour and jour >= limite):
            continue
        resultat = t.fiche.get("resultat") or t.fiche.get("fait") or ""
        ligne = {"id": ident, "titre": t.titre, "statut": t.statut, "ouverte": ouverte,
                 "fil": vault.fil_ariane(ident, parents)[-3:],
                 "resultat": " ".join(str(resultat).split())[:MAX_RESULTAT],
                 "phrase": premiere_phrase(resultat), "maj": jour.isoformat() if jour else None,
                 "autres": [m for m in etiquettes.de(t.fm) if m != mot], "routine": None}
        if routines.est_routine(t):
            p = moteur.routines.public(ident, t)
            ligne["routine"] = {"programme": p["programme"], "en_pause": p["etat"] == routines.EN_PAUSE,
                                "prochaine": p["prochaine"], "derniere": p["derniere"], "erreur": p["erreur"],
                                "en_cours": moteur.etat_de(ident) in routines.OCCUPEE}
        lignes.append(ligne)
    lignes.sort(key=lambda x: (x["routine"] is None, not x["ouverte"],
                               -(_jour(x["maj"]) or dt.date.min).toordinal(), x["titre"].casefold()))
    return {"mot": mot, "consigne": moteur.etiquettes.consigne(mot), "taches": lignes[:MAX_LIGNES]}
