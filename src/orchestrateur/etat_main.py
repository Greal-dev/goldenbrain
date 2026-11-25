"""Lecture « à qui est la main » : quatre états, calculés par-dessus les statuts du vault.

Rôle : dire, pour une tâche, qui doit agir — `ia` (un agent travaille), `file` (elle attend son tour, avec le
motif et la reprise), `humain` (une action est nécessaire, en une phrase et avec le geste pour la faire) ou
`termine`. Une lecture seule : les statuts du vault (a-faire, en-cours, retour, bloque, fait…) restent la donnée
de fond, rien n'est migré ni écrit. Sert la pastille de l'en-tête, l'arbre, les listes, le compteur « À moi » et
le rapport de reprise de l'existant (`rapport`).
Frontières : lecture du moteur et du vault ; ne lance aucun tour et n'écrit rien (le renvoi à l'IA est
`attente_muette`) ; la tâche tenue par l'humain, la tâche permanente et la conversation d'un conteneur
(INV-PILOTAGE-1) n'ont pas de lecture (None) sauf « Moi » qui est une action humaine.
Invariants portés : INV-MAIN-1 (quatre états et pas un de plus, motif et geste dits), INV-MAIN-4 (« À moi » =
exactement les tâches en `humain`).
"""

from __future__ import annotations

from collections import defaultdict

from . import decisions, depot, echecs, langues, liens, reseau, temps
from .vault import Tache

ETATS = ("ia", "file", "humain", "termine")
FERMEES = ("cloture", "abandonne")
SANS_LECTURE = ("permanente",)  # INV-EXEC-7 : une tâche qui ne se termine jamais n'attend personne


class Contexte:
    """Données du poste lues une fois pour toute une série de tâches (arbre, compteur, rapport)."""

    def __init__(self, moteur):
        self.m = moteur
        self.taches = moteur.vault.index()[0]
        self.enfants: dict[str, list[str]] = defaultdict(list)
        for k, t in self.taches.items():
            if p := t.parent_brut:
                self.enfants[p].append(k)
        routines = getattr(moteur, "routines", None)
        self.routines = routines._routines() if routines else {}
        self._etat: dict[str, str] = {}

    def etat(self, ident: str) -> str:
        if ident not in self._etat:
            self._etat[ident] = self.m.etat_de(ident)
        return self._etat[ident]

    def travaille_sous(self, ident: str) -> list[str]:
        """Sous-tâches dont un agent travaille ou dont le tour attend : l'agent de la mère les attend."""
        return [k for k in self.enfants.get(ident, ()) if self.etat(k) in ("en_cours", "en_file")]


def _etat(cle: str, motif: str, phrase: str, geste: str = "", reprise: str = "", muette: bool = False) -> dict:
    return {"cle": cle, "motif": motif, "phrase": " ".join(phrase.split()), "geste": geste,
            "reprise": reprise, "muette": muette}


def _premiere_phrase(texte, n: int = 220) -> str:
    texte = " ".join(str(texte or "").split())
    return texte if len(texte) <= n else texte[:n - 1].rstrip() + "…"


def livraison_a_integrer(m, ctx: Contexte, t: Tache) -> bool:
    """Livrée sur une branche et reliée (`alimente`) à la tâche d'intégration de son projet : elle appartient
    à cette tâche, pas à l'humain (INV-INTEG-2). Un lien seulement proposé ne compte pas."""
    if not t.fiche.get("resultat") and not t.fiche.get("fait"):
        return False
    cible = depot.integration(m.vault, t.id)
    return bool(cible and cible in ctx.taches and cible != t.id and cible in liens.ids(t.fm, "alimente")
                and m.vault.ouverte(ctx.taches[cible]))


