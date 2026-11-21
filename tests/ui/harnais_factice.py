"""Harnais factice des tests d'interface : joue un tour scénarisé, ne lance jamais un vrai agent.

Rôle : se brancher dans le registre `HARNAIS` du VRAI serveur (voir `serveur.py`) sous le nom
« faux ». Le tour émet une session, un texte, un outil, puis une fin portant une fiche. Un message
qui contient « [lent N] » fait durer le tour N secondes (ou jusqu'à son arrêt) avant l'outil ; « [echec] » le fait échouer (quota) ; « [creer <titre> | <conteneur>] » crée cette tâche par la vraie
commande `orch` (chat de projet, INV-PILOTAGE-1) ; « [journaux] » ouvre une session sans transcript lisible
(la conversation se relit aux journaux, comme Codex : « Modifier », INV-RETOUR-1) ; « [bavard] » écrit 64 Ko sur la sortie d'erreur
du serveur (journal abondant, voir `scenario_porte.py`) ; « [aides] » lance deux sous-agents (un fini), une liste
d'étapes et une écriture, avec un processus inerte à mettre en pause (écran « En cours », INV-TRAVAUX-1).
Démonstration (captures, vidéo) : si `GB_DEMO` nomme un fichier JSON `{message: scène}`, un message qui y figure
joue sa scène (texte, sous-agents, durée, fin) dans la langue de la démonstration, sans directive visible.
Frontières : aucune E/S vault ; seul processus : `orch creer`, comme un agent. Hors de `src/` : n'entre pas dans le produit.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from orchestrateur.harnais import Evenement, Message

RENDU = ("Travail fait.\n<fiche>\nstatut: terminee\nfait: lu le dossier\nsituation: en bonne voie\n"
         "reste: rien\nprochain_pas: relire\nsous_taches:\n- [x] lire\n</fiche>")


# Mode « Apprendre » (INV-APPRENDRE-1) : le harnais obéit à la consigne reçue, comme un vrai agent.
EXPLICATION = "> [!apprendre] Ce que je fais\n> Je lis le dossier pour comprendre où en est le travail avant de le modifier."
RENDU_APPRENDRE = RENDU.replace("prochain_pas: relire\n", "prochain_pas: relire\nretenir: lire avant d'agir ; vérifier ensuite ; noter ce qui reste\n")


def _scenes() -> dict:
    chemin = os.environ.get("GB_DEMO")
    return json.loads(Path(chemin).read_text(encoding="utf-8")) if chemin else {}


class HarnaisFactice:
    nom = "faux"
    consigne_native = True
    sait_deriver = True

    def __init__(self, conf: dict):
        self.stop = asyncio.Event()

    async def lancer(self, message, *, session, deriver, consigne, env, modele=""):
        if scene := _scenes().get(message.strip()):
            async for e in self._jouer(scene, session or "s-demo"):
                yield e
            return
        apprend = "Mode « Apprendre » actif" in (consigne or "")
        sid = session or ("s-journaux" if "[journaux]" in message else "s-apprendre" if apprend else "s-faux")
        yield Evenement("session", session=sid)
        yield Evenement("texte", texte="je lis le dossier" + (f"\n\n{EXPLICATION}" if apprend else ""))
        await asyncio.sleep(0.05)
        if "[aides]" in message:  # écran « En cours » : un processus inerte, dans sa propre session (comme un harnais)
            self._proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", "import time; time.sleep(600)",
                **({} if sys.platform == "win32" else {"start_new_session": True}))
            yield Evenement("suivi", suivi={"sous_agent": {"id": "a1", "description": "Relire le module des factures", "genre": "Explore"}})
            yield Evenement("suivi", suivi={"sous_agent": {"id": "a2", "description": "Chercher les tests existants", "genre": "Explore"}})
            yield Evenement("suivi", suivi={"sous_agent": {"id": "a2", "fin": True, "erreur": False}})
            yield Evenement("suivi", suivi={"avancement": {"fait": 2, "total": 5}})
            yield Evenement("outil", texte="Write: /tmp/projet/factures.py")
            yield Evenement("outil", texte="Bash: pytest -q")
        if m := re.search(r"\[lent (\d+)\]", message):
            try:
                await asyncio.wait_for(self.stop.wait(), int(m[1]))
                return  # arrêté : le moteur marque le tour interrompu
            except TimeoutError:
                pass
        if "[reseau]" in message:  # coupure réseau : le harnais échoue comme un vrai client sans connexion
            yield Evenement("erreur", texte="API Error: Can't reach the API server — check your internet or DNS (ENOTFOUND)")
            return
        if "[bavard]" in message:  # assez pour remplir un tuyau non lu (4 Ko sous Windows)
            sys.stderr.write("journal abondant " * 4096)
            sys.stderr.flush()
        if "[echec]" in message:  # scénario d'échec de tour : quota épuisé
            yield Evenement("erreur", texte="You’ve hit your usage limit. Try again in 5 hours.")
            return
        if m := re.search(r"\[creer (.+?) \| (.+?)\]", message):  # le geste d'un agent de pilotage
            orch = Path(__file__).resolve().parents[2] / "orch.py"
            await asyncio.to_thread(subprocess.run, [sys.executable, str(orch), "creer", m[1], "--conteneur", m[2],
                                     "--description", f"Tâche créée par le harnais factice : {m[1]}."],
                                    env={**os.environ, **env}, capture_output=True, timeout=60)
        if m := re.search(r"<texte>\n(.*?)\n</texte>", message, re.S):  # bouton « IA » des notes
            yield Evenement("fin", texte=f"<proposition>## Points clés\n- synthèse de : {m[1]}</proposition>")
            return
        if (p := getattr(self, "_proc", None)) and p.returncode is None:  # [aides] : fin du tour
            p.kill()
            await p.wait()
        yield Evenement("outil", texte="Read: dossier")
        yield Evenement("fin", session=sid, texte=RENDU_APPRENDRE if apprend else RENDU, mesure={"contexte": 123_456, "cout": 0.02})

    async def _jouer(self, scene: dict, sid: str):
        """Scène de démonstration : le tour se lit comme celui d'un vrai agent, dans la langue choisie."""
        yield Evenement("session", session=sid)
        yield Evenement("texte", texte=scene["texte"])
        for i, aide in enumerate(scene.get("aides", [])):
            yield Evenement("suivi", suivi={"sous_agent": {"id": f"a{i}", "description": aide, "genre": "Explore"}})
        if scene.get("aides"):
            yield Evenement("suivi", suivi={"avancement": {"fait": 2, "total": 5}})
            yield Evenement("outil", texte="Write: factures/export.py")
            yield Evenement("outil", texte="Bash: pytest -q")
        try:
            await asyncio.wait_for(self.stop.wait(), scene.get("duree", 1))
            return
        except TimeoutError:
            pass
        yield Evenement("outil", texte="Read: dossier")
        yield Evenement("fin", session=sid, texte=scene["fin"], mesure={"contexte": 48_000, "cout": 0.03})

    async def arreter(self):
        self.stop.set()
        if (p := getattr(self, "_proc", None)) and p.returncode is None:
            p.kill()
            await p.wait()

    def transcript(self, session, limite):
        if session.startswith("s-journaux"):
            raise NotImplementedError
        texte = f"bonjour {session}" + (f"\n\n{EXPLICATION}" if session == "s-apprendre" else "")
        return [Message("assistant", texte, ["Read"], "2026-11-12T10:00:00")]

    def commande_terminal(self, session):
        return f"faux --resume {session}"
