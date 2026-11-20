"""Scan du système : préconisations d'optimisation classées par gain et par effort.

Rôle : parcourir l'index du vault (tâches, conteneurs, liens) et déposer, pour chaque défaut
repéré par une règle déterministe, une proposition (`de` = « scan ») portant `gain`, `effort`
et le motif en clair : doublon probable, tâche en sommeil, tâche sans place.
Frontières : n'écrit que des propositions (`moteur.proposer`) ; ne ferme, ne déplace, ne
supprime rien ; aucun appel d'agent (la « Revue de cohérence » du jardinage reste le regard
d'un modèle ; le scan en est le pendant mécanique et gratuit).
Invariants portés : INV-SCAN-1 (préconisation = proposition en attente quelle que soit la
politique ; jamais reproposée si elle attend déjà ou a été refusée).
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

from . import langues
from .vault import ErreurOrch

AUTEUR = "scan"
OUVERTS = ("a-faire", "en-cours", "confier-agent", "bloque")  # statut de retour : déjà une décision
SOMMEIL_JOURS = 60
SEUIL_DOUBLON = 0.8
SEUIL_PLACE = 0.5
GAIN = {"fort": 0, "moyen": 1, "faible": 2}
EFFORT = {"faible": 0, "moyen": 1, "fort": 2}
MOTS_VIDES = {"le", "la", "les", "l", "de", "du", "des", "d", "et", "a", "au", "aux", "en", "un",
              "une", "pour", "sur", "par", "dans", "avec", "ou", "que", "qui", "se", "sa", "son"}


def mots(titre: str) -> frozenset[str]:
    """Mots significatifs d'un titre : casse, accents et ponctuation ignorés."""
    plat = unicodedata.normalize("NFKD", titre.casefold()).encode("ascii", "ignore").decode()
    return frozenset(m for m in re.split(r"[^a-z0-9]+", plat) if m and m not in MOTS_VIDES)


def ressemblance(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _date(fm: dict) -> dt.date | None:
    for cle in ("updated", "created"):
        try:
            return dt.date.fromisoformat(str(fm.get(cle) or "")[:10])
        except ValueError:
            continue
    return None


def _candidats(moteur) -> dict:
    """Tâches ouvertes que le scan peut juger : ni permanentes, ni de pilotage, ni en cours de tour."""
    return {k: t for k, t in moteur.vault.index()[0].items()
            if t.statut in OUVERTS and not t.pilotage and str(t.fm.get("nature") or "") != "permanente"
            and moteur.etat_de(k) not in ("en_cours", "en_file")}


def doublons(taches: dict) -> list[dict]:
    # ponytail: comparaison par paires, O(n²) ; suffisant jusqu'à quelques milliers de tâches.
    sortie, vus, ids = [], set(), sorted(taches, key=lambda k: (str(_date(taches[k].fm) or ""), k))
    sacs = {k: mots(taches[k].titre) for k in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if b in vus or len(sacs[a]) < 2 or ressemblance(sacs[a], sacs[b]) < SEUIL_DOUBLON:
                continue
            if a == taches[b].parent_brut or b == taches[a].parent_brut:
                continue  # une mère et son ticket se ressemblent par construction
            vus.add(b)  # la plus récente est le doublon : l'ancienne porte l'historique
            sortie.append({"type": "fermer", "tache": b, "valeur": "abandonne", "gain": "fort",
                           "effort": "moyen", "motif": langues.t("serveur.scan.doublon", titre=taches[a].titre, ident=a)})
    return sortie


def sommeil(taches: dict, aujourd_hui: dt.date) -> list[dict]:
    sortie = []
    for k, t in taches.items():
        d = _date(t.fm)
        echeance = str(t.fm.get("echeance") or "")[:10]
        if d is None or (aujourd_hui - d).days < SOMMEIL_JOURS or echeance >= aujourd_hui.isoformat():
            continue
        sortie.append({"type": "fermer", "tache": k, "valeur": "abandonne", "gain": "moyen", "effort": "faible",
                       "motif": langues.t("serveur.scan.sommeil", n=(aujourd_hui - d).days, date=d.isoformat())})
    return sortie


def sans_place(moteur, taches: dict) -> list[dict]:
    """Tâche restée dans le conteneur d'arrivée : rangée près de la tâche dont le titre ressemble le plus."""
    arrivee = moteur.vault.cfg.arrivee
    autres = [t for t in moteur.vault.index()[0].values() if t.conteneur != arrivee]
    sortie = []
    for k, t in taches.items():
        if t.conteneur != arrivee or t.parent_brut:
            continue
        sac = mots(t.titre)
        score, voisine = max(((ressemblance(sac, mots(o.titre)), o) for o in autres),
                             key=lambda x: x[0], default=(0.0, None))
        if voisine is not None and score >= SEUIL_PLACE:
            sortie.append({"type": "deplacer", "tache": k, "valeur": voisine.conteneur, "gain": "moyen",
                           "effort": "faible", "motif": langues.t("serveur.scan.sans_place", titre=voisine.titre)})
    return sortie


def cle(p: dict) -> tuple:
    return p["type"], p["tache"], str(p["valeur"])


def ordre(p: dict) -> tuple:
    """Clé de classement : gain d'abord (fort → faible), puis effort (faible → fort)."""
    return GAIN.get(p.get("gain"), 3), EFFORT.get(p.get("effort"), 3), p.get("n", 0)


def scanner(moteur, aujourd_hui: dt.date | None = None) -> dict:
    """Dépose les préconisations nouvelles ; rend `{"nouvelles", "ignorees", "erreurs"}`."""
    taches = _candidats(moteur)
    trouvees = doublons(taches)
    fermees = {p["tache"] for p in trouvees}
    trouvees += [p for p in sommeil(taches, aujourd_hui or dt.date.today()) if p["tache"] not in fermees]
    trouvees += sans_place(moteur, taches)
    # INV-SCAN-1 : ce qui attend déjà ou a été refusé n'est jamais reproposé.
    connues = {cle(p) for p in moteur.propositions.liste if p.get("etat") in ("en_attente", "refusee")}
    nouvelles, erreurs = [], []
    for p in trouvees:
        if cle(p) in connues:
            continue
        try:
            nouvelles.append(moteur.proposer(p["type"], p["tache"], p["valeur"], AUTEUR, p["motif"],
                                             montrer=True, annexe={"gain": p["gain"], "effort": p["effort"]}))
        except ErreurOrch as e:  # une préconisation inacceptable n'arrête pas le scan
            erreurs.append({"tache": p["tache"], "erreur": str(e)})
        connues.add(cle(p))
    return {"nouvelles": len(nouvelles), "ignorees": len(trouvees) - len(nouvelles) - len(erreurs),
            "erreurs": erreurs}
