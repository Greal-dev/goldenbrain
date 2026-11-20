"""Adaptateur Codex CLI : un tour en `codex exec --json`, reprise par `codex exec resume <id>`.

Rôle : traduire le flux JSONL de `codex exec` en `Evenement` (formats observés en réel le 13/11
sur codex-cli 0.167.0, extraits dans `tests/donnees/codex-*.jsonl`).
Frontières : n'écrit pas dans le vault ; une instance par tour ; pas de transcript lisible
(la route `/conversation` se rabat sur les journaux).
Invariants portés : aucun en propre (INV-EXEC-3 repose sur l'événement `session` émis tôt).
"""

from __future__ import annotations

from contextlib import aclosing
from pathlib import Path
from typing import AsyncIterator

from . import Evenement, Message, distant as _distant, suivi as _suivi
from .processus import Processus, resoudre

NON_OUTILS = ("agent_message", "reasoning", "error")


def _resume_item(item: dict) -> str:
    detail = next((str(item[k]) for k in ("command", "tool", "query", "path")
                   if isinstance(item.get(k), str)), "")
    detail = " ".join(detail.split())
    return f"{item.get('type', '?')}: {detail[:160]}" if detail else str(item.get("type", "?"))


def analyser(brut: dict, etat: dict) -> list[Evenement]:
    """Une ligne JSON de `codex exec --json` -> événements ; `etat` porte le fil du tour."""
    type_, item = brut.get("type"), brut.get("item") or {}
    if type_ == "thread.started" and brut.get("thread_id"):
        etat["session"] = str(brut["thread_id"])
        return [Evenement("session", session=etat["session"], brut=brut)]
    if type_ in ("item.started", "item.updated", "item.completed") and isinstance(item, dict) \
            and item.get("type") == "todo_list":
        return _suivi.codex(item)  # INV-TRAVAUX-1 : avancement de la liste d'étapes
    if type_ in ("item.started", "item.completed") and isinstance(item, dict):
        if item.get("type") == "agent_message":
            if type_ == "item.completed" and str(item.get("text") or "").strip():
                etat["dernier"] = str(item["text"])
                return [Evenement("texte", texte=etat["dernier"], brut=brut)]
        elif item.get("type") not in NON_OUTILS and item.get("id") not in etat.setdefault("vus", set()):
            # Un item `error` est un avertissement (ex. modèle d'une autre session) : pas d'échec.
            etat["vus"].add(item.get("id"))
            return [Evenement("outil", texte=_resume_item(item), brut=brut)]
    elif type_ == "error":
        etat["erreur"] = str(brut.get("message") or "erreur codex")
    elif type_ == "turn.failed":
        etat["conclu"] = True
        message = (brut.get("error") or {}).get("message") if isinstance(brut.get("error"), dict) \
            else None
        return [Evenement("erreur", texte=str(message or etat.get("erreur") or "tour en échec"),
                          brut=brut)]
    elif type_ == "turn.completed":
        etat["conclu"] = True
        u = brut.get("usage") if isinstance(brut.get("usage"), dict) else {}
        # `input_tokens` cumule les appels du tour : approximation haute du contexte final.
        return [Evenement("fin", session=etat.get("session", ""), texte=etat.get("dernier", ""),
                          brut=brut, mesure={"contexte": u.get("input_tokens") or None, "cout": None})]
    return []


class HarnaisCodex:
    nom = "codex"
    # Aucune option sûre pour une consigne système : le moteur la place en tête du 1er message.
    consigne_native = False
    sait_deriver = True  # `codex exec fork <id>` (essai réel du 13/11)
    compactage_natif = True  # -c model_auto_compact_token_limit=<jetons> (présent dans codex 0.167.0)
    ordre_compactage = "/compact"
    analyser = staticmethod(analyser)

    def __init__(self, conf: dict | None = None):
        conf = conf or {}
        self.commande = conf.get("commande", "codex")
        self.dossier = conf.get("dossier") or str(Path.home())
        self.arguments = list(conf.get("arguments", []))
        self.transcripts = Path(conf.get("transcripts") or Path.home() / ".codex" / "sessions")
        self._p = Processus()
        self.compactage: tuple[float, int] | None = None  # posé par le moteur (INV-COMPACT-1)
        self.distant: dict | None = conf.get("distant")  # INV-CODESPACE-1

    def _argv(self, session: str | None, deriver: bool, modele: str) -> list[str]:
        argv = [*([self.commande] if self.distant else resoudre(self.commande)), "exec"]
        if session:
            argv.append("fork" if deriver else "resume")
        argv += ["--json", *self.arguments]
        if self.compactage:
            argv += ["-c", f"model_auto_compact_token_limit={int(self.compactage[1])}"]
        if modele:
            # `modèle@effort` (ex. gpt-6-astra@high) : l'effort de réflexion se règle par tâche,
            # sans toucher au défaut de ~/.codex/config.toml.
            nom, _, effort = modele.partition("@")
            argv += (["-m", nom] if nom else []) + (
                ["-c", f'model_reasoning_effort="{effort}"'] if effort else [])
        if session:
            argv.append(session)
        return argv + ["-"]  # `-` : prompt lu sur stdin

    async def lancer(self, message: str, *, session: str | None, deriver: bool,
                     consigne: str, env: dict[str, str], modele: str = "") -> AsyncIterator[Evenement]:
        etat: dict = {}
        argv = await _distant.envelopper(self._argv(session, deriver, modele), self.distant, env)
        async with aclosing(self._p.lignes(argv, message,
                                           self.dossier, env)) as flux:
            async for brut in flux:
                for ev in analyser(brut, etat):
                    if ev.type == "erreur":
                        ev.texte = _distant.indice(ev.texte, self.distant)
                    yield ev
        if not etat.get("conclu"):
            yield Evenement("erreur", texte=etat.get("erreur") or self._p.fin_anormale())

    async def arreter(self) -> None:
        await self._p.arreter()

    def transcript(self, session: str, limite: int) -> list[Message]:
        raise NotImplementedError

    def chemin_transcript(self, session: str) -> str:
        if self.distant:
            return ""
        fichier = next(self.transcripts.glob(f"*/*/*/rollout-*-{session}.jsonl"), None)
        return str(fichier) if fichier else ""

    def commande_terminal(self, session: str) -> str:
        commande = " ".join([self.commande, "resume", session])
        return _distant.commande_terminal(commande, self.distant) if self.distant else commande