def en_attente_legitime(m, ctx: Contexte, t: Tache) -> dict | None:
    """Une tâche `en-cours` sans agent qui attend pourtant quelque chose de nommé : sous-tâche, prérequis,
    réveil, routine, report. None si rien n'explique l'attente (= attente muette)."""
    if (att := m.attente_prerequis(t.id)):
        return _etat("file", "dependance", langues.t("serveur.main.file_dependance", titres=", ".join(p["titre"] for p in att)))
    if (actives := ctx.travaille_sous(t.id)):
        return _etat("file", "dependance", langues.t("serveur.main.file_enfants", titres=", ".join(ctx.taches[k].titre for k in actives[:3])))
    if pause := m.pause_de(t.id):
        return _etat("file", "quota", pause, reprise=pause)
    if t.id in ctx.routines:
        p = m.routines.public(t.id, ctx.routines[t.id])
        return _etat("file", "horaire", langues.t("serveur.main.file_routine", quand=(p.get("prochaine") or "—").replace("T", " ")),
                     reprise=p.get("prochaine") or "")
    if temps.reportee(t):
        return _etat("file", "horaire", langues.t("serveur.main.file_report", date=str(t.fm.get("reporte_jusqu_au") or "")),
                     reprise=str(t.fm.get("reporte_jusqu_au") or ""))
    return None


def _question(m, t: Tache, profond: bool) -> str:
    q, _ = decisions.question_de(t)
    if not q and profond:
        q = decisions._depuis_journaux(m, t.id)
    return q


def _en_file(m, t: Tache) -> dict:
    ident = t.id
    if att := m.attente_prerequis(ident):
        return _etat("file", "dependance", langues.t("serveur.main.file_dependance", titres=", ".join(p["titre"] for p in att)))
    if poste := m.attente_poste(ident):
        return _etat("file", "poste", langues.t("serveur.main.file_poste", titre=poste["titre"]))
    vigie = getattr(m, "vigie", None)  # branchée par creer_app ; absente d'un moteur nu
    raison, c = (vigie.raison_attente(ident) if vigie else "") or "", m._sem
    quota = echecs.est_quota(str(t.fm.get("echec_tour") or ""))
    motif = ("quota" if quota else "memoire" if c.regule() and (c.pauses or c.depasse(c.mesure))
             else "simultanes" if c.pris >= c.limite() else "file")
    return _etat("file", motif, langues.t("serveur.main.file_motif", raison=raison or langues.t("serveur.vigie.demarrage_imminent")),
                 reprise=raison if quota else "")


