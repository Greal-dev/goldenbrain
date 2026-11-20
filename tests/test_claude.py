"""Adaptateur Claude : flux stream-json (faux exécutable Python, jamais le vrai claude), transcript."""

import asyncio
import json
import sys
import time

from orchestrateur.harnais import HARNAIS
from orchestrateur.harnais.claude import HarnaisClaude

FAUX_CLAUDE = r'''
import json, sys, time
argv = sys.argv[1:]
prompt = sys.stdin.buffer.read().decode("utf-8")
def emettre(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
emettre({"type": "system", "subtype": "init", "session_id": "sess-9"})
if "--dormir" in argv:
    time.sleep(60)
emettre({"type": "assistant", "session_id": "sess-9", "message": {"content": [
    {"type": "text", "text": "x" * 200000},
    {"type": "tool_use", "name": "Bash", "input": {"command": "ls   -la"}}]}})
emettre({"type": "result", "subtype": "success", "is_error": False, "session_id": "sess-9",
         "result": json.dumps({"prompt": prompt, "argv": argv})})
'''


def harnais(tmp_path, *args):
    script = tmp_path / "faux_claude.py"
    script.write_text(FAUX_CLAUDE, encoding="utf-8")
    return HarnaisClaude({"commande": sys.executable, "dossier": str(tmp_path),
                          "arguments": [str(script), *args]})


async def collecter(h, **kw):
    return [ev async for ev in h.lancer("bonjour « été »", env={"ORCH_TACHE": "t"}, **kw)]


def test_registre():
    assert HARNAIS["claude"] is HarnaisClaude


def test_flux_stream_json_et_ligne_de_plus_de_64_ko(tmp_path):
    h = harnais(tmp_path)
    evs = asyncio.run(collecter(h, session="abc", deriver=True, consigne="sois bref"))
    assert [e.type for e in evs] == ["session", "texte", "outil", "fin"]
    assert evs[0].session == "sess-9" and len(evs[1].texte) == 200000
    assert evs[2].texte == "Bash: ls -la"
    rendu = json.loads(evs[3].texte)
    assert rendu["prompt"] == "bonjour « été »"  # prompt passé par stdin
    argv = rendu["argv"]
    assert argv[:4] == ["-p", "--output-format", "stream-json", "--verbose"]
    assert argv[argv.index("--resume") + 1] == "abc" and "--fork-session" in argv
    assert argv[argv.index("--append-system-prompt") + 1] == "sois bref"


def test_nouvelle_session_sans_resume(tmp_path):
    evs = asyncio.run(collecter(harnais(tmp_path), session=None, deriver=False, consigne=""))
    argv = json.loads(evs[-1].texte)["argv"]
    assert "--resume" not in argv and "--fork-session" not in argv
    assert "--append-system-prompt" not in argv


def test_arret_tue_le_processus(tmp_path):
    h = harnais(tmp_path, "--dormir")

    async def scenario():
        evs = []
        debut = time.monotonic()
        async for ev in h.lancer("x", session=None, deriver=False, consigne="", env={}):
            evs.append(ev)
            if ev.type == "session":
                await h.arreter()
        return evs, time.monotonic() - debut

    evs, duree = asyncio.run(scenario())
    assert duree < 30
    assert evs[-1].type == "erreur"


def test_generateur_abandonne_ne_laisse_pas_de_processus_orphelin(tmp_path):
    h = harnais(tmp_path, "--dormir")

    async def scenario():
        flux = h.lancer("x", session=None, deriver=False, consigne="", env={})
        assert (await anext(flux)).type == "session"
        await flux.aclose()  # le moteur abandonne le tour (exception de son côté)
        return await asyncio.wait_for(h._proc.wait(), 30)

    assert asyncio.run(scenario()) is not None


def test_executable_introuvable(tmp_path):
    h = HarnaisClaude({"commande": "introuvable-orch-xyz"})
    try:
        asyncio.run(collecter(h, session=None, deriver=False, consigne=""))
    except FileNotFoundError:
        return
    raise AssertionError("FileNotFoundError attendue")


def test_transcript(tmp_path):
    dossier = tmp_path / "projects" / "C--Users-utilisateur"
    dossier.mkdir(parents=True)
    lignes = [
        {"type": "summary", "summary": "ignoré"},
        {"type": "user", "timestamp": "2026-11-12T10:00:00Z", "message": {"content": "Salut"}},
        {"type": "assistant", "timestamp": "t2", "message": {"content": [
            {"type": "thinking", "thinking": "..."}, {"type": "text", "text": "Je regarde."},
            {"type": "tool_use", "name": "Read", "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Fini."}]}},
    ]
    (dossier / "sess-1.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lignes) + "\nligne cassée\n", encoding="utf-8")
    h = HarnaisClaude({"transcripts": str(tmp_path / "projects")})
    msgs = h.transcript("sess-1", 200)
    assert [(m.role, m.texte, m.outils) for m in msgs] == [
        ("utilisateur", "Salut", []), ("assistant", "Je regarde.", ["Read"]),
        ("assistant", "Fini.", [])]
    assert msgs[0].horodatage == "2026-11-12T10:00:00Z"
    assert [m.texte for m in h.transcript("sess-1", 1)] == ["Fini."]
    assert h.transcript("absente", 10) == []


def test_commande_terminal():
    h = HarnaisClaude({"commande": "claude", "arguments": ["--dangerously-skip-permissions"]})
    assert h.commande_terminal("abc") == "claude --dangerously-skip-permissions --resume abc"


def test_argv_natif_session_neuve_ou_reprise_avec_la_consigne():
    h = HarnaisClaude({"commande": "claude-introuvable", "arguments": ["--dangerously-skip-permissions"]})
    assert h.argv_natif("u-1", True, "consigne", "opus", "bonjour") == [
        "claude-introuvable", "--dangerously-skip-permissions", "--session-id", "u-1",
        "--append-system-prompt", "consigne", "--model", "opus", "bonjour"]
    assert h.argv_natif("u-1", False, "", "", "") == [
        "claude-introuvable", "--dangerously-skip-permissions", "--resume", "u-1"]
