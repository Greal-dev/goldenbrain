"""Validation automatique par périmètre : clôture sur contrôle déterministe et revue IA indépendante.

Rôle : un conteneur (projet, opération) déclare `validation: automatique` dans son `contexte.md`
(le plus proche l'emporte, la tâche peut surcharger) : c'est l'accord écrit de l'utilisateur, borné
à ce périmètre, tracé par `validation_accord:`. Une tâche « faite » de ce périmètre passe à
`cloture` seulement si (a) le contrôle requis (INV-CONTROLE-1) est réussi et non périmé, (b) une
revue IA indépendante de l'auteur rend GO sans aucun P1, (c) la fiche porte Résultat et Essai ;
hors exclusions ; une clôture sur N reste proposée à l'utilisateur (audit par échantillon).
Persistance : `<donnees>/etat/validation_auto.json` (compteur, journal des issues), relu à chaque
lecture.
Frontières : ne lance aucun contrôle (il lit le verdict du moteur) ; la revue passe par le tour de
persona de `revues` ; n'écrit dans le vault que `cloture` (clôture), `fait` (geste « Rouvrir ») et
les clés `validation`, `validation_accord` d'un `contexte.md` (geste de réglage).
Invariants portés : INV-VALID-2 (exclusions en mots entiers ; « réévaluer » ne clôt jamais), INV-EXECUTANT-1 (jamais de validation automatique d'une tâche « Moi »).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import unicodedata
from pathlib import Path

from . import depot, executant, fiches, langues
from .propositions import maintenant
from .roles import Choix
from .vault import Conflit, Invalide, NonTrouve

log = logging.getLogger(__name__)
MODES = ("manuelle", "automatique")
ECHANTILLON_DEFAUT = 5
JOURS_VISIBLES = 7
# INV-VALID-2 : toujours à l'utilisateur, même en automatique (mots cherchés dans le titre et les tags).
# Mots entiers (frontière de mot, accents ignorés) ; un « * » final ouvre la fin du mot (« deploi* »).
EXCLUSIONS_DEFAUT = ("infra", "infrastructure", "deploi*", "deploy*", "production", "suppression",
                     "supprimer", "structure du vault", "argent", "paiement", "virement", "banque",
                     "facture", "factures", "identite", "mot de passe", "secret", "secrets", "envoi",
                     "envois", "envoyer", "publication", "publications", "publier", "mail", "mails")
# Expressions internes qui contiennent un mot exclu sans viser le geste (retirées du texte avant la
# recherche) ; `validation_exemptions` d'un contexte les complète.
EXEMPTIONS_DEFAUT = ("garde de publication",)
# INV-VALID-2 : un Essai qui décrit un geste dans l'interface (ouvrir, cliquer, regarder) est démontrable :
# la clôture reste à l'utilisateur. Motifs normalisés par `_norme`, cherchés en début de mot.
DEMONTRABLE_MOTIFS = ("interface", "127.0.0.1", "localhost", "http://", "navigateur", "clic", "cliquer",
                      "clique", "bouton", "page", "onglet", "glisser", "deposer", "selecteur", "menu",
                      "affichage", "afficher", "ecran", "icone", "volet", "fenetre")
REVUE = {"id": "revue-auto", "harnais": "", "modele": "",
         "mandat": "Tu relis, en regard indépendant de l'auteur, le travail livré par une tâche avant "
                   "sa clôture automatique. Lis la fiche, le dépôt à l'état vérifié et le transcript. "
                   "Classe chaque constat P1, P2 ou P3 ; un P1 nomme l'invariant violé (sécurité "
                   "exploitable, perte de données, contrat publié cassé, régression factuelle, écart à "
                   "la demande de la tâche). Écris chaque point « [P1] … », « [P2] … » ou « [P3] … ».",
         "focus": "verdict: ok s'il n'y a aucun P1 (les P2 et P3 n'empêchent pas ok) ; reserves sinon. "
                  "Tu ne produis jamais le feu vert du contrôle : il est déjà rendu par la machine."}


def _norme(texte: str) -> str:
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return " ".join(t.casefold().split())


def demontrable(t) -> str:
    """Motif de démontrabilité : `demontrable: oui|non` en frontmatter de la tâche tranche (non = auto
    forcé) ; sinon le premier motif de l'Essai de la fiche ; « » si la tâche n'est pas démontrable."""
    marque = _norme(t.fm.get("demontrable"))
    if marque in ("oui", "true", "vrai"):
        return "marqueur demontrable: oui"
    if marque in ("non", "false", "faux"):
        return ""
    essai = _norme(t.fiche.get("essai"))
    for mot in DEMONTRABLE_MOTIFS:
        if re.search(rf"(?<![a-z0-9]){re.escape(_norme(mot))}", essai):
            return langues.t("serveur.validation_auto.essai", mot=mot)
    return ""


def _entier(v, defaut: int) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return defaut


def reglage(vault, ident: str) -> dict:
    """Réglage effectif : chaque clé vient de la tâche, sinon du conteneur le plus proche qui la
    déclare. `mode` vaut `manuelle` par défaut ; valeur inconnue = `manuelle` (jamais présumée)."""
    t = vault.tache(ident)
    sources = [(ident, t.fm)] + depot.contextes(vault, ident)
    r = {"mode": "manuelle", "declare_par": "", "accord": "", "exclusions": list(EXCLUSIONS_DEFAUT),
         "exemptions": list(EXEMPTIONS_DEFAUT), "echantillon": ECHANTILLON_DEFAUT}
    vus = set()
    for origine, fm in sources:
        if "mode" not in vus and str(fm.get("validation") or "").strip():
            vus.add("mode")
            mode = str(fm["validation"]).strip().casefold()
            r.update(mode=mode if mode in MODES else "manuelle", declare_par=origine,
                     accord=str(fm.get("validation_accord") or ""))
        for cle, nom in (("exclusions", "validation_exclusions"), ("exemptions", "validation_exemptions")):
            if cle not in vus and (brut := fm.get(nom)) is not None:
                vus.add(cle)  # lecture tolérante : liste YAML, ou « [a, b] » resté en texte
                liste = brut if isinstance(brut, list) else str(brut).strip().strip("[]").split(",")
                r[cle] = [str(x).strip().strip("\"'") for x in liste if str(x).strip()]
        if "echantillon" not in vus and fm.get("validation_echantillon") is not None:
            vus.add("echantillon")
            r["echantillon"] = _entier(fm["validation_echantillon"], ECHANTILLON_DEFAUT)
    return r


def exclusion(t, mots: list[str], exemptions=EXEMPTIONS_DEFAUT) -> str:
    """Premier mot d'exclusion trouvé, en mot entier, dans le titre ou les tags de la tâche ; « »
    sinon. Les exemptions (expressions) sont retirées du texte avant la recherche."""
    tags = t.fm.get("tags") if isinstance(t.fm.get("tags"), list) else []
    texte = f" {_norme(' '.join([t.titre, *map(str, tags)]))} "
    for ex in exemptions:
        if e := _norme(ex):
            texte = re.sub(rf"(?<![a-z0-9]){re.escape(e)}(?![a-z0-9])", " ", texte)
    for mot in mots:
        ouvert = str(mot).strip().endswith("*")
        if m := _norme(str(mot).strip().rstrip("*")):
            fin = "" if ouvert else "(?![a-z0-9])"
            if re.search(rf"(?<![a-z0-9]){re.escape(m)}{fin}", texte):
                return mot
    return ""


def relecteur(config, harnais: str, modele: str) -> Choix | None:
    """Moteur de la revue, indépendant de l'auteur : `[validation] revue_harnais` s'il diffère de
    l'auteur, sinon un autre harnais (ordre des crédits), sinon le même harnais avec un autre modèle."""
    v = config.validation
    if v.revue_harnais:
        ok = (v.revue_harnais, v.revue_modele) != (harnais, modele) and (
            v.revue_harnais != harnais or v.revue_modele)
        return Choix(v.revue_harnais, v.revue_modele) if ok else None
    ordre = list(dict.fromkeys([*config.credits.get("opus", []), *config.harnais]))
    autres = [(h, config.harnais.get(h, {}).get("familles", {}).get("opus", ""))
              for h in ordre if h in config.harnais and h != harnais]
    if autres:
        return Choix(*autres[0], tuple(autres[1:]))
    familles = config.harnais.get(harnais, {}).get("familles", {})
    for f in ("opus", "sonnet", "rapide"):
        if (m := familles.get(f)) and m != modele:
            return Choix(harnais, m)
    return None


