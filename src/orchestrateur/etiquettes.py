"""Étiquettes libres des tâches : mots courts posés à la main pour diriger l'IA dans les liens entre tâches.

Rôle : normaliser un mot, lire et écrire la clé `etiquettes:` d'une fiche (distincte de `tags:`, vocabulaire
fermé de l'ontologie), tenir le registre des consignes (`<données>/etat/etiquettes.json`), calculer les tâches
qui partagent une étiquette et le texte joint à la consigne d'un tour.
Frontières : écrit les fiches par `Vault.modifier` seulement (clé gérée, jamais de reformatage, INV-VAULT-1) ;
ne lance aucun tour ; le renommage et la pose en bloc passent par `lot_statuts` (annulables).
Invariants portés : INV-ETIQUETTE-1 (mot normalisé : minuscules, sans accent ni espace, 30 caractères ; pas de
doublon par casse ; clé retirée quand la liste est vide), INV-ETIQUETTE-2 (un agent ne crée jamais une
étiquette : il pose une étiquette existante ou la propose, l'utilisateur accepte), INV-ETIQUETTE-3 (une
étiquette commune borne les liens proposés et pèse dans le rapprochement ; sa consigne est jointe au tour).
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from . import fiches, langues
from .vault import Invalide

MAX_CARACTERES = 30
MAX_PAR_TACHE = 12
MAX_CONSIGNE = 600
MAX_LIEES = 12
CLE = "etiquettes"


def normaliser(brut) -> str:
    """Mot canonique : sans `#`, sans accent, en minuscules, espaces devenus `-` ; refuse le vide et le trop long."""
    texte = unicodedata.normalize("NFKD", str(brut or "").strip().lstrip("#").casefold())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"[^a-z0-9_-]", "", re.sub(r"\s+", "-", texte.strip())).strip("-_")
    if not texte:
        raise Invalide(langues.t("serveur.etiquettes.vide"))
    if len(texte) > MAX_CARACTERES:
        raise Invalide(langues.t("serveur.etiquettes.trop_long", max=MAX_CARACTERES))
    return texte


def de(fm: dict) -> list[str]:
    """Étiquettes d'une fiche : tolérant (liste ou texte séparé par des virgules), sans doublon, sans mot illisible."""
    brut = fm.get(CLE)
    if isinstance(brut, str):
        brut = brut.split(",")
    sortie: list[str] = []
    for x in brut if isinstance(brut, list) else []:
        try:
            mot = normaliser(x)
        except Invalide:
            continue
        if mot not in sortie:
            sortie.append(mot)
    return sortie


def appliquer(vault, ident: str, ajouter=(), retirer=()) -> list[str]:
    """Pose et retire des étiquettes sur une tâche ; renvoie la liste finale. N'écrit que s'il y a un changement."""
    t = vault.tache(ident)
    avant = de(t.fm)
    sorties = {normaliser(x) for x in retirer}
    apres = [x for x in avant if x not in sorties]
    for mot in map(normaliser, ajouter):
        if mot not in apres:
            apres.append(mot)
    if len(apres) > MAX_PAR_TACHE:
        raise Invalide(langues.t("serveur.etiquettes.trop_nombreuses", max=MAX_PAR_TACHE))
    if apres != avant or (t.fm.get(CLE) is not None and not isinstance(t.fm.get(CLE), list)):
        vault.modifier(ident, {CLE: apres or None})
    return apres


def utilisees(taches: dict) -> dict[str, int]:
    """Étiquette → nombre de tâches (hors conversations de conteneur) qui la portent."""
    compte: dict[str, int] = {}
    for t in taches.values():
        if not t.pilotage:  # INV-PILOTAGE-1
            for mot in de(t.fm):
                compte[mot] = compte.get(mot, 0) + 1
    return compte


