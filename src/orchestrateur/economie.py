"""Curseur Performance ↔ Économie : moteur du travail principal d'une tâche, motivé.

Rôle : décider le harnais et le modèle d'un tour de tâche quand l'humain n'a rien imposé — profil de
la tâche (règles déterministes) → famille (rapide, sonnet, opus), escalade après deux échecs
consécutifs, descente quand un contrôle requis sert d'oracle, décalage par la position du curseur
(réglage général, `economie:` d'un contexte ou d'une tâche), mode intelligent (indice de rythme des
quotas avec hystérésis), équilibrage entre fournisseurs avant la première conversation, proposition
de bascule pour une conversation commencée. Compte les échecs consécutifs (`<donnees>/etat/economie.json`).
Frontières : ne lance aucun tour ; n'écrit dans le vault que le motif (`moteur_motif`) ; ne change
jamais le harnais d'une conversation commencée (la bascule est une proposition, acceptée par
`changer_moteur`) ; mesure déléguée à `conso`.
Invariants portés : INV-ECO-1 (un modèle ou un moteur posé à la main l'emporte toujours ; jamais le
défaut implicite du harnais quand une famille est connue ; une conversation commencée garde son
harnais), INV-ECO-2 (aucune décision sur donnée de quota absente ou douteuse).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass

from . import conso, depot, fiches, langues
from .config import FAMILLES_MODELE, POSITIONS

log = logging.getLogger(__name__)
DECALAGE = {"economie_max": -2, "economie": -1, "intelligent": 0, "performance": 1, "performance_max": 2}


def libelle(position: str) -> str:
    return {"economie_max": langues.t("serveur.economie.libelle_economie_max"),
            "economie": langues.t("serveur.economie.libelle_economie"),
            "intelligent": langues.t("serveur.economie.libelle_intelligent"),
            "performance": langues.t("serveur.economie.libelle_performance"),
            "performance_max": langues.t("serveur.economie.libelle_performance_max")}[position]


# Positions où le fournisseur d'une tâche neuve peut changer selon la tension des quotas.
EQUILIBRAGE = ("economie_max", "economie", "intelligent")
CONTEXTE_ALERTE = 250_000  # jetons de contexte au-delà desquels un tour est signalé (coût, dérive)
# Profil : première règle qui s'applique au titre et au corps de la tâche.
REGLES = (
    ("rapide", lambda: langues.t("serveur.economie.profil_tri"), re.compile(
        r"\b(tri(er)?|class(er|ement)|ranger|relev(er|é)|inventaire|recenser)\b", re.I)),
    ("sonnet", lambda: langues.t("serveur.economie.profil_integration"), re.compile(
        r"\b(int[ée]gr(er|ation)|fusionn?(er|ion)|rejeu|rejouer)\b[^\n]{0,60}\b(branches?|porte|lot|correctifs?|mvp)\b", re.I)),
    ("opus", lambda: langues.t("serveur.economie.profil_conception"), re.compile(
        r"\b(architecture|refonte|conception|concevoir|d[ée]bog\w*|migration|strat[ée]gi\w*)\b", re.I)),
)
LONGUE = 6000  # caractères de corps au-delà desquels la tâche monte d'un cran


@dataclass
class Decision:
    harnais: str
    modele: str
    famille: str = ""
    position: str = ""
    motif: str = ""
    bascule: dict | None = None  # {vers, motif} : proposée, jamais appliquée d'office


def cran(famille: str, pas: int) -> str:
    i = FAMILLES_MODELE.index(famille) + pas
    return FAMILLES_MODELE[min(len(FAMILLES_MODELE) - 1, max(0, i))]


def profil(texte: str, a_depot: bool, oracle: bool, defaut: str) -> tuple[str, str]:
    """Famille utile d'une tâche et son motif, par règles déterministes."""
    regle = next((x for x in REGLES if x[2].search(texte)), None)
    if regle:
        famille, motif = regle[0], regle[1]()
    elif a_depot:
        famille, motif = "sonnet", langues.t("serveur.economie.profil_depot")
    else:
        famille, motif = defaut, langues.t("serveur.economie.profil_defaut")
    if len(texte) > LONGUE and famille != "opus" and regle is not REGLES[1]:  # jamais un cran de plus : on délègue
        famille, motif = cran(famille, 1), langues.t("serveur.economie.tache_longue", motif=motif)
    if oracle and famille == "opus":
        famille, motif = "sonnet", langues.t("serveur.economie.oracle", motif=motif)
    return famille, motif


def impose(fm: dict) -> bool:
    """Case « moteur imposé » de la fiche (posée par tout choix fait à la main)."""
    return str(fm.get("moteur_impose") or "").strip().lower() not in ("", "false", "non", "0")


def pct(x: float) -> str:
    return f"{round(100 * x)} %"


def duree(s: float) -> str:
    h = max(0, round(s / 3600))
    return f"{h} h" if h < 48 else f"{round(h / 24)} j"


