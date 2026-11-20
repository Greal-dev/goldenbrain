"""Compactage automatique des conversations d'agents : seuil général, héritage, repli, mesure.

Rôle : calculer le seuil de compactage d'une tâche (% de la fenêtre du modèle, plafond absolu en
jetons facultatif ; héritage tâche -> contexte du projet -> réglage général), le faire traduire par
l'adaptateur du harnais (`harnais.compactage`), envoyer l'ordre de compactage entre deux tours quand
le harnais n'a pas de mécanisme natif, et consigner chaque tour dans le journal de mesure
(`<donnees>/etat/mesures.jsonl`) pour régler le seuil sur des données.
Frontières : ne lance un tour que par `_tour_au_poste` du moteur (un seul chemin de lancement) ;
n'écrit rien dans le vault ; lit seulement les frontmatters de la tâche et du contexte de son projet.
Mélangé au `Moteur` (config, vault, registre, files, publier).
Invariants portés : INV-COMPACT-1.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from functools import cached_property

from . import codespace, depot, economie, instrumentation
from .propositions import maintenant

log = logging.getLogger(__name__)

# Fenêtres par défaut, en jetons : motif cherché dans le nom du modèle (minuscules, sans `@effort`),
# premier trouvé gagne. Valeurs de départ à vérifier à l'usage (la table se corrige dans
# `[compactage.fenetres]` de config.toml, qui prime) ; le dernier recours est FENETRE_INCONNUE.
FENETRES_DEFAUT = (("[1m]", 1_000_000), ("gemini", 1_048_576), ("gpt", 272_000), ("codex", 272_000),
                   ("claude", 200_000), ("opus", 200_000), ("sonnet", 200_000), ("haiku", 200_000),
                   ("fable", 200_000))
FENETRE_INCONNUE = 200_000
# Tranches de taille de contexte de la vue de mesure : borne basse en jetons.
TRANCHES = (0, 50_000, 100_000, 200_000, 400_000)
SIGNAUX_ECHEC = ("tour_en_echec", "relance", "porte_rouge", "terminee_refusee")  # « interrompu » est un geste humain, pas un échec
BAISSE = 0.7  # un contexte tombé sous 70 % du précédent marque un compactage (natif, non vu)
LIGNES_MAX = 20_000  # relecture bornée du journal de mesure


def fenetre(modele: str, personnalisees: dict | None = None) -> int:
    """Fenêtre en jetons d'un modèle : table de la configuration d'abord (motif le plus long), puis
    défauts ; `[1m]` (variante à un million de jetons) l'emporte sur le nom de famille."""
    nom = (modele or "").split("@")[0].lower()
    for motif, n in sorted((personnalisees or {}).items(), key=lambda kv: -len(kv[0])):
        if motif.lower() in nom:
            return int(n)
    return next((n for motif, n in FENETRES_DEFAUT if motif in nom), FENETRE_INCONNUE)


def seuil_jetons(pct: float, plafond: int, fen: int) -> int:
    """Seuil de déclenchement : le premier atteint de `pct` % de la fenêtre et du plafond absolu."""
    s = max(1, int(fen * pct / 100))
    return min(s, plafond) if plafond > 0 else s


def _nombre(v, borne: tuple[float, float], entier: bool = False):
    """Valeur de frontmatter valide ou None (une valeur illisible laisse jouer le niveau suivant)."""
    try:
        n = int(v) if entier else float(v)
    except (TypeError, ValueError):
        return None
    return n if borne[0] <= n <= borne[1] else None


def reglage(config, fm_tache: dict, fm_projet: dict) -> dict:
    """Héritage : tâche -> contexte du projet -> réglage général, champ par champ."""
    pct, plafond, origine = config.compactage.pct, config.compactage.plafond, {"pct": "general", "plafond": "general"}
    for niveau, fm in (("projet", fm_projet), ("tache", fm_tache)):
        if (p := _nombre(fm.get("compactage_pct"), (1, 100))) is not None:
            pct, origine["pct"] = p, niveau
        if (q := _nombre(fm.get("compactage_plafond"), (0, 10**9), True)) is not None:
            plafond, origine["plafond"] = q, niveau
    return {"pct": pct, "plafond": plafond, "origine": origine}


def tranche(contexte) -> str:
    if not isinstance(contexte, int) or contexte < 0:
        return "inconnue"
    bas = max(b for b in TRANCHES if b <= contexte)
    haut = next((b for b in TRANCHES if b > contexte), None)
    return f"{bas // 1000}–{haut // 1000} k" if haut else f"≥ {bas // 1000} k"