class Journal:
    """Compteur d'échantillonnage et journal des issues (relu à chaque lecture : petit fichier)."""

    def __init__(self, fichier: Path):
        self.fichier = fichier

    def _lire(self) -> dict:
        try:
            brut = json.loads(self.fichier.read_text("utf-8"))
        except (OSError, ValueError):
            return {"compteur": 0, "entrees": [], "reevaluation": {}}
        if not isinstance(brut, dict):
            return {"compteur": 0, "entrees": [], "reevaluation": {}}
        entrees = brut.get("entrees") if isinstance(brut.get("entrees"), list) else []
        return {"compteur": _entier(brut.get("compteur"), 1) if brut.get("compteur") else 0,
                "entrees": [e for e in entrees if isinstance(e, dict)],
                "reevaluation": brut.get("reevaluation") if isinstance(brut.get("reevaluation"), dict) else {}}

    def _ecrire(self, etat: dict) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier, json.dumps(etat, ensure_ascii=False, indent=1))
        except OSError as e:
            log.warning("journal de validation automatique non persisté : %s", e)

    def entrees(self) -> list[dict]:
        return self._lire()["entrees"]

    def reevaluations(self) -> dict:
        return self._lire()["reevaluation"]

    def noter_reevaluation(self, notes: dict) -> None:
        """Remplace le relevé de réévaluation (un motif par tâche) ; clôtures et compteur intacts."""
        etat = self._lire()
        etat["reevaluation"] = notes
        self._ecrire(etat)

    def compter(self) -> int:
        """Incrémente le compteur d'échantillonnage (clôtures admissibles) et le rend."""
        etat = self._lire()
        etat["compteur"] += 1
        self._ecrire(etat)
        return etat["compteur"]

    def ajouter(self, entree: dict) -> None:
        etat = self._lire()
        etat["entrees"] = [entree, *etat["entrees"]][:500]
        self._ecrire(etat)

    def rouvrir(self, ident: str) -> bool:
        etat = self._lire()
        for e in etat["entrees"]:
            if e.get("tache") == ident and e.get("issue") == "cloture" and not e.get("rouvert"):
                e["rouvert"] = maintenant()
                self._ecrire(etat)
                return True
        return False