class Registre:
    """Étiquettes déclarées (Réglages) et leur consigne pour l'IA. Une étiquette sans tâche reste connue tant qu'elle
    est déclarée ; la consigne vit ici, jamais dans une fiche."""

    def __init__(self, donnees: Path):
        self.chemin = Path(donnees) / "etat" / "etiquettes.json"

    def _lire(self) -> dict[str, str]:
        try:
            brut = json.loads(self.chemin.read_text(encoding="utf-8")).get("etiquettes", {})
        except (OSError, ValueError, AttributeError):
            return {}
        return {str(k): str(v or "") for k, v in brut.items()} if isinstance(brut, dict) else {}

    def _ecrire(self, d: dict[str, str]) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(self.chemin, json.dumps({"etiquettes": d}, ensure_ascii=False, indent=1))

    def declarees(self) -> dict[str, str]:
        return self._lire()

    def consigne(self, mot: str) -> str:
        return self._lire().get(mot, "")

    def declarer(self, mot: str, consigne: str | None = None) -> str:
        """Déclare une étiquette (et pose sa consigne si fournie ; vide = effacée) ; renvoie le mot canonique."""
        mot, d = normaliser(mot), self._lire()
        if consigne is not None:
            consigne = " ".join(str(consigne).split()) if "\n" not in str(consigne) else str(consigne).strip()
            if len(consigne) > MAX_CONSIGNE:
                raise Invalide(langues.t("serveur.etiquettes.consigne_longue", max=MAX_CONSIGNE))
        if mot not in d or consigne is not None:
            d[mot] = consigne if consigne is not None else d.get(mot, "")
            self._ecrire(d)
        return mot

    def oublier(self, mot: str) -> None:
        d = self._lire()
        if d.pop(mot, None) is not None:
            self._ecrire(d)

    def deplacer(self, ancien: str, nouveau: str) -> dict:
        """Renommage ou fusion : la consigne suit (les deux se suivent si chacune en portait une). Renvoie l'état
        d'avant des deux mots, que `restaurer` remet (annulation)."""
        d = self._lire()
        avant = {ancien: d.get(ancien), nouveau: d.get(nouveau)}
        a = d.pop(ancien, None)
        if a is not None:
            d[nouveau] = " ".join(dict.fromkeys(x for x in (d.get(nouveau, ""), a) if x))
            self._ecrire(d)
        return avant

    def restaurer(self, avant: dict) -> None:
        d = self._lire()
        for mot, v in avant.items():
            if v is None:
                d.pop(mot, None)
            else:
                d[mot] = v
        self._ecrire(d)


def connues(taches: dict, registre: Registre) -> dict[str, dict]:
    """Toutes les étiquettes connues : {mot: {n, consigne}} ; les plus utilisées d'abord, puis alphabétique."""
    compte, decl = utilisees(taches), registre.declarees()
    return {m: {"n": compte.get(m, 0), "consigne": decl.get(m, "")}
            for m in sorted({*compte, *decl}, key=lambda m: (-compte.get(m, 0), m))}


def communes(fm_a: dict, fm_b: dict) -> list[str]:
    b = set(de(fm_b))
    return [m for m in de(fm_a) if m in b]


def borne(fm_a: dict, fm_b: dict) -> bool:
    """INV-ETIQUETTE-3 : vrai si un lien entre ces deux tâches sort du périmètre (l'une porte des étiquettes, aucune en commun)."""
    return bool((de(fm_a) or de(fm_b)) and not communes(fm_a, fm_b))


def liees(vault, ident: str, limite: int = MAX_LIEES) -> list[dict]:
    """Les autres tâches qui partagent une étiquette avec `ident` : ouvertes d'abord, plus d'étiquettes communes d'abord."""
    taches = vault.index()[0]
    if ident not in taches:
        return []
    ma = taches[ident]
    sortie = []
    for k, t in taches.items():
        if k == ident or t.pilotage or not (c := communes(ma.fm, t.fm)):
            continue
        sortie.append(((not vault.ouverte(t), -len(c), t.titre.casefold()),
                       {"id": k, "titre": t.titre, "statut": t.statut, "etiquettes": c,
                        "situation": " ".join(str((t.fiche or {}).get("situation") or "").split())[:160]}))
    sortie.sort(key=lambda x: x[0])
    return [x for _, x in sortie[:max(1, limite)]]


def vue(vault, registre: Registre, ident: str) -> dict:
    """Ce que l'API sert pour une tâche : ses étiquettes, leur consigne, les tâches liées par étiquette."""
    t = vault.tache(ident)
    mots = de(t.fm)
    decl = registre.declarees()
    return {"etiquettes": mots, "consignes_etiquettes": {m: decl[m] for m in mots if decl.get(m)},
            "liees_etiquette": liees(vault, ident) if mots else []}


def texte_tour(v: dict) -> str:
    """Bloc joint à la consigne d'un tour (vide si la tâche n'a aucune étiquette)."""
    if not v["etiquettes"]:
        return ""
    lignes = ["", langues.t("serveur.etiquettes.tour_titre", mots=", ".join(f"#{m}" for m in v["etiquettes"]))]
    if v["consignes_etiquettes"]:
        lignes.append(langues.t("serveur.etiquettes.tour_consignes"))
        lignes += [f"- #{m} : {c}" for m, c in v["consignes_etiquettes"].items()]
    if v["liees_etiquette"]:
        lignes.append(langues.t("serveur.etiquettes.tour_liees"))
        lignes += [f"- {x['id']} [{x['statut'] or '?'}] {x['titre']}" + (f" — {x['situation']}" if x["situation"] else "")
                   + f" ({' '.join('#' + m for m in x['etiquettes'])})" for x in v["liees_etiquette"]]
    lignes.append(langues.t("serveur.etiquettes.tour_regle"))
    return "\n".join(lignes)
