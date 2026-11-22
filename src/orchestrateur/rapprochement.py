"""Rapprochement avant création : retrouver les tâches voisines d'une demande, et compter les doublons évités.

Rôle : un SEUL moteur de ressemblance pour toutes les entrées (POST /api/taches, formulaire « Nouvelle
tâche », `orch creer`, `orch deleguer`, assistant Telegram) ; recherche lexicale locale, sans modèle.
Frontières : lit l'index en mémoire de `Vault` ; n'écrit que `<donnees>/etat/rapprochement.json`
(compteur et journal), jamais le vault. Aucun appel HTTP, aucun modèle : `arbitre` est un point
d'extension facultatif (départage IA désactivé tant qu'on n'en branche pas un).
Invariants portés : INV-RAPPROCHEMENT-1 (une correspondance forte avec une tâche OUVERTE refuse la
création, doucement : 409 + candidates, sauf `forcer`), INV-RAPPROCHEMENT-2 (la mesure compte les
créations évitées : refus non suivis d'une création, et compléments).

Score d'une candidate (0 à 1), sur des mots normalisés (sans casse ni accents, sans mots vides, sans
pluriel final) :
- `dice` = 2·|T∩Ct| / (|T|+|Ct|) : recouvrement des mots du titre demandé (T) et du titre de la candidate
  (Ct) ; 1 pour un même titre, 0,67 pour deux mots partagés sur trois de chaque côté.
- `couverture` = part des mots de T qui figurent dans le titre ou la fiche de la candidate.
- `description` = recouvrement des mots de la description demandée avec la candidate (plafonné à 15 mots).
- score = 0,6·dice + 0,25·couverture + 0,15·description (sans description : 0,7·dice + 0,3·couverture),
  plus 0,10 si même conteneur (seulement quand le recouvrement est déjà net : le conteneur départage les
  homonymes, il ne crée pas de parenté).
Seuils : AFFICHE (0,35, au moins un mot de titre partagé) pour proposer ; FORTE (0,72, au moins deux mots
de titre partagés, ou un titre d'un seul mot identique) pour refuser. À titre d'étalon : même titre = 1,0 ;
deux mots sur trois partagés dans le même projet ≈ 0,77 (forte), dans un autre projet ≈ 0,67 (proposée,
non bloquante) ; un seul mot en commun ≈ 0,3 (rien). Une tâche close depuis moins de 30 jours est
proposée mais ne bloque jamais (la rouvrir est un geste humain)."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from .recherche import normaliser

AFFICHE = 0.35
FORTE = 0.72
RECENT_J = 30
LIMITE = 5
JOURNAL_MAX = 500

MOTS_VIDES = frozenset("""
les des une aux que qui quoi dont sur sous par pour dans avec sans vers chez entre contre depuis comme
mais donc car ainsi alors aussi tout tous toute toutes cette cet ces son sont ses leur leurs nos vos
etre avoir fait faire faut doit peut plus moins tres bien tache taches
""".split())


def mots(texte: str) -> set[str]:
    """Mots utiles : normalisés, 3 lettres au moins, hors mots vides, pluriel final retiré."""
    sortie = set()
    for m in re.findall(r"[a-z0-9]+", normaliser(texte or "")):
        if len(m) < 3 or m in MOTS_VIDES:
            continue
        sortie.add(m[:-1] if len(m) > 4 and m[-1] in "sx" else m)
    return sortie


def cle(titre: str) -> str:
    """Identité d'une demande pour la mesure : ses mots, triés."""
    return " ".join(sorted(mots(titre)))


def _texte_fiche(t) -> str:
    f = t.fiche or {}
    return " ".join([*(f.get(k) or "" for k in ("situation", "fait", "reste", "prochain_pas")),
                     *(s.get("texte") or "" for s in [*(f.get("sous_taches") or []), *(f.get("lignes") or [])])])


def _clos_recemment(t, maintenant: datetime) -> bool:
    brut = t.fm.get("updated") or t.fm.get("modifie")
    try:
        quand = brut if isinstance(brut, date) else date.fromisoformat(str(brut)[:10])
        quand = datetime(quand.year, quand.month, quand.day)
    except (TypeError, ValueError):
        try:
            quand = datetime.fromtimestamp(t.chemin.stat().st_mtime)
        except OSError:
            return False
    return maintenant - quand <= timedelta(days=RECENT_J)


def noter(titre: str, description: str, conteneur: str | None, t, mots_titre: set[str],
          mots_desc: set[str]) -> tuple[float, int]:
    """(score, nombre de mots de titre partagés) d'une tâche pour la demande."""
    ct = mots(t.titre)
    communs = mots_titre & ct
    if not communs:
        return 0.0, 0
    plein = ct | mots(_texte_fiche(t))
    dice = 2 * len(communs) / (len(mots_titre) + len(ct))
    couverture = len(mots_titre & plein) / len(mots_titre)
    if mots_desc:
        desc = len(mots_desc & plein) / min(len(mots_desc), 15)
        base = 0.6 * dice + 0.25 * couverture + 0.15 * min(1.0, desc)
    else:
        base = 0.7 * dice + 0.3 * couverture
    if conteneur and t.conteneur == conteneur and base >= 0.2:
        base += 0.10
    return min(1.0, base), len(communs)


