"""Adaptateur GitHub Copilot CLI : un tour en `copilot -p … --output-format json`, reprise par `--resume=<id>`.

Rôle : traduire le flux JSONL de `copilot` en `Evenement`.
Frontières : n'écrit pas dans le vault ; une instance par tour ; pas de transcript lisible
(la route `/conversation` se rabat sur les journaux).
Invariants portés : aucun en propre (INV-EXEC-3 repose sur l'événement `session` émis AVANT le
lancement : l'identifiant est choisi par nous, `--session-id=<uuid>`).

Vérifié dans la documentation officielle (16/11) : `-p`, `--output-format=json` (JSONL), `--model`,
`--allow-all-tools`, `--no-ask-user`, `--resume`, `--session-id`, `~/.copilot/session-state/<id>/events.jsonl`.
NON vérifié faute de compte Copilot sur le poste : le schéma des événements JSONL d'un tour (le doc
ne le décrit pas) et la syntaxe exacte de `--resume`. `analyser` lit donc de façon tolérante les noms
d'événements du SDK Copilot (`assistant.message`, `tool.execution_start`, `result`) ; si un nom diffère,
le tour se conclut quand même sur le code de sortie, avec le texte retenu s'il y en a un.
"""

from __future__ import annotations

import os
import uuid
from contextlib import aclosing
from pathlib import Path
from typing import AsyncIterator

from . import Evenement, Message
from .processus import Processus, resoudre

# Droits accordés d'avance : sans eux, toute demande d'approbation est refusée en mode non interactif ;
# `--no-ask-user` évite qu'un tour attende une réponse humaine qui ne viendra pas.
PERMISSIONS = ("--allow-all-tools", "--no-ask-user")


def _dict(valeur) -> dict:
    return valeur if isinstance(valeur, dict) else {}


def _resume_outil(donnees: dict) -> str:
    nom = str(donnees.get("toolName") or donnees.get("name") or "?")
    args = _dict(donnees.get("arguments"))
    detail = next((str(args[k]) for k in ("command", "path", "query", "url", "pattern")
                   if isinstance(args.get(k), str)), "")
    detail = " ".join(detail.split())
    return f"{nom}: {detail[:160]}" if detail else nom


def analyser(brut: dict, etat: dict) -> list[Evenement]:
    """Une ligne JSON de `copilot --output-format json` -> événements ; `etat` porte le fil du tour."""
    type_, donnees = str(brut.get("type") or ""), _dict(brut.get("data"))
    if type_ == "assistant.message":
        texte = str(donnees.get("content") or "")
        if texte.strip():
            etat["dernier"] = texte
            return [Evenement("texte", texte=texte, brut=brut)]
    elif type_ == "tool.execution_start":
        return [Evenement("outil", texte=_resume_outil(donnees), brut=brut)]
    elif type_ in ("error", "session.error"):
        etat["erreur"] = str(donnees.get("message") or brut.get("message") or "erreur copilot")
    elif type_ == "result":
        etat["conclu"] = True
        code = brut.get("exitCode", donnees.get("exitCode", 0))
        if code not in (0, None):
            return [Evenement("erreur", brut=brut,
                              texte=etat.get("erreur") or f"copilot a échoué (code {code})")]
        # Aucun champ de jetons documenté : pas de mesure plutôt qu'une mesure fausse (INV-ECO-2).
        return [Evenement("fin", texte=etat.get("dernier", ""), brut=brut,
                          mesure={"contexte": None, "cout": None})]
    return []


class HarnaisCopilot:
    nom = "copilot"
    # Pas d'option de consigne système en ligne de commande : le moteur la place en tête du 1er message.
    consigne_native = False
    sait_deriver = False  # aucune option de dérivation documentée
    # Copilot se compacte seul à 95 % de la fenêtre, sans seuil réglable ; `/compact` n'est pas
    # garanti en `-p` : aucun repli commun (le seuil de GoldenBrain ne s'applique pas à Copilot).
    compactage_natif = False
    ordre_compactage = ""
    compactage: tuple[float, int] | None = None
    analyser = staticmethod(analyser)

    def __init__(self, conf: dict | None = None):
        conf = conf or {}
        self.commande = conf.get("commande", "copilot")
        self.dossier = conf.get("dossier") or str(Path.home())
        self.arguments = list(conf.get("arguments", PERMISSIONS))
        # « argument » : `-p <texte>` (certain, limité à ~32 000 caractères sous Windows) ;
        # « stdin » : texte lu sur l'entrée standard (documenté, mais ignoré par Copilot si `-p` est présent).
        self.prompt = conf.get("prompt", "argument")
        self.maison = Path(conf.get("transcripts") or Path(os.environ.get("COPILOT_HOME")
                                                           or Path.home() / ".copilot") / "session-state")
        self._p = Processus()

    def _argv(self, session: str, neuve: bool, modele: str, message: str) -> list[str]:
        argv = [*resoudre(self.commande), "--output-format=json", *self.arguments]
        argv.append(f"--session-id={session}" if neuve else f"--resume={session}")
        if modele:
            argv.append(f"--model={modele}")
        if self.prompt != "stdin":
            argv += ["-p", message]
        return argv

    async def lancer(self, message: str, *, session: str | None, deriver: bool,
                     consigne: str, env: dict[str, str], modele: str = "") -> AsyncIterator[Evenement]:
        if deriver:
            raise NotImplementedError("copilot ne sait pas dériver une conversation")
        etat: dict = {}
        sid = session or str(uuid.uuid4())
        argv = self._argv(sid, session is None, modele, message)  # introuvable : rien n'est lancé
        if session is None:
            yield Evenement("session", session=sid)
        async with aclosing(self._p.lignes(argv, message if self.prompt == "stdin" else "",
                                           self.dossier, env)) as flux:
            async for brut in flux:
                for ev in analyser(brut, etat):
                    if ev.type == "fin":
                        ev.session = sid
                    yield ev
        if etat.get("conclu"):
            return
        # Pas d'événement de fin reconnu : la fin propre est la sortie en code 0.
        if self._p.code == 0:
            yield Evenement("fin", session=sid, texte=etat.get("dernier", ""),
                            mesure={"contexte": None, "cout": None})
        else:
            yield Evenement("erreur", texte=etat.get("erreur") or self._p.fin_anormale())

    async def arreter(self) -> None:
        await self._p.arreter()

    def transcript(self, session: str, limite: int) -> list[Message]:
        raise NotImplementedError

    def chemin_transcript(self, session: str) -> str:
        fichier = self.maison / session / "events.jsonl"
        return str(fichier) if fichier.is_file() else ""

    def commande_terminal(self, session: str) -> str:
        return f"{self.commande} --resume={session}"