def lire(m, t: Tache, ctx: Contexte | None = None, profond: bool = False) -> dict | None:
    """L'état de la main d'une tâche (voir le module) ; None hors périmètre."""
    if t.pilotage or str(t.fm.get("nature") or "") in SANS_LECTURE:
        return None
    ctx = ctx or Contexte(m)
    v, s = m.vault, t.statut
    if s in FERMEES:
        return _etat("termine", "clos", langues.t("serveur.main.termine"))
    if s == "fait":
        if v.a_valider(t):
            return _etat("humain", "valider", langues.t("serveur.main.valider", resultat=_premiere_phrase(t.fiche.get("resultat"), 160) or langues.t("detail.non_indique")), "valider")
        return _etat("termine", "fait", langues.t("serveur.main.termine"))
    if not v.ouverte(t):
        return None  # statut inconnu : ni ouvert ni fermé, aucune lecture inventée (INV-STATUT-1)
    etat = ctx.etat(t.id)
    if etat == "en_cours" or (etat == "inactif" and m.occupation(t.id)):
        tour = m.tours.get(t.id)
        return _etat("ia", "travaille", langues.t("serveur.main.ia", depuis=(getattr(tour, "depuis", "") or "")[11:16] or "—"))
    if etat == "en_file":
        return _en_file(m, t)
    if etat == "inactif" and (rang := m.poste.rang(t.id)):  # son agent attend le poste dans la file (INV-POSTE-1)
        return _etat("file", "poste", langues.t("serveur.main.file_poste_rang", rang=rang))
    if etat == "en_pause":
        return _etat("file", "quota", m.pause_de(t.id) or langues.t("detail.pause_quota"), reprise=m.pause_de(t.id) or "")
    if etat == reseau.ETAT:
        return _etat("file", "reseau", langues.t("serveur.main.file_reseau"))
    if etat == "interrompu":
        if m.reprise_auto.attendue(t.id):
            return _etat("file", "reprise", langues.t("serveur.main.file_reprise"))
        return _etat("humain", "interrompu", langues.t("serveur.main.interrompu"), "renvoyer")
    if temps.reportee(t):
        return en_attente_legitime(m, ctx, t)
    if str(t.fm.get("executant") or "") == "humain":
        return _etat("humain", "moi", langues.t("serveur.main.moi"), "confier")
    if t.id in ctx.routines:
        return en_attente_legitime(m, ctx, t)
    lance = bool(t.fm.get("session"))
    geste = "renvoyer" if lance else "confier"
    epuise = m.attente_muette.epuise(t.id)
    if s == m.vault.retour:
        if livraison_a_integrer(m, ctx, t):
            return _etat("ia", "integration", langues.t("serveur.main.integration"))
        q = _question(m, t, profond)
        if q and not epuise:
            return _etat("humain", "repondre", q, "repondre")
        if epuise:
            return _etat("humain", "epuise", langues.t("serveur.main.epuise"), "renvoyer", muette=True)
        return _etat("humain", "muette", langues.t("serveur.main.muette_retour"), "renvoyer", muette=True)
    if s == "bloque":
        if att := m.attente_prerequis(t.id):
            return _etat("file", "dependance", langues.t("serveur.main.file_dependance", titres=", ".join(p["titre"] for p in att)))
        attend = str(t.fm.get("waiting-for") or t.fm.get("waiting_for") or "").strip()
        if attend:
            return _etat("humain", "lever", langues.t("serveur.main.bloque_attend", attend=_premiere_phrase(attend, 160)), "lever")
        if echec := str(t.fm.get("echec_tour") or ""):
            return _etat("humain", "echec", langues.t("serveur.main.bloque_echec", echec=_premiere_phrase(echec, 160)), "renvoyer", muette=True)
        return _etat("humain", "lever", langues.t("serveur.main.bloque"), "lever")
    if s == "en-cours":
        if (att := en_attente_legitime(m, ctx, t)):
            return att
        if epuise:
            return _etat("humain", "epuise", langues.t("serveur.main.epuise"), "renvoyer", muette=True)
        return _etat("humain", "muette", langues.t("serveur.main.muette_en_cours"), "renvoyer", muette=True)
    # a-faire, confier-agent : la main n'est à personne tant que la tâche n'est pas confiée
    phrase = langues.t("serveur.main.a_confier" if not lance else "serveur.main.a_renvoyer")
    return _etat("humain", "confier", phrase, geste, muette=s == "confier-agent")


def toutes(m, profond: bool = False) -> dict[str, dict]:
    """Lecture de toutes les tâches ouvertes (ou à valider), hors décision reportée pour le compteur."""
    ctx = Contexte(m)
    sortie = {}
    for k, t in ctx.taches.items():
        if t.statut in ("fait", *FERMEES) and not m.vault.a_valider(t):
            continue
        if (e := lire(m, t, ctx, profond)):
            sortie[k] = e
    return sortie


def humain_par_id(m) -> dict[str, dict]:
    """Tâches en « Action humaine nécessaire » (INV-MAIN-4), avec leur lecture ; une décision reportée n'y est pas (INV-DECISIONS-3)."""
    ctx = Contexte(m)
    return {k: e for k, t in ctx.taches.items() if not temps.reportee(t) and (e := lire(m, t, ctx)) and e["cle"] == "humain"}


def compter_humain(m) -> int:
    """Le compteur « À moi » de la barre haute : exactement les tâches de la vue « À moi »."""
    return len(humain_par_id(m))


def annoter(m, noeuds: list[dict], taches: dict | None = None) -> None:
    """Pose `main` sur chaque nœud tâche de l'arbre (INV-MAIN-1)."""
    ctx = Contexte(m)
    pile = list(noeuds)
    while pile:
        n = pile.pop()
        pile.extend(n.get("enfants") or [])
        if n.get("type") == "tache" and (t := ctx.taches.get(n["id"])):
            n["main"] = lire(m, t, ctx)
