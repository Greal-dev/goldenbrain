"""Suivi structuré d'un tour : sous-agents lancés par l'agent et avancement de sa liste d'étapes.

Rôle : lire, dans le flux brut d'un harnais, les appels qui lancent un sous-agent (Claude Code :
outil `Task`/`Agent` ; OpenCode : outil `task`) et ceux qui tiennent une liste d'étapes
(`TodoWrite`, `todowrite`, item Codex `todo_list`), et les traduire en événements `suivi`.
Frontières : aucune E/S, aucun état hors du dictionnaire `ouverts` fourni par l'adaptateur.
Invariants portés : INV-TRAVAUX-1 (le suivi est lu dans le flux existant, jamais sondé).
"""

from __future__ import annotations

from . import Evenement

SOUS_AGENTS = {"task", "agent"}
LISTES = {"todowrite"}


def _court(texte, n: int = 120) -> str:
    return " ".join(str(texte or "").split())[:n]


def _sous_agent(ident: str, entree: dict, **plus) -> Evenement:
    return Evenement("suivi", suivi={"sous_agent": {
        "id": ident, "description": _court(entree.get("description") or entree.get("prompt")),
        "genre": _court(entree.get("subagent_type") or entree.get("agent"), 40), **plus}})


def avancement(etapes, fait=lambda e: e.get("status") == "completed") -> Evenement | None:
    """Liste d'étapes -> {"fait", "total"} ; None si la liste est vide ou illisible."""
    etapes = [e for e in etapes or [] if isinstance(e, dict)] if isinstance(etapes, list) else []
    if not etapes:
        return None
    return Evenement("suivi", suivi={"avancement": {"fait": sum(1 for e in etapes if fait(e)),
                                                    "total": len(etapes)}})


def claude(brut: dict, ouverts: set) -> list[Evenement]:
    """Ligne `stream-json` de Claude Code -> événements `suivi`. Un message émis à l'intérieur
    d'un sous-agent (`parent_tool_use_id`) ne change pas l'avancement de l'agent principal."""
    message = brut.get("message") if isinstance(brut.get("message"), dict) else {}
    contenu = message.get("content") if isinstance(message.get("content"), list) else []
    blocs = [b for b in contenu if isinstance(b, dict)]
    out: list[Evenement] = []
    if brut.get("type") == "assistant":
        for b in blocs:
            nom, entree = str(b.get("name") or "").lower(), b.get("input") or {}
            if b.get("type") != "tool_use" or not isinstance(entree, dict):
                continue
            if nom in SOUS_AGENTS and b.get("id"):
                ouverts.add(str(b["id"]))
                out.append(_sous_agent(str(b["id"]), entree))
            elif nom in LISTES and not brut.get("parent_tool_use_id"):
                if ev := avancement(entree.get("todos")):
                    out.append(ev)
    elif brut.get("type") == "user":
        for b in blocs:
            ident = str(b.get("tool_use_id") or "")
            if b.get("type") == "tool_result" and ident in ouverts:
                ouverts.discard(ident)
                out.append(Evenement("suivi", suivi={"sous_agent": {
                    "id": ident, "fin": True, "erreur": bool(b.get("is_error"))}}))
    return out


def opencode(part: dict) -> list[Evenement]:
    """Partie `tool_use` d'OpenCode -> événements `suivi` (sous-agent `task`, liste `todowrite`)."""
    etat = part.get("state") if isinstance(part.get("state"), dict) else {}
    entree = etat.get("input") if isinstance(etat.get("input"), dict) else {}
    nom = str(part.get("tool") or "").lower()
    if nom == "task":
        ident = str(part.get("callID") or part.get("id") or "")
        if not ident:
            return []
        fini = etat.get("status") in ("completed", "error")
        out = [_sous_agent(ident, entree)]
        if fini:
            out.append(Evenement("suivi", suivi={"sous_agent": {
                "id": ident, "fin": True, "erreur": etat.get("status") == "error"}}))
        return out
    if nom in LISTES and (ev := avancement(entree.get("todos"))):
        return [ev]
    return []


def codex(item: dict) -> list[Evenement]:
    """Item Codex `todo_list` -> avancement."""
    if item.get("type") != "todo_list":
        return []
    ev = avancement(item.get("items"), fait=lambda e: bool(e.get("completed")))
    return [ev] if ev else []