def proches(vault, titre: str, description: str = "", conteneur: str | None = None, *,
            exclure=(), limite: int = LIMITE, maintenant: datetime | None = None) -> list[dict]:
    """Candidates classées : ouvertes d'abord, closes de moins de 30 jours ensuite, chacune par score
    décroissant. `forte` : la création doit être refusée (INV-RAPPROCHEMENT-1)."""
    mt = mots(titre)
    if not mt:
        return []
    md = mots(description) - mt
    maintenant = maintenant or datetime.now()
    exclus = {x for x in exclure if x}
    taches = vault.index()[0]
    parents = vault._parents(taches)
    trouvees = []
    for k, t in taches.items():
        if k in exclus or t.pilotage:  # INV-PILOTAGE-1
            continue
        ouverte = vault.ouverte(t)
        if not ouverte and not _clos_recemment(t, maintenant):
            continue
        score, partages = noter(titre, description, conteneur, t, mt, md)
        if score < AFFICHE:
            continue
        seul = len(mt) == 1 and mots(t.titre) == mt
        forte = ouverte and score >= FORTE and (partages >= 2 or seul)
        trouvees.append({"id": k, "titre": t.titre, "statut": t.statut, "ouverte": ouverte,
                         "conteneur": t.conteneur, "fil_ariane": vault.fil_ariane(k, parents),
                         "score": round(score, 2), "forte": forte})
    trouvees.sort(key=lambda c: (not c["ouverte"], -c["score"], c["titre"].casefold()))
    return trouvees[:max(1, limite)]


def forte(candidates: list[dict]) -> bool:
    return any(c["forte"] for c in candidates)


async def departager(candidates: list[dict], arbitre=None) -> list[dict]:
    """Départage IA, seulement si nécessaire : plusieurs candidates ouvertes et aucune forte, dans la
    zone grise (0,5 à FORTE). `arbitre` (coroutine : candidates → identifiants du plus proche au moins
    proche) est facultatif ; absent, l'ordre lexical reste (c'est le cas tant qu'aucun modèle n'est branché)."""
    grises = [c for c in candidates if c["ouverte"] and not c["forte"] and c["score"] >= 0.5]
    if arbitre is None or len(grises) < 2:
        return candidates
    ordre = {i: n for n, i in enumerate(await arbitre(grises))}
    return sorted(candidates, key=lambda c: (not c["ouverte"], ordre.get(c["id"], len(ordre)), -c["score"]))


class Mesure:
    """Compteur persistant des créations évitées (INV-RAPPROCHEMENT-2). Un refus compte tant qu'aucune
    création de la même demande ne le suit ; un complément compte aussitôt."""

    def __init__(self, donnees: Path):
        self.chemin = Path(donnees) / "etat" / "rapprochement.json"

    def _lire(self) -> list[dict]:
        try:
            return json.loads(self.chemin.read_text(encoding="utf-8")).get("journal", [])
        except (OSError, ValueError):
            return []

    def _ecrire(self, journal: list[dict]) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps({"journal": journal[-JOURNAL_MAX:]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.chemin)

    def _noter(self, journal: list[dict], **entree) -> None:
        journal.append({"quand": datetime.now().isoformat(timespec="seconds"), **entree})
        self._ecrire(journal)

    def refus(self, titre: str, candidates: list[dict]) -> None:
        j = self._lire()
        self._noter(j, etat="refus", cle=cle(titre), titre=titre, candidates=[c["id"] for c in candidates])

    def creation(self, titre: str) -> None:
        """La demande a fini par créer : le dernier refus de cette demande n'était pas une création évitée."""
        j, k = self._lire(), cle(titre)
        for e in reversed(j):
            if e.get("etat") == "refus" and e.get("cle") == k:
                e["etat"] = "force"
                self._ecrire(j)
                return

    def complement(self, tache: str, titre: str = "") -> None:
        j = self._lire()
        k = cle(titre) if titre else ""
        for e in reversed(j):  # le refus qui a mené à ce complément ne compte pas deux fois
            if k and e.get("etat") == "refus" and e.get("cle") == k:
                e["etat"] = "complete"
                break
        self._noter(j, etat="complement", cle=k, titre=titre, tache=tache)

    def vue(self) -> dict:
        j = self._lire()
        n = lambda etat: sum(e.get("etat") == etat for e in j)  # noqa: E731
        return {"evitees": n("refus") + n("complement"), "refus_non_forces": n("refus"),
                "complements": n("complement"), "forces_apres_refus": n("force"),
                "dernieres": j[-5:]}