class ValidationAuto:
    def __init__(self, moteur):
        self.m = moteur
        self.journal = Journal(moteur.config.donnees / "etat" / "validation_auto.json")

    def applique(self, ident: str) -> bool:
        try:
            return reglage(self.m.vault, ident)["mode"] == "automatique"
        except NonTrouve:
            return False

    # --- décision ----------------------------------------------------------------------
    def _prealables(self, t, r: dict) -> str:
        """Motif de refus des conditions sans IA (exclusion, fiche R1, contrôle a) ; « » si remplies."""
        if mot := exclusion(t, r["exclusions"], r["exemptions"]):
            return langues.t("serveur.validation_auto.exclusion", mot=mot)
        if not (str(t.fiche.get("resultat") or "").strip() and str(t.fiche.get("essai") or "").strip()):
            return langues.t("serveur.validation_auto.sans_resultat")
        if motif := demontrable(t):
            return langues.t("serveur.validation_auto.demontrable", motif=motif)
        vue = self.m.controle_vue(t.id)
        if vue is None:
            return langues.t("serveur.validation_auto.sans_controle")
        v = vue["verdict"]
        if not v or v.get("verdict") != "reussi":
            return (langues.t("serveur.validation_auto.controle_cause", cause=v["cause"]) if v and v.get("cause")
                    else langues.t("serveur.validation_auto.controle_non_reussi"))
        if v.get("perime") is not False:
            return langues.t("serveur.validation_auto.perime")
        return ""

    async def evaluer(self, ident: str, echec_revue: bool = False) -> str:
        """INV-VALID-2 : clôt la tâche si (a), (b), (c) tiennent et que l'échantillon ne la retient
        pas ; sinon la laisse « à valider » avec le motif journalisé. Rend l'issue."""
        t = self.m.vault.tache(ident)
        r = reglage(self.m.vault, ident)
        auteur = {"harnais": str(t.fm.get("harnais") or self.m.config.moteur.harnais_defaut),
                  "modele": str(t.fm.get("modele") or "")}
        base = {"tache": ident, "titre": t.titre, "conteneur": t.conteneur, "auteur": auteur,
                "declare_par": r["declare_par"], "accord": r["accord"]}
        motif = langues.t("serveur.validation_auto.echec_revue") if echec_revue else self._prealables(t, r)
        if motif:
            return self._refus(base, motif)
        v = self.m.controle_vue(ident)["verdict"]
        base["controle"] = {"reference": v["reference"], "date": v["date"], "commande": v["commande"]}
        choix = relecteur(self.m.config, auteur["harnais"], auteur["modele"])
        if choix is None:
            return self._refus(base, langues.t("serveur.validation_auto.sans_relecteur"))
        question = (f"État vérifié par le contrôle : {v['reference']} dans {v['dossier']}.\n"
                    f"Résultat annoncé : {t.fiche.get('resultat')}\nEssai annoncé : {t.fiche.get('essai')}")
        avis = await self.m.revues._tour(ident, {**REVUE, "nom": langues.t("serveur.validation_auto.nom_revue")},
                                         "validation", question, choix=choix)
        p1 = [p for p in avis["points"] if re.match(r"\[?\s*P1\b", p)]
        base["revue"] = {"harnais": avis.get("moteur", ""), "modele": avis.get("modele", ""),
                         "verdict": avis["verdict"], "points": avis["points"][:20]}
        if (avis.get("moteur"), avis.get("modele")) == (auteur["harnais"], auteur["modele"]):
            return self._refus(base, langues.t("serveur.validation_auto.meme_moteur"))
        if avis["verdict"] != "ok" or p1:
            return self._refus({**base, "revue_refusee": True},
                               langues.t("serveur.validation_auto.revue_p1", n=len(p1)) if p1
                               else langues.t("serveur.validation_auto.revue_verdict", verdict=avis["verdict"]))
        try:
            t = self.m.vault.tache(ident)
        except NonTrouve:
            return "disparue"
        if t.verrouille or executant.humain(t) or t.statut != "fait" or self.m.ferme:  # INV-EXECUTANT-1
            return self._refus(base, langues.t("serveur.validation_auto.a_bouge"))  # INV-VALID-1
        if self.journal.compter() % r["echantillon"] == 0:
            return self._refus(base, langues.t("serveur.validation_auto.echantillon", n=r["echantillon"]),
                               issue="echantillon")
        self.m.vault.poser_statut(ident, "cloture")  # INV-EXEC-5 : accord borné au périmètre
        self.m.revues._remettre_a_zero(ident)
        self.journal.ajouter({**base, "issue": "cloture", "date": maintenant()})
        self.m.publier("arbre")
        return "cloture"

    def reevaluer(self) -> dict:
        """Rejoue les préalables sans IA (exclusion, R1, démontrable, contrôle) sur les tâches `fait`
        des périmètres automatiques ; ne clôt rien, ne lance ni revue ni contrôle (INV-VALID-2).
        Écrit un motif par tâche dans `reevaluation` du journal ; rend ce relevé."""
        notes = {}
        for ident, t in self.m.vault.index()[0].items():
            if t.statut != "fait" or not self.applique(ident):
                continue
            motif = self._prealables(t, reglage(self.m.vault, ident))
            notes[ident] = {"titre": t.titre, "conteneur": t.conteneur, "date": maintenant(),
                            "issue": "refus" if motif else "admissible",
                            "motif": motif or langues.t("serveur.validation_auto.prealables_ok")}
        self.journal.noter_reevaluation(notes)
        return notes

    def _refus(self, base: dict, motif: str, issue: str = "refus") -> str:
        self.journal.ajouter({**base, "issue": issue, "motif": motif, "date": maintenant()})
        self.m.publier("arbre")
        return issue

    # --- lecture et gestes ---------------------------------------------------------------
    def motif(self, ident: str) -> dict | None:
        """Dernière issue non close de la tâche (refus ou échantillon), pour la page Décisions."""
        for e in self.journal.entrees():
            if e.get("tache") == ident:
                return e if e["issue"] in ("refus", "echantillon") else None
        return None

    def clos_recents(self, jours: int = JOURS_VISIBLES) -> list[dict]:
        limite = (dt.datetime.now() - dt.timedelta(days=jours)).isoformat(timespec="seconds")
        return [e for e in self.journal.entrees()
                if e.get("issue") == "cloture" and not e.get("rouvert") and str(e.get("date")) >= limite]

    def rouvrir(self, ident: str) -> None:
        """Geste humain : la tâche close automatiquement revient « à valider »."""
        t = self.m.vault.tache(ident)
        if t.statut != "cloture":
            raise Conflit(langues.t("serveur.validation_auto.non_cloturee"))
        if not self.journal.rouvrir(ident):
            raise Conflit(langues.t("serveur.validation_auto.sans_cloture"))
        self.m.vault.poser_statut(ident, "fait", humain=True)
        self.m.publier("arbre")

    def regler(self, conteneur: str, mode: str) -> dict:
        """Geste humain depuis l'interface : pose le mode et sa trace dans le `contexte.md`."""
        if mode not in MODES:
            raise Invalide(langues.t("serveur.validation_auto.mode_inconnu", mode=mode))
        if conteneur not in self.m.vault.index()[1]:
            raise NonTrouve(langues.t("serveur.validation_auto.projet_inconnu", conteneur=conteneur))
        chemin = self.m.vault.racine / conteneur / self.m.vault.cfg.contexte
        if not chemin.is_file():
            raise NonTrouve(langues.t("serveur.validation_auto.contexte_absent", conteneur=conteneur))
        accord = f"posé depuis l'interface le {dt.date.today().isoformat()}"
        # INV-VAULT-1 : seules ces deux clés changent, le reste du frontmatter est intact.
        texte = fiches.modifier_cles(fiches.lire(chemin), {"validation": mode, "validation_accord": accord})
        fiches.ecrire_atomique(chemin, texte)
        self.m.vault._index = None
        self.m.publier("arbre")
        return {"conteneur": conteneur, "mode": mode, "accord": accord}
