"""Interface native du harnais : la tâche ouverte dans un onglet du terminal, relais à la fermeture.

Rôle : ouvrir un onglet Windows Terminal (`wt -w 0 nt`, repli : nouvelle console) qui lance
`orch.py natif <fichier>` — un relais qui écrit son PID puis exécute le harnais dans l'onglet ;
tant que ce processus vit, la tâche est « au terminal » (aucun tour, messages en file) ; à sa fin,
relire l'échange, mettre la fiche à jour, reprendre en arrière-plan un tour coupé, vider la file.
Frontières : ne lance aucun tour lui-même (la boucle du moteur s'en charge) ; aucune E/S vault hors
`Vault` ; l'état d'ouverture vit en mémoire (un redémarrage du serveur l'oublie : l'onglet survit,
la fermeture n'est alors plus relayée — ponytail: persister `ouverts` si le cas se présente).
Invariants portés : INV-NATIF-1.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import codespace, depot, fiches, langues, sessions
from .config import RACINE_DEPOT
from .propositions import maintenant
from .vault import Conflit, NonTrouve

log = logging.getLogger(__name__)
DEMARRAGE_S = 60  # délai laissé au terminal pour lancer le relais (sinon : ouverture ratée)
PREMIER = ("[GoldenBrain] Interface native ouverte sur la tâche « {titre} ». Lis ce que la consigne "
           "indique, dis où tu t'es placé, puis attends les instructions de l'utilisateur.")
REPRISE = ("[GoldenBrain — reprise] L'interface native a été fermée pendant ton travail. Reprends "
           "là où tu t'es arrêté, termine ce qui était demandé et rends ta fiche.")


def ouvrir_onglet(titre: str, dossier: str, argv: list[str]) -> None:
    """Onglet de la fenêtre Windows Terminal courante ; repli : nouvelle console."""
    if wt := shutil.which("wt"):
        # `;` sépare les commandes de wt : il ne doit pas paraître dans le titre.
        subprocess.Popen([wt, "-w", "0", "nt", "--title", titre.replace(";", ",")[:60],
                          "-d", dossier, *argv])
        return
    drapeaux = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform == "win32" else 0
    subprocess.Popen(argv, cwd=dossier, creationflags=drapeaux)


def _vivant_windows(pid: int):
    import ctypes
    k = ctypes.windll.kernel32
    poignee = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not poignee:
        return None
    return k, poignee


def _vivant_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # POSIX seulement : sous Windows, ce signal tuerait le processus
    except OSError:
        return False
    try:  # INV-NATIF-1 : un zombie (fini, non réclamé par son parent) répond encore à `kill 0`
        return Path(f"/proc/{pid}/stat").read_text("utf-8").rpartition(")")[2].split()[0] != "Z"
    except (OSError, IndexError):
        return True  # pas de /proc (macOS) : repli sur `kill 0`


async def attendre_fin(fichier_pid: Path, demarrage_s: float = DEMARRAGE_S) -> None:
    """Rend la main quand le relais (PID écrit dans `fichier_pid`) a fini, ou s'il n'a jamais
    démarré. Interrogation par pas d'une seconde : aucun fil bloqué à l'arrêt du serveur."""
    limite = time.monotonic() + demarrage_s
    while not fichier_pid.exists():
        if time.monotonic() > limite:
            return
        await asyncio.sleep(0.5)
    try:
        pid = int(fichier_pid.read_text("utf-8").strip())
    except (OSError, ValueError):
        return
    if sys.platform == "win32":
        if not (h := _vivant_windows(pid)):
            return
        k, poignee = h
        try:
            while await asyncio.to_thread(k.WaitForSingleObject, poignee, 1000) == 0x102:
                pass  # WAIT_TIMEOUT : toujours vivant
        finally:
            k.CloseHandle(poignee)
        return
    while _vivant_posix(pid):
        await asyncio.sleep(1)


class Natifs:
    """INV-NATIF-1 : tâches ouvertes dans l'interface native de leur harnais."""

    def __init__(self, moteur):
        self.m = moteur
        self.ouverts: dict[str, dict] = {}  # id -> {depuis, moteur, avant, veille}

    def ouvert(self, ident: str) -> dict | None:
        return self.ouverts.get(ident)

    def ouvrir(self, ident: str) -> dict:
        m = self.m
        if ident in self.ouverts:
            raise Conflit(langues.t("serveur.natif.deja_ouverte"))
        if ident in m.tours or m.etat_de(ident) in ("en_cours", "en_file"):
            raise Conflit(langues.t("serveur.natif.seance_en_cours"))
        t = m.vault.tache(ident)
        if codespace.lieu(t) == "codespace":  # INV-CODESPACE-2 : jamais lancée sur le poste
            raise Conflit(langues.t("serveur.natif.codespace"))
        nom = str(t.fm.get("harnais") or m.config.moteur.harnais_defaut)
        if not (fabrique := m.registre.get(nom)):
            raise Conflit(langues.t("serveur.natif.harnais_inconnu", nom=nom))
        conf = depot.conf_harnais(m.vault, m.config.harnais.get(nom, {}), ident)
        h = fabrique(conf)
        session = str(t.fm.get("session") or "")
        modele = str(t.fm.get("modele") or "")
        spec: dict = {"dossier": getattr(h, "dossier", "") or conf.get("dossier") or str(Path.home()),
                      "env": {"ORCH_TACHE": ident, "ORCH_SAUTS": "0",
                              "ORCH_URL": f"http://127.0.0.1:{m.config.port}"}}
        if hasattr(h, "argv_natif"):
            consigne = m._consigne(ident)
            message = ""
            if not session:  # session neuve, préparée comme un premier tour GoldenBrain
                session = str(uuid.uuid4())
                message = sessions.premier_message(PREMIER.format(titre=t.titre), consigne, h,
                                                   m.sessions, t, nom, m.registre, m.config.harnais)
                m.vault.modifier(ident, {"session": session, "harnais": nom})
                neuve = True
            else:
                neuve = False
            spec["argv"] = h.argv_natif(session, neuve, consigne, modele, message)
        elif session:
            spec["commande"] = h.commande_terminal(session)
        else:
            raise Conflit(langues.t("serveur.natif.non_preparee", nom=nom))
        avant = len(self._transcript(h, session))
        dossier = m.config.donnees / "etat" / "natif"
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / f"{ident}.json"
        fichier.with_suffix(".pid").unlink(missing_ok=True)
        fiches.ecrire_atomique(fichier, json.dumps(spec, ensure_ascii=False))
        ouvrir_onglet(t.titre, spec["dossier"],
                      [sys.executable, str(RACINE_DEPOT / "orch.py"), "natif", str(fichier)])
        self.ouverts[ident] = {"depuis": maintenant(), "moteur": "/".join(x for x in (nom, modele) if x),
                               "avant": avant}
        self.ouverts[ident]["veille"] = asyncio.get_running_loop().create_task(
            self._veiller(ident, fichier.with_suffix(".pid")))
        m.publier("arbre")
        return {"tache": ident, "harnais": nom, "session": session}

    async def _veiller(self, ident: str, fichier_pid: Path) -> None:
        await attendre_fin(fichier_pid)  # annulée à l'arrêt du serveur : aucune clôture
        try:
            self.clore(ident)
        except Exception:  # INV-EXEC-6 : la clôture ne meurt jamais en silence
            log.exception("clôture de l'interface native : %s", ident)
            self.ouverts.pop(ident, None)
            self.m.publier("arbre")

    @staticmethod
    def _transcript(h, session: str) -> list:
        try:
            return h.transcript(session, 0) if session else []
        except (NotImplementedError, OSError):
            return []

    def clore(self, ident: str) -> None:
        """Fin du processus : fiche relue, tour coupé repris en arrière-plan, puis la file."""
        from .moteur import NATURES_SANS_FIN, Envoi  # import tardif : cycle
        m = self.m
        o = self.ouverts.pop(ident, None) or {"avant": 0}
        coupe = False
        try:
            t = m.vault.tache(ident)
            nom = str(t.fm.get("harnais") or m.config.moteur.harnais_defaut)
            h = m.registre[nom](depot.conf_harnais(m.vault, m.config.harnais.get(nom, {}), ident))
            neufs = self._transcript(h, str(t.fm.get("session") or ""))[o["avant"]:]
            if neufs:
                # Coupé en plein travail : rien après le dernier message de l'utilisateur, ou le dernier
                # message de l'agent appelle encore un outil (pas de réponse finale).
                coupe = neufs[-1].role == "utilisateur" or bool(neufs[-1].outils)
                tour: list[str] = []
                for msg in neufs:
                    tour = [] if msg.role == "utilisateur" else tour + [msg.texte]
                rendu = "\n\n".join(tour)
                if not coupe and (fiche := fiches.analyser_rendu(rendu)) is not None:
                    if t.statut == "en-cours" or t.verrouille:
                        statut = m.vault.statut_declare(fiches.declaration(rendu))
                        if statut == "fait" and str(t.fm.get("nature") or "") in NATURES_SANS_FIN:
                            statut = "en-cours"  # INV-EXEC-7
                        m.vault.poser_statut(ident, statut)
                    m.vault.modifier(ident, {}, fiche)
        except (NonTrouve, KeyError, OSError) as e:
            log.warning("interface native de %s : échange non relu (%s)", ident, e)
        if coupe:
            m.files[ident].appendleft(Envoi(REPRISE))
        m.publier("natif_fin", tache=ident, reprise=coupe)
        m.publier("arbre")
        if m.files.get(ident):
            m.etats[ident] = "en_file"
            boucle = m.boucles.get(ident)
            if not boucle or boucle.done():
                m.boucles[ident] = asyncio.get_running_loop().create_task(m._boucle(ident))

