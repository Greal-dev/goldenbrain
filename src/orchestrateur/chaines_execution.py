"""Exécution des chaînes : une tâche parente par dossier traité, une tâche enfant par phase, en série.

Rôle : lancer un modèle de chaîne sur un dossier (geste manuel ou dépôt dans un dossier surveillé), soumettre
une phase à la fois avec les résultats des précédentes, enchaîner la suivante quand un tour se conclut
« terminée », s'arrêter pour une validation humaine si la phase la demande, reprendre une phase en échec,
appliquer et journaliser les ajustements que l'IA décide pour le dossier réel (sauter, ajouter, dédoubler une
phase, réécrire une consigne). État des exécutions : `etat/chaines.json`.
Frontières : n'exécute rien lui-même — tout passe par `moteur.creer` / `moteur.soumettre` (file, poste,
prérequis) ; lit la fin des tours sur le flux d'événements du moteur (`tour_fin`), sans toucher au moteur ;
n'écrit dans le vault que par `Vault` (clés gérées, statuts).
Invariants portés : INV-CHAINE-1, INV-CHAINE-3, INV-CHAINE-4.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import logging
import time
from pathlib import Path

from . import chaines, fiches, langues
from .vault import Conflit, ErreurOrch, Invalide, NonTrouve

log = logging.getLogger(__name__)
A_VENIR, EN_COURS, FAITE, SAUTEE, ECHEC = "a_venir", "en_cours", "faite", "sautee", "echec"
ATTENTE, TERMINEE = "attente_validation", "terminee"
ACTIONS = ("sauter", "ajouter", "dedoubler", "consigne")
OCCUPEE = ("en_cours", "en_file", "en_pause")
SURVEILLANCE_S = 60
MAX_LANCEMENTS = 5  # par passage de la surveillance : un dépôt massif ne lance pas cent chaînes d'un coup
BORNE_RESULTAT = 1500


class Chaines:
    def __init__(self, moteur):
        self.moteur = moteur
        self.vault = moteur.vault
        self.chemin = moteur.config.donnees / "etat" / "chaines.json"
        self.etat = self._lire()

    # --- état persistant ---------------------------------------------------------------
    def _lire(self) -> dict:
        try:
            etat = json.loads(self.chemin.read_text("utf-8"))
        except (OSError, ValueError):
            etat = {}
        if not isinstance(etat, dict):
            etat = {}
        etat.setdefault("executions", {})
        etat.setdefault("vus", {})
        return etat

    def _sauver(self) -> None:
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.chemin, json.dumps(self.etat, ensure_ascii=False))
        except OSError as e:
            log.warning("état des chaînes non persisté : %s", e)

    def _exec(self, parent: str) -> dict:
        if (e := self.etat["executions"].get(parent)) is None:
            raise NonTrouve(langues.t("serveur.chaines.execution_inconnue", id=parent))
        return e

    def de_tache(self, ident: str) -> str | None:
        """Exécution (identifiant de la tâche parente) dont `ident` est la parente ou une phase."""
        if ident in self.etat["executions"]:
            return ident
        return next((p for p, e in self.etat["executions"].items()
                     if any(ph["tache"] == ident for ph in e["phases"])), None)

    # --- lancement ---------------------------------------------------------------------
    def _creer_phase(self, parent: str, p: dict, num: str) -> str:
        harnais = p.get("harnais") or None
        if harnais and harnais not in self.moteur.registre:
            harnais = None  # assistant absent de ce poste : celui par défaut, plutôt qu'une chaîne refusée
        try:
            ident = self.moteur.creer(f"{num}. {p['titre']}", p["consigne"], parent=parent, harnais=harnais,
                                      modele=p.get("modele") or None)
        except Invalide:  # modèle d'IA inconnu de ce poste : celui par défaut
            ident = self.moteur.creer(f"{num}. {p['titre']}", p["consigne"], parent=parent, harnais=harnais)
        self.vault.modifier(ident, {"chaine_phase": num})
        return ident

    def lancer(self, modele: str, conteneur: str | None = None, dossier: str = "", titre: str = "",
               origine: str = "manuelle") -> str:
        """Crée la tâche parente et une tâche par phase, puis soumet la première (INV-CHAINE-1)."""
        m = chaines.modele(self.vault.racine, modele)
        dossier = (dossier or "").strip()[:500]
        nom = (titre or "").strip() or (Path(dossier).name if dossier else "") or dt.date.today().isoformat()
        plan = "\n".join(f"{i}. {p['titre']}" for i, p in enumerate(m["phases"], 1))
        description = (f"{langues.t('serveur.chaines.parent_intro', modele=m['titre'])}\n\n"
                       + (f"{langues.t('serveur.chaines.parent_dossier', dossier=dossier)}\n\n" if dossier else "")
                       + plan)
        parent = self.moteur.creer(f"{m['titre']} — {nom}", description, conteneur or m["conteneur"] or None)
        # INV-CHAINE-1 : chaque phase travaille dans sa propre conversation — regroupées sur la parente (manque de
        # RAM, INV-REGROUPE-1), leurs tours se concluraient sur la parente et la chaîne ne verrait jamais leur fin.
        self.vault.modifier(parent, {"chaine": m["id"], "statut": "en-cours", "execution": "par_tache"})
        phases = []
        for i, p in enumerate(m["phases"], 1):
            phases.append({**p, "num": str(i), "etat": A_VENIR, "tache": self._creer_phase(parent, p, str(i))})
        self.etat["executions"][parent] = {
            "modele": m["id"], "titre": m["titre"], "contexte": m["contexte"], "dossier": dossier,
            "origine": origine, "lancee": dt.datetime.now().isoformat(timespec="minutes"),
            "etat": EN_COURS, "courante": -1, "phases": phases, "ajustements": []}
        self._suivante(parent)
        return parent

    # --- enchaînement ------------------------------------------------------------------
    def _chemin_dossier(self, dossier: str) -> str:
        """Chemin complet d'un dossier du vault, sinon le texte tel qu'il a été donné."""
        if dossier and not Path(dossier).is_absolute():
            p = (self.vault.racine / dossier).resolve()
            if p.is_relative_to(self.vault.racine) and p.exists():
                return str(p)
        return dossier

    def _resultats(self, e: dict, k: int) -> list[str]:
        lignes = []
        for ph in e["phases"][:k]:
            if ph["etat"] != FAITE:
                continue
            try:
                f = self.vault.detail(ph["tache"])["fiche"]
            except ErreurOrch:
                continue
            texte = " ".join(f"{c} : {f[c]}" for c in ("fait", "resultat", "situation") if f.get(c))
            lignes.append(f"- {ph['num']}. {ph['titre']} ({ph['tache']}) — {texte[:BORNE_RESULTAT] or '—'}")
        return lignes

    def mission(self, parent: str, k: int) -> str:
        """Consigne complète de la phase k : contexte, dossier, phase, résultats des précédentes, plan,
        et la manière d'ajuster la chaîne (INV-CHAINE-3)."""
        e = self.etat["executions"][parent]
        ph = e["phases"][k]
        reste = [f"{p['num']}. {p['titre']}" for p in e["phases"][k + 1:] if p["etat"] == A_VENIR]
        resultats = self._resultats(e, k)
        blocs = [f"[Chaîne « {e['titre']} » — phase {ph['num']} : {ph['titre']}. Tâche parente : {parent}.]"]
        if e["dossier"]:
            blocs.append(f"Dossier traité : {self._chemin_dossier(e['dossier'])}")
        if e["contexte"]:
            blocs.append(f"Contexte commun de la chaîne :\n{e['contexte']}")
        blocs.append(f"Consigne de cette phase :\n{ph['consigne']}")
        if ph.get("entrees"):
            blocs.append(f"Documents d'entrée : {ph['entrees']}")
        if ph.get("livrable"):
            blocs.append(f"Livrable attendu : {ph['livrable']} — enregistre-le à côté du dossier traité (ou dans "
                         f"le dossier du projet) et cite son chemin complet dans `resultat`.")
        blocs.append("Résultats des phases précédentes (leurs fiches se lisent par `orch lire <id>`) :\n"
                     + ("\n".join(resultats) if resultats else "- aucun : tu ouvres la chaîne."))
        blocs.append("Phases suivantes : " + ("; ".join(reste) if reste else "aucune, tu clos la chaîne."))
        blocs.append(
            "Adapter la chaîne au dossier réel : si ce dossier le justifie, ajuste les phases à venir, toujours avec "
            "un motif (l'utilisateur voit chaque ajustement) : `orch chaine sauter <n> --motif \"…\"`, "
            "`orch chaine ajouter \"<titre>\" \"<consigne>\" [--apres <n>] --motif \"…\"`, "
            "`orch chaine dedoubler <n> --motif \"…\"`, `orch chaine consigne <n> \"<consigne>\" --motif \"…\"` ; "
            "`orch chaine` montre le plan. Sinon, ne change rien.")
        blocs.append("Termine par `statut: terminee` quand le livrable de cette phase est prêt : la phase suivante "
                     "part d'office ; `en_attente` si une décision de l'utilisateur manque.")
        return "\n\n".join(blocs) + "\n\n" + langues.consigne_langue()

    def _soumettre(self, parent: str, k: int, prefixe: str = "") -> None:
        e = self.etat["executions"][parent]
        ph = e["phases"][k]
        e["courante"], ph["etat"], e["etat"] = k, EN_COURS, EN_COURS
        self._sauver()
        with contextlib.suppress(ErreurOrch):
            self.vault.poser_statut(ph["tache"], "en-cours")
        try:
            self.moteur.soumettre(ph["tache"], prefixe + self.mission(parent, k))
        except Exception as err:  # assistant « Moi », tâche disparue, disque… : la phase reste à reprendre
            ph["etat"], e["etat"], e["erreur"] = ECHEC, ECHEC, str(err)
            self._sauver()
        self.moteur.publier("arbre")

    def _suivante(self, parent: str) -> None:
        """INV-CHAINE-1 : la phase à venir suivante, ou la clôture de la chaîne."""
        e = self.etat["executions"][parent]
        k = next((i for i, p in enumerate(e["phases"]) if i > e["courante"] and p["etat"] == A_VENIR), None)
        if k is not None:
            self._soumettre(parent, k)
            return
        e["etat"] = TERMINEE
        self._sauver()
        with contextlib.suppress(ErreurOrch):
            self.vault.poser_statut(parent, "fait")
        self.moteur.publier("arbre")

    def apres_tour(self, ident: str, statut: str) -> None:
        """Fin d'un tour : la phase courante « terminée » enchaîne (ou attend la validation), « bloquée »
        met la chaîne en échec ; tout autre statut (en attente de l'utilisateur, en cours) ne change rien."""
        parent = self.de_tache(ident)
        if parent is None or parent == ident:
            return
        e = self.etat["executions"][parent]
        k = e["courante"]
        if k < 0 or e["phases"][k]["tache"] != ident or e["etat"] == TERMINEE:
            return  # INV-CHAINE-1 : seul le tour de la phase courante fait avancer la chaîne
        ph = e["phases"][k]
        if statut == "fait":
            ph["etat"] = FAITE
            e.pop("erreur", None)
            if ph.get("validation") and any(p["etat"] == A_VENIR for p in e["phases"][k + 1:]):
                e["etat"] = ATTENTE
                self._sauver()
                with contextlib.suppress(ErreurOrch):
                    self.vault.poser_statut(parent, self.vault.retour)  # visible dans « À moi »
                self.moteur.publier("arbre")
                return
            self._suivante(parent)
        elif statut == "bloque":
            ph["etat"], e["etat"] = ECHEC, ECHEC
            self._sauver()
            self.moteur.publier("arbre")

    # --- gestes de l'utilisateur ------------------------------------------------------
    def poursuivre(self, parent: str) -> dict:
        """Validation humaine accordée : la phase suivante part."""
        e = self._exec(parent)
        if e["etat"] != ATTENTE:
            raise Conflit(langues.t("serveur.chaines.pas_en_attente"))
        with contextlib.suppress(ErreurOrch):
            self.vault.poser_statut(parent, "en-cours")
        self._suivante(parent)
        return self.public(parent)

    def reprendre(self, parent: str) -> dict:
        """Reprise après échec — ou d'une phase arrêtée dont la fin n'a pas été vue — avec la même consigne."""
        e = self._exec(parent)
        k = e["courante"]
        if e["etat"] not in (ECHEC, EN_COURS) or k < 0:
            raise Conflit(langues.t("serveur.chaines.pas_en_echec"))
        if self.moteur.etat_de(e["phases"][k]["tache"]) in OCCUPEE:
            raise Conflit(langues.t("serveur.chaines.phase_occupee"))
        e.pop("erreur", None)
        self._soumettre(parent, k, "[Reprise après l'échec du tour précédent de cette phase.]\n\n")
        return self.public(parent)

    def ajuster(self, source: str, action: str, n: str = "", titre: str = "", consigne: str = "",
                motif: str = "") -> dict:
        """INV-CHAINE-3 : ajustement décidé par l'IA (ou l'utilisateur) sur une phase à venir, toujours
        motivé, journalisé et visible ; jamais sur une phase passée ou en cours."""
        parent = self.de_tache(source)
        if parent is None:
            raise NonTrouve(langues.t("serveur.chaines.hors_chaine", id=source))
        e = self.etat["executions"][parent]
        if action not in ACTIONS:
            raise Invalide(langues.t("serveur.chaines.action_inconnue", actions=", ".join(ACTIONS)))
        if not motif.strip():
            raise Invalide(langues.t("serveur.chaines.motif_requis"))
        if e["etat"] == TERMINEE:
            raise Conflit(langues.t("serveur.chaines.terminee"))
        nums = [p["num"] for p in e["phases"]]
        n = (n or "").strip() or (nums[e["courante"]] if e["courante"] >= 0 else "")
        if n not in nums:
            raise Invalide(langues.t("serveur.chaines.phase_inconnue", n=n, phases=", ".join(nums)))
        k = nums.index(n)
        if action != "ajouter" and (k <= e["courante"] or e["phases"][k]["etat"] != A_VENIR):
            raise Conflit(langues.t("serveur.chaines.phase_passee", n=n))
        if action == "ajouter" and k < e["courante"]:
            raise Conflit(langues.t("serveur.chaines.phase_passee", n=n))
        ph = e["phases"][k]
        if action == "sauter":
            ph["etat"] = SAUTEE
            with contextlib.suppress(ErreurOrch):
                self.vault.poser_statut(ph["tache"], "abandonne")
        elif action == "consigne":
            if not consigne.strip():
                raise Invalide(langues.t("serveur.chaines.consigne_requise"))
            ph["consigne"] = consigne.strip()[:8000]
        else:
            nouvelle = chaines.phase_valide({
                **({k2: ph[k2] for k2 in chaines.CHAMPS_PHASE} if action == "dedoubler" else {}),
                "titre": titre.strip() or (f"{ph['titre']} (2)" if action == "dedoubler" else ""),
                "consigne": consigne.strip() or (ph["consigne"] if action == "dedoubler" else ""),
                "validation": False})
            suffixes = {p["num"] for p in e["phases"]}
            i = 1
            while f"{n}.{i}" in suffixes:
                i += 1
            num = f"{n}.{i}"
            e["phases"].insert(k + 1, {**nouvelle, "num": num, "etat": A_VENIR,
                                       "tache": self._creer_phase(parent, nouvelle, num)})
        e["ajustements"].append({"a": dt.datetime.now().isoformat(timespec="minutes"), "de": source,
                                 "action": action, "phase": n, "titre": titre.strip()[:120],
                                 "motif": motif.strip()[:500]})
        self._sauver()
        self.moteur.publier("arbre")
        return self.public(parent)

    # --- lecture -----------------------------------------------------------------------
    def public(self, parent: str) -> dict:
        e = self._exec(parent)
        taches = self.vault.index()[0]
        phases = [{**{k: p.get(k, "") for k in ("num", "titre", "tache", "etat", "livrable", "harnais", "modele")},
                   "validation": bool(p.get("validation")),
                   "statut": taches[p["tache"]].statut if p["tache"] in taches else "",
                   "execution": self.moteur.etat_de(p["tache"]) if p["tache"] in taches else ""}
                  for p in e["phases"]]
        return {"id": parent, "modele": e["modele"], "titre": e["titre"], "dossier": e["dossier"],
                "origine": e["origine"], "lancee": e["lancee"], "etat": e["etat"], "erreur": e.get("erreur", ""),
                "courante": e["courante"], "phases": phases, "ajustements": e["ajustements"]}

    def plan(self, source: str) -> dict:
        if (parent := self.de_tache(source)) is None:
            raise NonTrouve(langues.t("serveur.chaines.hors_chaine", id=source))
        return self.public(parent)

    def liste(self) -> list[dict]:
        return [self.public(p) for p in list(self.etat["executions"]) if p in self.vault.index()[0]]

    # --- surveillance d'un dossier ----------------------------------------------------
    def surveiller(self) -> list[str]:
        """INV-CHAINE-4 : un dossier nouveau dans le dossier surveillé lance la chaîne, une seule fois ;
        les dossiers présents quand la surveillance commence ne sont jamais rattrapés."""
        lancees: list[str] = []
        racine = self.vault.racine
        for m in chaines.lister(racine):
            if not m["surveiller"]:
                continue
            d = (racine / m["surveiller"]).resolve()
            if not d.is_relative_to(racine) or not d.is_dir():
                continue
            noms = sorted(x.name for x in d.iterdir() if x.is_dir() and not x.name.startswith("."))
            cle = f"{m['id']}|{m['surveiller']}"  # dossier surveillé changé : nouveau départ, sans rattrapage
            vus = self.etat["vus"].get(cle)
            if vus is None:
                self.etat["vus"][cle] = noms
                self._sauver()
                continue
            for nom in [x for x in noms if x not in vus][:MAX_LANCEMENTS - len(lancees)]:
                vus.append(nom)  # compté avant le lancement : un échec ne relance pas en boucle
                self._sauver()
                try:
                    lancees.append(self.lancer(m["id"], m["conteneur"] or None, f"{m['surveiller']}/{nom}", nom,
                                               origine="surveillance"))
                except ErreurOrch as err:
                    log.warning("chaîne %s non lancée sur %s : %s", m["id"], nom, err)
        return lancees

    def reconcilier(self) -> None:
        """INV-CHAINE-1 : une phase conclue sans fin de tour vue (serveur arrêté, statut posé à la main)
        fait avancer la chaîne comme si son tour venait de finir."""
        taches = self.vault.index()[0]
        for parent, e in list(self.etat["executions"].items()):
            k = e["courante"]
            if e["etat"] != EN_COURS or k < 0 or (t := taches.get(e["phases"][k]["tache"])) is None:
                continue
            if self.moteur.etat_de(t.id) not in OCCUPEE and t.statut in ("fait", "bloque", "abandonne"):
                self.apres_tour(t.id, "fait" if t.statut == "fait" else "bloque")

    async def boucle(self) -> None:
        """Lit la fin des tours sur le flux du moteur ; passe la surveillance chaque minute."""
        q = self.moteur.abonner()
        dernier = 0.0
        try:
            while True:
                with contextlib.suppress(TimeoutError):
                    ev = await asyncio.wait_for(q.get(), timeout=SURVEILLANCE_S)
                    if ev.get("type") == "tour_fin" and ev.get("tache"):
                        try:
                            self.apres_tour(ev["tache"], str(ev.get("statut") or ""))
                        except Exception:  # une chaîne en erreur n'arrête pas la boucle
                            log.exception("chaîne : fin de tour de %s", ev.get("tache"))
                if time.monotonic() - dernier >= SURVEILLANCE_S:
                    dernier = time.monotonic()
                    try:
                        self.reconcilier()
                        self.surveiller()  # sur la boucle : `soumettre` y crée ses tâches
                    except Exception:
                        log.exception("chaîne : surveillance")
        finally:
            self.moteur.desabonner(q)
