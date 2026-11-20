"""Adaptateur Antigravity (`agy`) : un tour en `agy --output-format stream-json`, reprise par `--conversation`.

Rôle : traduire le flux NDJSON d'`agy` en `Evenement` (formats observés en réel le 14/11 sur agy 1.4.12,
extraits anonymisés dans `tests/donnees/agy-*.jsonl`) ; découvrir les modèles (`agy models`).
Frontières : n'écrit pas dans le vault ; une instance par tour ; pas de transcript lisible (la route
`/conversation` se rabat sur les journaux) ; pas de dérivation (aucune option de fork).
Invariants portés : aucun en propre (INV-EXEC-3 repose sur l'événement `session` émis dès `init`).
"""

from __future__ import annotations

import json
import subprocess
from contextlib import aclosing
from pathlib import Path
from typing import AsyncIterator

from . import Evenement, Message
from .processus import Processus, resoudre


def _resume_outil(info: dict) -> str:
    nom = str(info.get("name") or "?")
    parametres = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
    detail = next((str(v) for v in parametres.values() if isinstance(v, (str, int))), "")
    detail = " ".join(detail.split())
    return f"{nom}: {detail[:160]}" if detail else nom


def analyser(brut: dict, etat: dict) -> list[Evenement]:
    """Une ligne d'`agy --output-format stream-json` -> événements ; `etat` porte le fil du tour."""
    out: list[Evenement] = []
    type_ = brut.get("event")
    if type_ == "init":
        sid = str(brut.get("conversation_id") or "")
        if sid and sid != etat.get("session"):
            etat["session"] = sid
            out.append(Evenement("session", session=sid, brut=brut))
    elif type_ == "step_update":
        pas = brut.get("step_update") if isinstance(brut.get("step_update"), dict) else {}
        if isinstance(u := pas.get("usage"), dict):  # dernier appel : le contexte courant
            etat["contexte"] = (int(u.get("input_tokens") or 0) + int(u.get("cache_read_tokens") or 0)) or None
        if pas.get("step_type") == "agent_response" and pas.get("text_delta"):
            # Le texte arrive par morceaux (ACTIVE puis DONE) : on le cumule.
            etat["texte"] = etat.get("texte", "") + str(pas["text_delta"])
            if etat["texte"].strip():
                out.append(Evenement("texte", texte=etat["texte"], brut=brut))
        elif pas.get("step_type") == "tool" and pas.get("state") == "ACTIVE":
            info = pas.get("tool_info") if isinstance(pas.get("tool_info"), dict) else {}
            out.append(Evenement("outil", texte=_resume_outil(info), brut=brut))
            etat["texte"] = ""  # un nouveau message de l'agent suit l'outil
    elif type_ == "result":
        res = brut.get("result") if isinstance(brut.get("result"), dict) else {}
        etat["conclu"] = True
        if res.get("status") == "SUCCESS":
            out.append(Evenement("fin", session=str(res.get("conversation_id") or ""),
                                 texte=str(res.get("response") or etat.get("texte", "")).strip(),
                                 brut=brut, mesure={"contexte": etat.get("contexte"), "cout": None}))
        else:
            out.append(Evenement("erreur", brut=brut, texte=str(
                res.get("error") or f"agy : statut {res.get('status')}")))
    return out


class HarnaisAgy:
    nom = "agy"
    # Pas d'option de consigne système en mode impression : le moteur la place en tête du 1er message.
    consigne_native = False
    sait_deriver = False  # aucune option de fork dans `agy`
    compactage_natif = False  # aucune option de compactage dans `agy` : repli commun
    ordre_compactage = ""     # aucun ordre connu : pas de repli tant qu'il n'est pas réglé (config)
    compactage: tuple[float, int] | None = None
    analyser = staticmethod(analyser)

    def __init__(self, conf: dict | None = None):
        conf = conf or {}
        self.commande = conf.get("commande", "agy")
        self.dossier = conf.get("dossier") or str(Path.home())
        self.arguments = list(conf.get("arguments", []))
        self._p = Processus()

    def _argv(self, session: str | None, modele: str) -> list[str]:
        argv = [*resoudre(self.commande), "--input-format", "stream-json",
                "--output-format", "stream-json", *self.arguments]
        if session:
            argv += ["--conversation", session]
        if modele:
            argv += ["--model", modele]
        return argv

    @staticmethod
    def _entree(message: str) -> str:
        # Message par stdin en NDJSON (format observé le 14/11) : `-p` veut le prompt en argument,
        # ce que la ligne de commande Windows ne tient pas pour un texte long ou multiligne.
        return json.dumps({"event": "user", "message": {"content": message}},
                          ensure_ascii=False) + "\n"

    async def lancer(self, message: str, *, session: str | None, deriver: bool,
                     consigne: str, env: dict[str, str], modele: str = "") -> AsyncIterator[Evenement]:
        etat: dict = {}
        async with aclosing(self._p.lignes(self._argv(session, modele), self._entree(message),
                                           self.dossier, env)) as flux:
            async for brut in flux:
                for ev in analyser(brut, etat):
                    yield ev
        if etat.get("conclu"):
            return
        yield Evenement("erreur", texte=self._p.fin_anormale())

    async def arreter(self) -> None:
        await self._p.arreter()

    def transcript(self, session: str, limite: int) -> list[Message]:
        raise NotImplementedError

    def decouvrir_modeles(self) -> list[str]:
        """`agy models` : « identifiant<TAB>libellé » par ligne (appel bloquant)."""
        sortie = subprocess.run([*resoudre(self.commande), "models"], cwd=self.dossier,
                                capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        lignes = sortie.stdout.decode("utf-8", "replace").splitlines()
        return [ligne.split("\t")[0].strip() for ligne in lignes if "\t" in ligne]

    def commande_terminal(self, session: str) -> str:
        return " ".join([self.commande, "--conversation", session])