class Economie:
    def __init__(self, moteur):
        self.m = moteur
        self.config = moteur.config
        self.conso = conso.Conso(moteur.config)
        self.fichier = moteur.config.donnees / "etat" / "economie.json"
        self.etats: dict[str, int] = {}  # harnais -> état du mode intelligent (-1, 0, +1)
        moteur.roles.economie = self  # les rôles éphémères sont des conversations neuves
        try:
            self.echecs: dict[str, int] = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.echecs = {}

    # --- position ---------------------------------------------------------------------------
    def position(self, t) -> str:
        """Position effective : la tâche, puis le contexte le plus proche, puis le réglage général."""
        if (p := str(t.fm.get("economie") or "")) in POSITIONS:
            return p
        try:
            ctx = depot.contextes(self.m.vault, t.id)
        except Exception:  # noqa: BLE001 — un contexte illisible ne bloque pas un tour
            ctx = []
        return next((str(fm["economie"]) for _, fm in ctx if str(fm.get("economie") or "") in POSITIONS),
                    self.config.economie.position)

    # --- mode intelligent -------------------------------------------------------------------
    def tension(self, harnais: str) -> tuple[float, str] | None:
        """Rythme de la fenêtre la plus tendue du harnais et sa description ; None sans donnée."""
        now = time.time()
        mesures = [(p, f) for f in self.conso.fenetres(harnais) if (p := f.rythme(now)) is not None]
        if not mesures:
            return None
        p, f = max(mesures, key=lambda x: x[0])
        return p, langues.t("serveur.economie.tension", harnais=harnais, part=pct(f.part), fenetre=f.nom)

    def intelligent(self, harnais: str) -> tuple[int, str]:
        """Décalage du mode intelligent (-1, 0, +1) et son motif, avec hystérésis (INV-ECO-2)."""
        e, now = self.config.economie, time.time()
        fenetres = [f for f in self.conso.fenetres(harnais) if f.rythme(now) is not None]
        if not fenetres:
            self.etats.pop(harnais, None)
            return 0, langues.t("serveur.economie.sans_donnee", harnais=harnais)
        p = max(f.rythme(now) for f in fenetres)
        longue = max(fenetres, key=lambda f: f.duree_s)
        reste = longue.renouvellement - now
        proche = reste < e.proche_renouvellement * longue.duree_s and longue.part < 0.8
        ancien = self.etats.get(harnais, 0)
        if p > e.seuil_haut or (ancien == -1 and p > e.seuil_haut - e.hysteresis):
            nouveau = -1
        elif proche and (p < e.seuil_bas or (ancien == 1 and p < e.seuil_bas + e.hysteresis)):
            nouveau = 1
        else:
            nouveau = 0
        self.etats[harnais] = nouveau
        detail = langues.t("serveur.economie.credit_restant", reste=pct(1 - longue.part), nom=longue.nom,
                           duree=duree(reste), rythme=f"{p:.2f}")
        return nouveau, {-1: langues.t("serveur.economie.intelligent_economie", detail=detail),
                         0: langues.t("serveur.economie.intelligent_neutre", detail=detail),
                         1: langues.t("serveur.economie.intelligent_performance", detail=detail)}[nouveau]

    # --- choix du fournisseur ---------------------------------------------------------------
    def _candidats(self, prevu: str, famille: str) -> list[str]:
        ordre = [prevu, *self.config.credits.get(famille, [])]
        # INV-QUOTA-1 : un compte épuisé ou un harnais absent du poste n'est jamais choisi.
        q = getattr(self.m, "quota", None)
        return [h for i, h in enumerate(ordre) if h not in ordre[:i] and h in self.m.registre
                and (h == prevu or ((self.config.harnais.get(h, {}).get("familles") or {}).get(famille)
                                    and not (q and q.epuise(h)) and self.m.roles.installe(h)))]

    def _moins_tendu(self, prevu: str, famille: str) -> tuple[str, str] | None:
        """Autre fournisseur nettement moins tendu que le prévu, ou None (INV-ECO-2)."""
        if (tp := self.tension(prevu)) is None:
            return None
        mesures = [(t[0], h, t[1]) for h in self._candidats(prevu, famille)[1:]
                   if (t := self.tension(h)) is not None]
        if not mesures:
            return None
        p, h, desc = min(mesures)
        if tp[0] - p <= self.config.economie.ecart_bascule:
            return None
        return h, langues.t("serveur.economie.prevu", prevu=prevu, vers=h, tension=tp[1], desc=desc)

    def pour_role(self, famille: str) -> tuple[str, list[str]]:
        """Rôle éphémère (persona, mandat, conseil, jardinage, fiche) : famille décalée par la position
        générale, ordre des crédits avec le fournisseur nettement moins tendu en tête (INV-ECO-1)."""
        position, ordre = self.config.economie.position, list(self.config.credits.get(famille, []))
        pas = DECALAGE[position]
        if position == "intelligent" and ordre:
            pas = self.intelligent(ordre[0])[0]
        famille = cran(famille, pas)
        ordre = list(self.config.credits.get(famille, ordre))
        if position in EQUILIBRAGE and ordre and (choix := self._moins_tendu(ordre[0], famille)):
            ordre.sort(key=lambda h: h != choix[0])
        return famille, ordre

    # --- décision ---------------------------------------------------------------------------
    def decider(self, t, derivee: bool = False) -> Decision:
        """Harnais et modèle du travail principal de la tâche `t` (INV-ECO-1)."""
        fm = t.fm
        prevu = str(fm.get("harnais") or self.config.moteur.harnais_defaut)
        if fm.get("modele"):
            return Decision(prevu, str(fm["modele"]), motif=langues.t("serveur.economie.main"))
        session = bool(fm.get("session")) or derivee  # une dérivation garde le harnais de sa mère
        texte = f"{t.titre}\n{fiches.corps_sans_fiche(fiches.lire(t.chemin))}" if t.chemin.is_file() else t.titre
        try:
            ctx = depot.contextes(self.m.vault, t.id)
        except Exception:  # noqa: BLE001
            ctx = []
        famille, motif = profil(texte, any(fm_c.get("depot") for _, fm_c in ctx) or bool(fm.get("depot")),
                                any(fm_c.get("controle") for _, fm_c in ctx),
                                self.config.economie.famille_defaut)
        if self.echecs.get(t.id, 0) >= 2:
            famille, motif = cran(famille, 1), langues.t("serveur.economie.escalade", motif=motif, n=self.echecs[t.id])
        position = self.position(t)
        harnais, bascule = prevu, None
        if not session and not impose(fm) and position in EQUILIBRAGE:
            if choix := self._moins_tendu(prevu, famille):
                harnais, motif = choix[0], f"{motif} ; {choix[1]}"
        elif session and not impose(fm):
            if choix := self._moins_tendu(prevu, famille):  # INV-ECO-1 : proposée seulement
                bascule = {"vers": choix[0], "motif": choix[1]}
        pas = DECALAGE[position]
        if position == "intelligent":
            pas, detail = self.intelligent(harnais)
            motif = f"{motif} ; {detail}"
        elif pas:
            motif = langues.t("serveur.economie.curseur", motif=motif, curseur=libelle(position))
        famille = cran(famille, pas)
        modele = str((self.config.harnais.get(harnais, {}).get("familles") or {}).get(famille, ""))
        if not modele:
            motif = langues.t("serveur.economie.sans_table", motif=motif, harnais=harnais)
        return Decision(harnais, modele, famille, position, f"{famille} — {motif}", bascule)

    def pour_tour(self, t, derivee: bool = False) -> Decision:
        """Décision d'un tour : le motif est porté sur la tâche quand il change."""
        d = self.decider(t, derivee)
        if d.motif and t.fm.get("moteur_motif") != d.motif:
            try:
                self.m.vault.modifier(t.id, {"moteur_motif": d.motif})
            except Exception as e:  # noqa: BLE001 — un motif non écrit ne bloque pas le tour
                log.warning("motif du moteur non écrit pour %s : %s", t.id, e)
        return d

    # --- issue des tours --------------------------------------------------------------------
    def issue(self, ident: str, statut: str, final: str | None) -> None:
        """Compte les échecs consécutifs : tour en échec, ou « terminée » refusée par le contrôle."""
        refusee = bool(final) and fiches.declaration(final) == "terminee" and statut != "fait"
        avant = self.echecs.get(ident, 0)
        if statut == "bloque" or refusee:
            self.echecs[ident] = avant + 1
        elif statut in ("fait", "en-cours", self.m.vault.retour):
            self.echecs.pop(ident, None)
        if self.echecs.get(ident, 0) != avant:
            try:
                self.fichier.parent.mkdir(parents=True, exist_ok=True)
                fiches.ecrire_atomique(self.fichier, json.dumps(self.echecs))
            except OSError as e:
                log.warning("échecs non persistés : %s", e)

    # --- état public ------------------------------------------------------------------------
    def public(self) -> dict:
        harnais = [h for h in self.m.registre]
        quotas = {}
        for h in harnais:
            now = time.time()
            fen = self.conso.fenetres(h)
            quotas[h] = [{**asdict(f), "rythme": f.rythme(now)} for f in fen]
        position = self.config.economie.position
        effectif = {h: self.intelligent(h)[1] for h in harnais} if position == "intelligent" else {}
        return {"position": position, "positions": [[p, libelle(p)] for p in POSITIONS],
                "famille_defaut": self.config.economie.famille_defaut, "quotas": quotas,
                "motifs": effectif, "conso": self.conso.periode(7),
                "epuises": self.m.quota.public() if hasattr(self.m, "quota") else {}}  # INV-QUOTA-1