class Mesures:
    """Journal de mesure : une ligne JSON par tour, ajoutée à `mesures.jsonl` (hors vault)."""

    def __init__(self, fichier):
        self.fichier = fichier

    def ajouter(self, m: dict) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            with open(self.fichier, "a", encoding="utf-8") as f:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("mesure non consignée : %s", e)

    def lire(self) -> list[dict]:
        try:
            lignes = self.fichier.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        sortie = []
        for ligne in lignes[-LIGNES_MAX:]:
            try:
                m = json.loads(ligne)
            except ValueError:
                continue
            if isinstance(m, dict):
                sortie.append(m)
        return sortie

    def synthese(self) -> list[dict]:
        """Par harnais et par tranche de contexte : tours, durée moyenne, taux d'échec. Les tours
        d'ordre de compactage sont comptés à part (`compactages`), hors des moyennes."""
        groupes: dict[tuple[str, str], list[dict]] = {}
        compactages: dict[str, int] = {}
        for m in self.lire():
            if m.get("type"):
                continue  # attente, gel : lignes d'instrumentation, hors tours
            h = str(m.get("harnais") or "?")
            if m.get("compactage"):
                compactages[h] = compactages.get(h, 0) + 1
                continue
            groupes.setdefault((h, tranche(m.get("contexte"))), []).append(m)
        libelles = [tranche(b) for b in TRANCHES]
        sortie = []
        for (h, t), ms in sorted(groupes.items(), key=lambda kv: (
                kv[0][0], libelles.index(kv[0][1]) if kv[0][1] in libelles else len(libelles))):
            durees = [float(m["duree_s"]) for m in ms if isinstance(m.get("duree_s"), (int, float))]
            echecs = sum(any(s in SIGNAUX_ECHEC for s in m.get("signaux") or []) for m in ms)
            sortie.append({"harnais": h, "tranche": t, "tours": len(ms),
                           "duree_moyenne_s": round(sum(durees) / len(durees), 1) if durees else None,
                           "taux_echec": round(echecs / len(ms), 3), "apres_compactage": sum(
                               bool(m.get("apres_compactage")) for m in ms),
                           "compactages": compactages.get(h, 0)})
        return sortie


