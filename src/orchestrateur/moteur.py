"""Moteur d'exécution : files par tâche, tours, journal, fiche, messages, propositions.

Rôle : seul endroit où un harnais est lancé ; traduit ses événements en écritures vault
(via `vault`) et en événements publiés aux abonnés (SSE).
Frontières : pas de HTTP ; aucune écriture vault hors des méthodes de `Vault`.
Invariants portés : INV-EXEC-1 (interruption marquée, reprise unique via `reprise`), INV-EXEC-2 (un tour à la fois par tâche, file ordonnée), INV-EXEC-3 (session écrite au premier
événement), INV-EXEC-4 (journal brut par tour), INV-EXEC-5 révisé (propositions exécutées sur geste humain seulement ; `fait` écrit sur déclaration de l'agent, jamais `cloture` ni
`abandonne`), INV-MSG-1 (plafond de sauts), INV-MSG-2 (pas d'accusé de retour vers la source), INV-EXEC-6 (aucune mort silencieuse), INV-EXEC-7 (tâche permanente jamais terminée), INV-
TRANSFO-1 (un mandat n'est traité qu'à la fin d'un tour réussi ; interrompu, il reste en attente), INV-VERROU-1 (mise en file publiée et datée), INV-CONTROLE-1, INV-ECO-1, INV-COMPACT-1
(seuil posé, tour mesuré), INV-RETOUR-1, INV-RETOUR-3 (point et reprise avant le tour), INV-REGROUPE-2 (message d'une sous-tâche regroupée acheminé vers sa mère), INV-RESEAU-1, INV-EXECUTANT-1, INV-EXECUTANT-2.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
import sys
from contextlib import aclosing
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import (apprendre, assistant_absent, attente_muette, etat_main, instrumentation, agents_cc, langues, catalogue, codespace, decisions, depot, echecs, economie, executant, executeurs, fiches, incidents, liens, natif, ordonnancement, pilotage,
               quota, regroupement, reprise, reprise_auto, reseau, retour, session_perdue, sessions, simultanes, temps, transformations)
from .propagation import MixinPropagation
from .config import RACINE_DEPOT, Config
from .harnais import HARNAIS, Harnais
from .propositions import TYPES_PROPOSITION, MixinPropositions, Propositions, lire_liste, maintenant  # noqa: F401
from .revues import Revues
from .validation_auto import ValidationAuto
from .controle import NATURES_SANS_FIN, MixinControle  # INV-EXEC-7 : natures sans fin
from .compactage import MixinCompactage
from .reveil import MixinReveil
from .relance_fiche import MOTIF as MOTIF_FICHE, RelanceFiche, redemander
from .verrou import MixinVerrou
from .roles import Roles
from .vault import Conflit, ErreurOrch, Invalide, NonTrouve, Vault

log = logging.getLogger(__name__)
STATUT_DECLARE = ("en_cours", "en_attente", "terminee")  # `statut:` de <fiche> ; statut vault : Vault.statut_declare

def session_valide(session: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session or ""):
        raise Invalide(langues.t("serveur.moteur.session_invalide"))
    return session


class _Gabarit(dict):
    def __missing__(self, cle: str) -> str:
        return "{" + cle + "}"


@dataclass
class Envoi:
    texte: str
    sauts: int = 0
    de: str = ""
    harnais: str | None = None   # surcharge appliquée avant le tour (None = inchangé)
    modele: str | None = None
    source: str = ""  # tâche dont la propagation a déclenché ce tour (INV-MSG-2)
    mandat: bool = False  # message d'un mandat de transformation (INV-TRANSFO-1)
    role: str = ""  # rôle assistant du tour (INV-MOTEUR-2) ; "tache" = travail principal
    reprise: bool = False  # INV-EXEC-1 : repris automatiquement (la marque tombe au premier signe de progrès)
    progres: bool = False  # INV-EXEC-1 : le tour repris a produit un événement
    reprises: int = 0  # INV-REPRISE-1 : reprises d'office déjà faites de ce tour (plafond 3)
    pour: str = ""  # sous-tâche portée par ce tour de sa mère (INV-REGROUPE-2)
    t_file: float = field(default_factory=lambda: instrumentation.horloge())  # mesure d'attente (instrumentation.py)


@dataclass
class Tour:
    tache: str
    depuis: str
    harnais: Harnais
    dernier: str = ""
    arrete: bool = False
    arret: str = ""  # cause de l'arrêt : "humain", "ram", "serveur" (INV-REPRISE-1)
    persona: str = ""  # tour de revue d'un persona (INV-EQUIPE-1), vide pour un tour de tâche


class Moteur(retour.MixinRetour, MixinVerrou, MixinControle, MixinCompactage, MixinPropositions, ordonnancement.MixinOrdonnancement,
             MixinPropagation, regroupement.MixinRegroupement, MixinReveil):  # INV-REGROUPE-3 : etat_de ; INV-EXEC-10
    def __init__(self, config: Config, vault: Vault | None = None, registre: dict | None = None):
        self.config = config
        self.vault = vault or Vault(config.vault)
        self.registre = registre if registre is not None else HARNAIS
        self.files: dict[str, deque[Envoi]] = defaultdict(deque)
        self.etats: dict[str, str] = {}; self.tours: dict[str, Tour] = {}; self.boucles: dict[str, asyncio.Task] = {}
        self.a_deriver: dict[str, str] = {}; self.relance_fiche, self.attente_muette = RelanceFiche(), attente_muette.AttenteMuette(self)  # INV-EXEC-12, INV-MAIN-2
        self.envois: dict[str, Envoi] = {}  # message du tour en cours (conversation en direct)
        self.en_file_depuis: dict[str, str] = {}; self.abonnes: set[asyncio.Queue] = set()  # INV-VERROU-1 : « depuis » avant tout tour
        self._sem = simultanes.Creneaux(self)  # INV-SIMULT-1 : nombre fixe, optimisation ou plafond de RAM
        self.propositions = Propositions(config.donnees / "etat" / "propositions.json"); self.sessions = sessions.Sessions(config.donnees / "etat" / "sessions.json")
        # INV-EXEC-1 : un tour actif au dernier arrêt est marqué interrompu ; son message est gardé pour la reprise.
        self.fichier_tours = config.donnees / "etat" / "tours.json"
        self.actifs: dict[str, dict] = {}; self.ferme = False
        self.attente: dict[str, Envoi] = {}  # INV-EXEC-9 : sorti de la file, pas encore démarré
        self.file_precedente = reprise.lire_file(config.donnees / "etat" / reprise.FICHIER_FILE)
        self.interrompus = reprise.charger(lire_liste(self.fichier_tours))
        self.etats.update(dict.fromkeys(self.interrompus, "interrompu"))
        self._sauver_actifs()
        self._init_reveils()  # INV-EXEC-10
        self.revues, self.validation_auto = Revues(self), ValidationAuto(self)
        self.agents_cc = agents_cc.Releve(self)  # INV-AGENTSCC-1
        self.roles = Roles(config, self.registre); self.mandats = transformations.Mandats(config.donnees / "etat" / "mandats.json")
        self._init_verrou()
        self.natif = natif.Natifs(self)  # INV-NATIF-1 : tâches ouvertes au terminal
        self.economie = economie.Economie(self)  # INV-ECO-1 : moteur du travail principal
        self.reseau = reseau.Reseau(self)  # INV-RESEAU-1
        self.executeurs = executeurs.Executeurs(self)  # INV-DISTANT-2
        self.quota, self.incidents, self.reprise_auto = quota.Quotas(self), incidents.Incidents(self), reprise_auto.RepriseAuto(self)  # INV-QUOTA-1, INV-INCIDENT-1

    def _sauver_actifs(self) -> None:
        if self.ferme:
            return  # INV-EXEC-1 : à l'arrêt, la liste reste sur disque pour le redémarrage.
        try:
            self.fichier_tours.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier_tours, json.dumps(list(self.actifs.values()), ensure_ascii=False))
            reprise.sauver_file(self)  # INV-EXEC-9
        except OSError as e:
            log.warning("tours actifs non persistés : %s", e)

    async def fermer(self) -> None:
        """Arrêt du serveur : tue tous les tours actifs, garde leur liste pour le redémarrage."""
        self.ferme = True
        self.fermer_reveils()
        for tour in list(self.tours.values()):
            tour.arrete, tour.arret = True, "serveur"
            await asyncio.shield(tour.harnais.arreter())

    # --- événements --------------------------------------------------------------------
    def abonner(self) -> asyncio.Queue:
        self.abonnes.add(q := asyncio.Queue(maxsize=1000))
        return q

    def desabonner(self, q: asyncio.Queue) -> None:
        self.abonnes.discard(q)

    def publier(self, type_: str, **donnees) -> None:
        for q in list(self.abonnes):
            if not q.full():
                q.put_nowait({"type": type_, **donnees})

    # --- files et tours ----------------------------------------------------------------
    def soumettre(self, ident: str, texte: str, de: str | None = None, sauts: int = 0,
                  harnais: str | None = None, modele: str | None = None,
                  mandat: bool = False, source: str = "", role: str = "", humain: bool = False,
                  direct: bool = False) -> str:  # direct : jamais acheminé vers la mère (reprise d'office)
        executant.exiger_ia(self.vault.tache(ident))  # INV-EXECUTANT-1 : rien ne part sur une tâche « Moi »
        if humain: self.retenus.discard(ident); self.attente_muette.remettre(ident)  # INV-MAIN-2 ; INV-EXEC-11 : un message humain débloque la file retenue
        harnais = harnais if self.config.interface.actif("moteurs") else None  # INV-INTERFACE-1
        if not texte or not texte.strip():
            raise Invalide(langues.t("serveur.moteur.message_vide"))
        if sauts > self.config.moteur.sauts_max:  # INV-MSG-1 : coupe les boucles entre agents.
            raise Conflit(langues.t("serveur.moteur.plafond_sauts", n=self.config.moteur.sauts_max))
        if harnais and harnais not in self.registre:
            raise Invalide(langues.t("serveur.moteur.harnais_inconnu", nom=harnais))
        catalogue.modele_valide(modele or "")
        pour = ""
        if not (mandat or role or direct):  # INV-REGROUPE-2 : la mère travaille pour une sous-tâche regroupée
            ident, texte, pour = regroupement.acheminer(self, ident, texte, de or "")
            harnais, modele = (None, None) if pour else (harnais, modele)  # jamais le moteur de la mère
        if de:
            texte = f"[Message de la tâche {de}]\n{texte}"
        self.files[ident].append(Envoi(texte, sauts, de or "", harnais, modele, source, mandat,
                                  role or ("mandat" if mandat else ""), pour=pour))
        if self.etat_de(ident) != "en_cours" and ident not in self.retenus:
            self.etats[ident] = "en_file"
        self.en_file_depuis.setdefault(ident, maintenant())
        self._sauver_actifs(); decisions.noter(self, ident)  # INV-EXEC-9 : la file survit ; INV-DECISIONS-2 : réponse notée
        self.publier("arbre")  # INV-VERROU-1 : la tâche occupée paraît aussitôt à l'écran
        self._lancer_boucle(ident)
        return self.etats[ident]

    async def _boucle(self, ident: str) -> None:
        # INV-EXEC-2 : une seule boucle par tâche consomme sa file dans l'ordre.
        # INV-EXEC-6 : aucune mort silencieuse : toute exception est journalisée et publiée.
        try:
            while self.files[ident]:
                envoi = self.attente[ident] = self.files[ident].popleft()
                try:
                    await self._attendre_verrou(ident)
                    if envoi := await self._preparer_compactage(ident, envoi):  # INV-COMPACT-1
                        await self._tour_au_poste(ident, envoi)  # INV-POSTE-1
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._echec_boucle(ident, e)
                self.attente.pop(ident, None)
                if self.etat_de(ident) in ("interrompu", reseau.ETAT) or ident in self.retenus: return  # INV-EXEC-11
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._echec_boucle(ident, e)
        finally:
            self.envois.pop(ident, None); self.attente.pop(ident, None)
            self.en_file_depuis.pop(ident, None)
            if self.etat_de(ident) not in ("interrompu", reseau.ETAT): self.etats[ident] = "inactif"
            if ident in self.mandats.sans_tour():
                # INV-TRANSFO-1 : un mandat posé sans qu'aucun tour l'ait reçu se signale.
                log.warning("mandat de %s resté sans tour", ident)
                self.publier("mandat_sans_tour", tache=ident)

    def _echec_boucle(self, ident: str, e: Exception) -> None:
        log.exception("boucle de la tâche %s : %s", ident, e)
        self.tours.pop(ident, None)
        self.actifs.pop(ident, None)
        self._sauver_actifs()
        self.publier("tour_fin", tache=ident, statut="bloque", fiche_absente=False,
                     erreur=f"{type(e).__name__}: {e}")

    def _consigne(self, ident: str) -> str:
        taches, conts = self.vault.index()
        t = taches[ident]
        parents = self.vault._parents(taches)
        soeurs = [str(s.chemin) for s in taches.values() if s.conteneur == t.conteneur
                  and s.id != ident and parents[s.id] == parents[ident]
                  and s.statut in self.config.vault.statuts_ouverts and not s.pilotage][:20]
        return self.config.consigne.format_map(_Gabarit(
            titre=t.titre, chemin=str(t.chemin),
            fil_ariane=" > ".join(self.vault.fil_ariane(ident)),
            contexte=str(self.vault.racine / t.conteneur / self.config.vault.contexte),
            soeurs=", ".join(soeurs) or "aucune", equipe=(self.revues.equipe.consigne() if self.config.interface.actif("equipe")
                    else "aucun persona actif."),
            orch=f'"{Path(sys.executable).as_posix()}" "{(RACINE_DEPOT / "orch.py").as_posix()}"')) + "\n" + langues.consigne_langue() + self.reprise_auto.consigne(ident) + apprendre.consigne(self.config, t.fm)  # INV-APPRENDRE-1

    def _journal(self, ident: str):
        # INV-EXEC-4 : un journal brut par tour.
        now = dt.datetime.now()
        dossier = self.config.donnees / "journal" / now.strftime("%Y-%m-%d")
        dossier.mkdir(parents=True, exist_ok=True)
        return open(dossier / f"{ident}-{now.strftime('%H%M%S')}.jsonl", "a", encoding="utf-8")

    async def _tour(self, ident: str, envoi: Envoi) -> None:
        final, erreur, tour, outils, choix, nom = None, None, None, False, None, ""
        # Tout le tour est sous `try` : un échec (vault, journal, harnais) devient un tour en
        # échec publié, jamais une boucle morte qui perdrait les messages suivants.
        try:
            if envoi.harnais is not None or envoi.modele is not None:
                self._moteur(ident, envoi.harnais, envoi.modele)
            t = self.vault.tache(ident)
            choix = self.roles.pour_envoi(envoi)  # INV-MOTEUR-2 : tour éphémère d'un rôle assistant
            auto = None if choix else self.economie.pour_tour(t, ident in self.a_deriver)  # INV-ECO-1
            nom = choix.harnais if choix else auto.harnais
            fabrique = self.registre.get(nom)
            session = None if choix else (str(t.fm.get("session") or "") or None)
            deriver = False
            if not session and not choix and ident in self.a_deriver:
                session, deriver = self.a_deriver.pop(ident), True
            self.etats[ident] = "en_cours"
            self.envois[ident] = envoi
            if envoi.mandat:
                self.mandats.demarrer(ident)
            self.actifs[ident] = reprise.enregistrement(ident, envoi)
            self.interrompus.pop(ident, None)
            self.attente.pop(ident, None)
            self._sauver_actifs()
            self.publier("tour_debut", tache=ident)
            self.publier("arbre")
            self.vault.poser_statut(ident, "en-cours")
            connue = session if not deriver else None
            if session: session_valide(session)  # la valeur vient du fichier : jamais de --resume douteux
            modele = catalogue.modele_valide(choix.modele if choix else auto.modele)
            if not fabrique:
                # INV-MOTEUR-1 : échec avant tout lancement, jamais de repli sur un autre harnais.
                raise Invalide(f"harnais inconnu : {nom}")
            self.roles.compter(nom, envoi.role or "tache")
            with self._journal(ident) as journal:
                # En tête de journal : la conversation se relit d'ici si le harnais n'a pas de
                # transcript lisible.
                journal.write(json.dumps({"type": "orch_message", "texte": envoi.texte,
                                          "de": envoi.de, "harnais": nom, "date": maintenant()},
                                         ensure_ascii=False) + "\n")
                tour = self.tours[ident] = Tour(ident, maintenant(),
                                                self.instancier(ident, t, nom, modele, fabrique))  # INV-COMPACT-1
                await self.point_avant_tour(ident, tour.harnais, journal, choix)  # INV-RETOUR-1, INV-RETOUR-3
                env = {"ORCH_TACHE": ident, "ORCH_SAUTS": str(envoi.sauts),
                       "ORCH_URL": f"http://127.0.0.1:{self.config.port}"}
                texte = pilotage.amorcer(self, ident, envoi.texte)  # INV-PILOTAGE-2
                texte = executant.amorcer(self, ident, texte, neuve=not session)  # INV-EXECUTANT-2
                if deriver:
                    # La conversation dérivée hérite de la consigne de sa mère (figée par le
                    # harnais) : on lui dit qu'elle a changé de tâche (essai réel du 12/11).
                    texte = (f"[Conversation dérivée. Tu travailles désormais sur la tâche "
                             f"« {t.titre} » (id {ident}, fichier {t.chemin}). Ta fiche finale "
                             f"porte sur cette tâche, plus sur la précédente.]\n\n{texte}")
                consigne = self._consigne(ident)
                neuf = lambda: sessions.premier_message(texte, consigne, tour.harnais, self.sessions, t, nom, self.registre, self.config.harnais)  # noqa: E731
                if not session:
                    texte = neuf()
                try:
                    flux = session_perdue.avec_repli(tour.harnais.lancer, neuf, session, deriver,
                                                     message=texte, consigne=consigne, env=env, modele=modele)
                    async with aclosing(flux), \
                            asyncio.timeout(self.config.moteur.duree_max_s or None):
                        async for ev in flux:
                            journal.write(json.dumps(ev.brut or asdict(ev), ensure_ascii=False) + "\n")
                            journal.flush()
                            reprise.progres(self, ident, envoi)  # INV-EXEC-1
                            if ev.session and ev.session != connue and not choix:
                                # INV-EXEC-3 : la session est écrite dès qu'elle est connue.
                                connue = session_valide(ev.session)
                                self.vault.modifier(ident, {"session": connue, "harnais": nom})
                            if ev.type == "session_perdue":  # INV-SESSION-1
                                connue = None; self.vault.modifier(ident, {"session": None})
                            elif ev.type == "texte":
                                tour.dernier = ev.texte[-300:]
                                self.publier("tour_texte", tache=ident,
                                             texte=fiches.sans_rendu(ev.texte))
                            elif ev.type == "outil":
                                outils = True
                                self.publier("tour_outil", tache=ident, texte=ev.texte)
                            elif ev.type == "suivi" and ev.suivi: self.publier("suivi", tache=ident, **ev.suivi)  # INV-TRAVAUX-1
                            elif ev.type == "fin":
                                final = ev.texte or tour.dernier
                                self.mesure_tour[ident] = {**(ev.mesure or {}), **instrumentation.echantillon(tour.harnais)}  # INV-COMPACT-1
                                self.economie.conso.mesurer(nom, ev.brut)  # INV-ECO-2
                            elif ev.type == "erreur":
                                erreur = ev.texte or "erreur du harnais"
                finally:
                    # Toute sortie de la boucle tue l'arbre de processus : pas d'orphelin.
                    await asyncio.shield(tour.harnais.arreter())
        except TimeoutError: erreur = "durée maximale du tour dépassée"
        except Exception as e:  # le serveur survit à tout échec d'un tour
            erreur = f"{type(e).__name__}: {e}"
        finally:
            self.tours.pop(ident, None)
            if (rec := self.actifs.pop(ident, None)) and tour and tour.arrete:
                self.interrompus[ident] = rec  # INV-EXEC-1 : « Relancer » le reprendra
            self._sauver_actifs()
        if erreur and not choix and not (tour and tour.arrete) and await self.reseau.signaler(ident, envoi, erreur, nom):
            return  # INV-RESEAU-1 : gelé jusqu'au retour du réseau
        if not choix and self.quota.basculer(ident, envoi, erreur, nom, bool(tour and tour.arrete)): return  # INV-QUOTA-1
        if erreur and not choix and not (tour and tour.arrete) and self.reprise_auto.api_passagere(ident, envoi, erreur, nom): return  # INV-REPRISE-1
        if self.roles.reprendre(self, ident, envoi, choix, final, erreur, outils,
                                bool(tour and tour.arrete)):
            return  # INV-MOTEUR-2 : le même message repart sur le moteur de la tâche
        try:
            await self._conclure_tour(ident, tour, final, erreur, envoi)  # INV-CONTROLE-1, INV-COMPACT-1
        except Exception as e:  # INV-EXEC-6 : une conclusion en échec ne tue pas la boucle
            self._echec_boucle(ident, e)
        self._reveil_fin(ident, envoi, erreur, nom, (tour.arret or "humain") if tour and tour.arrete else "")

    def _conclure(self, ident: str, tour: Tour | None, final, erreur, sauts: int = 0,
                  de: str = "") -> None:
        fiche_absente, fiche, decoupage, verdict = False, None, None, None
        if tour and tour.arrete:
            # INV-EXEC-1 : interrompu, rendu à l'humain, jamais relancé.
            self.etats[ident] = "interrompu"
            statut, erreur = self.vault.retour, "tour interrompu"
            if self.reprise_auto.marquer(ident, tour): statut = "en-cours"  # INV-REPRISE-1 : reprise d'office, statut inchangé
        elif erreur or final is None:
            statut, erreur = "bloque", erreur or "tour terminé sans résultat"
        elif verdict := self.relance_fiche.juger(ident, final):  # INV-EXEC-12 : fiche absente ≠ question
            statut, erreur = ("en-cours", None) if verdict == "relancer" else ("bloque", MOTIF_FICHE)
        else:
            statut = self._statut_controle(ident, self.vault.statut_declare(fiches.declaration(final)))
        if not (tour and tour.arrete) and not session_perdue.session_absente(erreur): self.economie.issue(ident, statut, final)  # INV-ECO-1 : escalade
        terminee, echec, message_echec = False, None, None
        if erreur and not (tour and tour.arrete):
            # INV-EXEC-8 : un tour en échec laisse un message du système (journal) et un repère
            # (`echec_tour`) jusqu'au prochain tour réussi.
            echec, message_echec = erreur, echecs.message(erreur)
            self._journaliser_echec(ident, echec, message_echec)
        try:
            # Un humain a pu clore, abandonner ou changer le statut pendant le tour : on le garde.
            if (t := self.vault.tache(ident)).statut == "en-cours" or t.verrouille:
                if statut == "fait" and str(t.fm.get("nature") or "") in NATURES_SANS_FIN:
                    statut = "en-cours"  # tâche permanente : elle ne se termine jamais
                self.vault.poser_statut(ident, statut)
                terminee = statut == "fait"
            if not erreur:
                fiche = fiches.analyser_rendu(final)
                if fiche is None:
                    fiche_absente = True
                    fiche = fiches.lire_fiche(fiches.lire(self.vault.tache(ident).chemin))
                    if final.strip():
                        fiche["situation"] = final[:500]
                # INV-TRANSFO-1 : seul un tour réussi répond à un mandat ; interrompu, il attend.
                decoupage = transformations.conclure(self, ident, final, fiche)
                self.vault.modifier(ident, {"echec_tour": None}
                                    if self.vault.tache(ident).fm.get("echec_tour") else {}, fiche)
            elif message_echec:
                self.vault.modifier(ident, {"echec_tour": message_echec})
        except NonTrouve:
            pass  # la tâche a disparu du vault pendant le tour : rien à écrire
        except OSError as e:
            erreur = erreur or f"{type(e).__name__}: {e}"
        fin = {"tache": ident, "statut": statut, "fiche_absente": fiche_absente,
               **({"decoupage": decoupage} if decoupage is not None else {})}
        self.publier("tour_fin", **fin, **({"erreur": erreur} if erreur else {}))
        self.publier("arbre")
        if not erreur and fiche is not None:
            pilotage.remonter(self, ident, fiche)  # INV-PILOTAGE-3 : une ligne, aucun tour
            if self.config.liens.propagation and self.config.interface.actif("liens"):
                self._propager(ident, fiche, sauts + 1, de)
        if verdict == "relancer": redemander(self, ident)  # INV-EXEC-12 : une seule relance
        elif not (erreur or fiche_absente or (tour and tour.arrete)) and fiche: self.attente_muette.juger(ident, statut, fiche)  # INV-MAIN-2
        if terminee and not erreur and (self.config.interface.actif("equipe")  # INV-INTERFACE-1
                                        or self.validation_auto.applique(ident)):  # INV-VALID-2
            self.revues.declencher(ident)

    async def arreter(self, ident: str) -> str:
        self.vault.tache(ident)
        self.files[ident].clear()
        self.annuler_reveil(ident)  # INV-EXEC-10
        self.reprise_auto.annuler(ident)  # INV-REPRISE-1 : un arrêt humain ne reprend jamais
        if tour := self.tours.get(ident):
            tour.arrete, tour.arret = True, "humain"
            self.etats[ident] = "interrompu"
            await tour.harnais.arreter()
        elif (boucle := self.boucles.get(ident)) and not boucle.done():
            boucle.cancel()  # en attente d'une place : rien n'a été lancé
            self.etats[ident] = "inactif"
        elif self.etat_de(ident) in ("interrompu", reseau.ETAT): self.reseau.oublier(ident); self.etats[ident] = "inactif"
        return self.etat_de(ident)

    # --- gestes composés -----------------------------------------------------------------
    def creer(self, titre: str, description: str = "", conteneur: str | None = None,
              parent: str | None = None, lancer: bool = False, harnais: str | None = None,
              modele: str | None = None, echeance: str | None = None,
              priorite: str | None = None, mission: str = "") -> str:
        harnais = harnais if self.config.interface.actif("moteurs") or harnais in self.registre else None  # INV-INTERFACE-1 : sauf l'assistant choisi aux premiers pas
        if harnais and harnais not in self.registre:
            raise Invalide(langues.t("serveur.moteur.harnais_inconnu", nom=harnais))
        catalogue.modele_valide(modele or "")
        if lancer: assistant_absent.exiger(self, None, harnais)  # INV-PREMIERS-PAS-2 : avant de créer
        ident = self.vault.creer(titre, conteneur, parent, description, harnais, temps.valider(echeance or None, priorite or None))
        if modele: self.vault.modifier(ident, {"modele": modele})
        self.publier("arbre")
        if lancer:  # la mission (consigne du premier tour) l'emporte sur la description
            self.soumettre(ident, mission or description or titre)
        return ident

    def deriver(self, origine: str, titre: str, lien: str, avec_fil: bool,
                message: str | None = None, description: str = "") -> str:
        if lien not in ("enfant", "soeur"):
            raise Invalide(langues.t("serveur.moteur.lien_attendu"))
        o = self.vault.tache(origine)
        session = str(o.fm.get("session") or "")
        if avec_fil and not session:
            raise Conflit(langues.t("serveur.moteur.sans_session"))
        nom = str(o.fm.get("harnais") or self.config.moteur.harnais_defaut)
        if avec_fil and not getattr(self.registre.get(nom), "sait_deriver", True):
            raise Conflit(langues.t("serveur.moteur.deriver_impossible", nom=nom))
        parent = origine if lien == "enfant" else self.vault.detail(origine)["parent"]
        ident = self.vault.creer(titre, o.conteneur, parent, description,
                                 str(o.fm.get("harnais") or "") or None if avec_fil else None)
        if avec_fil:
            self.a_deriver[ident] = session
        self.publier("arbre")
        if message:
            self.soumettre(ident, message)
        return ident

    def changer_moteur(self, ident: str, harnais: str | None = None,
                       modele: str | None = None) -> None:
        """Pose harnais et modèle (None = inchangé, "" = défaut) ; refusé pendant un tour."""
        if self.etat_de(ident) == "en_cours":
            raise Conflit(langues.t("serveur.moteur.seance_en_cours"))
        self._moteur(ident, harnais, modele)

    def _moteur(self, ident: str, harnais: str | None, modele: str | None) -> None:
        harnais = harnais if self.config.interface.actif("moteurs") else None  # INV-INTERFACE-1
        if harnais and harnais not in self.registre:
            raise Invalide(langues.t("serveur.moteur.harnais_inconnu", nom=harnais))
        maj = sessions.changement(self.vault.tache(ident), self.sessions, harnais, modele,
                                  self.config.moteur.harnais_defaut)
        if maj:
            self.vault.modifier(ident, maj)
        self.liberer(ident)  # INV-EXEC-11 : changer de moteur débloque la file retenue

    def message_en_cours(self, ident: str) -> dict | None:
        """Message du tour en cours, au format d'un message de conversation."""
        if (envoi := self.envois.get(ident)) and ident in self.tours:
            return {"role": "utilisateur", "texte": envoi.texte, "outils": [], "secondaire": False,
                    "horodatage": self.tours[ident].depuis}
        return None

    def etat_global(self) -> dict:
        taches = self.vault.index()[0]
        compte: dict[str, int] = defaultdict(int)
        for t in taches.values():
            if self.vault.ouverte(t) and not t.pilotage:  # INV-PILOTAGE-1
                compte[t.statut] += 1
        return {"pauses": self.pauses(), "roles": self.roles.public(), "tours": [{"tache": t.tache, "titre": taches[t.tache].titre if t.tache in taches
                           else t.tache, "depuis": t.depuis, "dernier": t.dernier,
                           "persona": t.persona, "pause_ram": self._sem.en_pause(t.tache)} for t in self.tours.values()],
                **self.file_publique(),  # INV-ORDO-1, INV-ORDO-2 : rang, motif, prérequis attendus
                "mandats_sans_tour": [i for i in self.mandats.sans_tour()
                                      if self.etat_de(i) not in ("en_cours", "en_file")],
                "a_moi": etat_main.compter_humain(self),  # INV-MAIN-4
                "en_retard": temps.nb_retard(self.vault),
                "propositions": sum(p["etat"] == "en_attente" for p in self.propositions.liste),
                "a_valider": sum(self.vault.a_valider(t) for t in taches.values()),
                "reseau": self.reseau.public(), "occupees": self.occupees(), "poste": self.poste.public(),  # INV-VERROU-1, INV-POSTE-1
                "compte": dict(compte), "fiches_absentes": self.relance_fiche.public()}