class MixinCompactage:
    @cached_property
    def mesures(self) -> Mesures:
        return Mesures(self.config.donnees / "etat" / "mesures.jsonl")

    @cached_property
    def _suivi(self) -> dict:
        return {}  # tâche -> tour en cours : début, harnais, modèle, fenêtre, seuil

    @cached_property
    def _dernier(self) -> dict:
        return {}  # tâche -> contexte connu au dernier tour réussi

    @cached_property
    def _apres(self) -> set:
        return set()  # tâches dont le prochain tour suit un compactage (ordre envoyé par le moteur)

    @cached_property
    def mesure_tour(self) -> dict:
        return {}  # tâche -> `mesure` de l'événement `fin` du tour en cours

    def _fm_projet(self, t) -> dict:
        try:
            return self.vault._lire_meta(self.vault.racine / t.conteneur / self.config.vault.contexte)[0]
        except OSError:
            return {}

    def seuil_de(self, t, harnais: str, modele: str) -> dict:
        """Seuil effectif d'une tâche pour un harnais et un modèle (INV-COMPACT-1)."""
        r = reglage(self.config, t.fm, self._fm_projet(t))
        nom = modele or str(self.config.harnais.get(harnais, {}).get("modele_defaut") or harnais)
        fen = fenetre(nom, self.config.compactage.fenetres)
        return {**r, "fenetre": fen, "seuil": seuil_jetons(r["pct"], r["plafond"], fen)}

    def instancier(self, ident: str, t, harnais: str, modele: str, fabrique):
        """Adaptateur du tour : dossier de travail du projet, seuil de compactage posé (l'adaptateur le
        traduit en son option native) et suivi de mesure ouvert."""
        conf = codespace.conf_tour(depot.conf_harnais(
            self.vault, self.config.harnais.get(harnais, {}), ident), harnais, self.vault, t)
        if t.fm.get("mcp") == "heritage":  # INV-MCP-1 : dérogation par tâche (navigateur, etc.)
            conf = {**conf, "mcp": "heritage"}
        instance = fabrique(conf)
        s = self.seuil_de(t, harnais, modele)
        instance.compactage = (100 * s["seuil"] / s["fenetre"], s["seuil"])
        self._suivi[ident] = {"debut": time.monotonic(), "harnais": harnais, "modele": modele,
                              "fenetre": s["fenetre"], "seuil": s["seuil"]}
        return self.executeurs.envelopper(ident, harnais, instance)  # INV-DISTANT-2

    def noter_mesure(self, ident: str, envoi, tour, erreur, refus: bool = False) -> None:
        """Fin de tour (réussi, en échec ou interrompu) : une ligne au journal de mesure."""
        s, fin = self._suivi.pop(ident, None), self.mesure_tour.pop(ident, None) or {}
        if not s:
            return  # le tour a échoué avant tout lancement
        contexte, interrompu = instrumentation.borner_contexte(fin.get("contexte"), s["fenetre"]), bool(tour and tour.arrete)
        avant = self._dernier.get(ident)
        compacte = envoi.role == "compactage"
        signaux = [n for n, vrai in (("tour_en_echec", bool(erreur) and not interrompu),
                                     ("interrompu", interrompu), ("relance", envoi.reprise),
                                     ("porte_rouge", refus), ("terminee_refusee", refus)) if vrai]
        self.mesures.ajouter({
            "date": maintenant(), "tache": ident, "harnais": s["harnais"], "modele": s["modele"],
            "contexte": contexte, "fenetre": s["fenetre"], "seuil": s["seuil"], "cout": fin.get("cout"),
            "duree_s": round(time.monotonic() - s["debut"], 1), "signaux": signaux,
            "compactage": compacte, "rss_ko": fin.get("rss_ko"), "petits_fils": fin.get("petits_fils"),
            "apres_compactage": not compacte and (ident in self._apres or bool(
                contexte and avant and contexte < BAISSE * avant))})
        if not compacte:
            self._apres.discard(ident)
        if contexte and contexte > economie.CONTEXTE_ALERTE and not compacte:  # INV-ECO-1 : alerte, jamais d'arrêt
            self.publier("alerte_contexte", tache=ident, contexte=contexte, seuil=economie.CONTEXTE_ALERTE)
        # Après un compactage, le contexte connu est oublié : un second ordre n'est envoyé que si
        # le tour suivant dépasse de nouveau le seuil (pas d'ordre en boucle sur un compactage vain).
        self._dernier[ident] = None if compacte else (contexte if not erreur else avant)

    async def _preparer_compactage(self, ident: str, envoi):
        """Repli commun (INV-COMPACT-1) : avant le message suivant, si le dernier tour a dépassé le
        seuil et que le harnais n'a pas de mécanisme natif, envoie l'ordre de compactage en tour,
        puis rappelle la fiche. Rend l'envoi à jouer, ou None si l'humain a arrêté la tâche entre-temps."""
        if envoi.role not in ("", "tache") or not (dernier := self._dernier.get(ident)):
            return envoi
        t = self.vault.tache(ident)
        nom = envoi.harnais or str(t.fm.get("harnais") or self.config.moteur.harnais_defaut)
        fabrique = self.registre.get(nom)
        ordres = self.config.compactage.ordres
        ordre = ordres[nom] if nom in ordres else getattr(fabrique, "ordre_compactage", "")
        if not fabrique or getattr(fabrique, "compactage_natif", False) or not ordre:
            return envoi
        modele = envoi.modele if envoi.modele is not None else str(t.fm.get("modele") or "")
        if dernier < self.seuil_de(t, nom, modele)["seuil"]:
            return envoi
        self._dernier[ident] = None
        try:
            await self._tour_au_poste(ident, replace(envoi, texte=ordre, role="compactage", sauts=0, de="",
                                                     source="", mandat=False))
        except Exception as e:  # un compactage raté ne doit pas perdre le message qui suit
            log.warning("compactage de %s non fait : %s", ident, e)
        if self.etat_de(ident) == "interrompu":
            return None
        self._apres.add(ident)
        t = self.vault.tache(ident)
        rappel = (f"[Le contexte de cette conversation vient d'être compacté. Avant de poursuivre, relis ta "
                  f"fiche ({t.chemin}) et le contexte du projet "
                  f"({self.vault.racine / t.conteneur / self.config.vault.contexte}) : ne perds rien d'essentiel.]\n\n")
        return replace(envoi, texte=rappel + envoi.texte)

    async def _conclure_tour(self, ident: str, tour, final, erreur, envoi) -> None:
        """Conclusion d'un tour, puis ligne de mesure (le verdict du contrôle n'est connu qu'ici). Un
        ordre de compactage ne passe ni par le contrôle ni par le statut."""
        refus = False
        try:
            if envoi.role == "compactage":
                return self._conclure_compactage(ident, tour, final, erreur)
            await self._controler(ident, final, erreur, tour)  # INV-CONTROLE-1
            v = self._verdicts_tour.get(ident)  # lu avant `_conclure`, qui le consomme
            refus = bool(v and v["verdict"] != "reussi")
            self._conclure(ident, tour, final, erreur, envoi.sauts, envoi.de or envoi.source)
        finally:
            self.noter_mesure(ident, envoi, tour, erreur, refus)

    def _conclure_compactage(self, ident: str, tour, final, erreur) -> None:
        """Fin d'un tour d'ordre de compactage : ni statut ni fiche (le texte rendu n'est pas une
        fiche) ; un échec se journalise, la file continue."""
        if erreur and not (tour and tour.arrete):
            self._journaliser_echec(ident, erreur, f"Compactage non fait : {erreur}")
        self.publier("tour_fin", tache=ident, statut="en-cours", fiche_absente=False, compactage=True,
                     **({"erreur": erreur} if erreur else {}))
        self.publier("arbre")

    def compactage_public(self) -> dict:
        """État pour les Réglages : seuil général, fenêtres effectives, mécanisme par harnais."""
        c = self.config.compactage
        return {"pct": c.pct, "plafond": c.plafond, "fenetres": {**dict(FENETRES_DEFAUT), **c.fenetres},
                "fenetre_inconnue": FENETRE_INCONNUE,
                "harnais": {nom: {"natif": bool(getattr(f, "compactage_natif", False)),
                                  "ordre": c.ordres[nom] if nom in c.ordres else getattr(f, "ordre_compactage", "")}
                            for nom, f in self.registre.items()}}
