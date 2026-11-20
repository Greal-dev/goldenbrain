"""Adaptateurs codex et opencode (faux exécutables Python, jamais les vrais CLI), Claude --model,
analyse des flux réels enregistrés le 13/11 (`tests/donnees/`)."""

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from orchestrateur.harnais import HARNAIS, codex, opencode
from orchestrateur.harnais.claude import HarnaisClaude
from orchestrateur.harnais.codex import HarnaisCodex
from orchestrateur.harnais.opencode import HarnaisOpencode
from orchestrateur.harnais.processus import resoudre

DONNEES = Path(__file__).parent / "donnees"

FAUX_CODEX = r'''
import json, os, sys, time
argv = sys.argv[1:]
prompt = sys.stdin.buffer.read().decode("utf-8")
def emettre(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
emettre({"type": "thread.started", "thread_id": "th-2" if "fork" in argv else "th-1"})
if os.environ.get("FAUX_DORMIR"):
    time.sleep(60)
emettre({"type": "turn.started"})
if os.environ.get("FAUX_ERREUR"):
    emettre({"type": "error", "message": "modèle refusé"})
    emettre({"type": "turn.failed", "error": {"message": "modèle refusé"}})
    sys.exit(1)
item = {"id": "item_1", "type": "command_execution", "command": "echo   salut"}
emettre({"type": "item.started", "item": item})
emettre({"type": "item.completed", "item": item})
emettre({"type": "item.completed", "item": {"id": "item_2", "type": "agent_message",
         "text": "y" * 200000}})
# Prompt long (consigne + ligne de langue, INV-LANGUE-1) abrégé : la situation de la fiche est bornée.
court = prompt if len(prompt) < 200 else prompt[:40] + "…" + prompt[-40:]
emettre({"type": "item.completed", "item": {"id": "item_3", "type": "agent_message",
         "text": json.dumps({"prompt": court, "argv": argv})}})
emettre({"type": "turn.completed", "usage": {}})
'''

FAUX_OPENCODE = r'''
import json, os, sys, time
argv = sys.argv[1:]
prompt = sys.stdin.buffer.read().decode("utf-8")
sid = "ses_fourche" if "--fork" in argv else "ses_1"
def emettre(o):
    o["sessionID"] = sid
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
emettre({"type": "step_start", "part": {"type": "step-start"}})
if os.environ.get("FAUX_DORMIR"):
    time.sleep(60)
if os.environ.get("FAUX_ERREUR"):
    emettre({"type": "error", "error": {"name": "APIError", "data": {"message": "refusé"}}})
    sys.exit(1)
emettre({"type": "tool_use", "part": {"type": "tool", "tool": "bash",
         "state": {"input": {"command": "echo salut"}}}})
emettre({"type": "text", "part": {"type": "text", "text": json.dumps({"prompt": prompt, "argv": argv})}})
emettre({"type": "step_finish", "part": {"reason": "stop"}})
'''


def faux(tmp_path, monkeypatch, module, script, classe, **conf):
    chemin = tmp_path / "faux.py"
    chemin.write_text(script, encoding="utf-8")
    monkeypatch.setattr(module, "resoudre", lambda commande: [sys.executable, str(chemin)])
    return classe({"dossier": str(tmp_path), **conf})


async def collecter(h, message="bonjour « été »", env=None, **kw):
    kw.setdefault("session", None)
    kw.setdefault("deriver", False)
    return [ev async for ev in h.lancer(message, consigne="CONSIGNE", env=env or {}, **kw)]


def rendu(evs) -> dict:
    return json.loads(next(e.texte for e in reversed(evs) if e.type == "texte"))


def test_registre_et_attributs():
    assert HARNAIS["codex"] is HarnaisCodex and HARNAIS["opencode"] is HarnaisOpencode
    assert HarnaisClaude.consigne_native and HarnaisClaude.sait_deriver
    assert not HarnaisCodex.consigne_native and not HarnaisOpencode.consigne_native
    assert HarnaisCodex.sait_deriver and HarnaisOpencode.sait_deriver


# --- codex -------------------------------------------------------------------------------
def test_codex_premier_tour_prompt_par_stdin_sans_consigne_en_argument(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, codex, FAUX_CODEX, HarnaisCodex,
             arguments=["--skip-git-repo-check"])
    evs = asyncio.run(collecter(h))
    assert [e.type for e in evs] == ["session", "outil", "texte", "texte", "fin"]
    assert evs[0].session == "th-1" and evs[1].texte == "command_execution: echo salut"
    assert len(evs[2].texte) == 200000  # ligne de plus de 64 Ko
    r = rendu(evs)
    assert r["prompt"] == "bonjour « été »"
    assert r["argv"] == ["exec", "--json", "--skip-git-repo-check", "-"]
    assert evs[-1].session == "th-1" and json.loads(evs[-1].texte) == r


def test_codex_reprise_modele_et_derivation(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, codex, FAUX_CODEX, HarnaisCodex)
    argv = rendu(asyncio.run(collecter(h, session="th-1", modele="gpt-6")))["argv"]
    assert argv == ["exec", "resume", "--json", "-m", "gpt-6", "th-1", "-"]
    evs = asyncio.run(collecter(h, session="th-1", deriver=True))
    assert rendu(evs)["argv"] == ["exec", "fork", "--json", "th-1", "-"]
    assert evs[0].session == "th-2"


def test_codex_effort_de_reflexion_par_tache(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, codex, FAUX_CODEX, HarnaisCodex)
    argv = rendu(asyncio.run(collecter(h, modele="gpt-6-astra@high")))["argv"]
    assert argv[argv.index("-m") + 1] == "gpt-6-astra"
    assert argv[argv.index("-c") + 1] == 'model_reasoning_effort="high"'
    argv = rendu(asyncio.run(collecter(h, modele="@low")))["argv"]
    assert "-m" not in argv and 'model_reasoning_effort="low"' in argv


def test_codex_erreur(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, codex, FAUX_CODEX, HarnaisCodex)
    evs = asyncio.run(collecter(h, env={"FAUX_ERREUR": "1"}))
    assert [e.type for e in evs] == ["session", "erreur"] and evs[-1].texte == "modèle refusé"


@pytest.mark.parametrize("module,script,classe", [
    (codex, FAUX_CODEX, HarnaisCodex), (opencode, FAUX_OPENCODE, HarnaisOpencode)])
def test_arret_tue_le_processus(tmp_path, monkeypatch, module, script, classe):
    h = faux(tmp_path, monkeypatch, module, script, classe)

    async def scenario():
        evs, debut = [], time.monotonic()
        async for ev in h.lancer("x", session=None, deriver=False, consigne="", env={"FAUX_DORMIR": "1"}):
            evs.append(ev)
            if ev.type == "session":
                await h.arreter()
        return evs, time.monotonic() - debut

    evs, duree = asyncio.run(scenario())
    assert duree < 30 and evs[-1].type == "erreur"


@pytest.mark.parametrize("classe", [HarnaisCodex, HarnaisOpencode])
def test_executable_introuvable_rien_n_est_lance(classe):
    h = classe({"commande": "introuvable-orch-xyz"})
    with pytest.raises(FileNotFoundError):
        asyncio.run(collecter(h))
    assert h._p.proc is None


def test_codex_transcript_absent_et_terminal(tmp_path):
    h = HarnaisCodex({"commande": "codex", "transcripts": str(tmp_path)})
    with pytest.raises(NotImplementedError):
        h.transcript("x", 10)
    f = tmp_path / "2026" / "11" / "13" / "rollout-2026-11-13T11-43-03-th-1.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    assert h.chemin_transcript("th-1") == str(f) and h.chemin_transcript("autre") == ""
    assert h.commande_terminal("th-1") == "codex resume th-1"


# --- opencode ----------------------------------------------------------------------------
def test_opencode_premier_tour_reprise_modele_derivation(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, opencode, FAUX_OPENCODE, HarnaisOpencode, arguments=["--auto"])
    evs = asyncio.run(collecter(h))
    assert [e.type for e in evs] == ["session", "outil", "texte", "fin"]
    assert evs[1].texte == "bash: echo salut" and evs[-1].session == "ses_1"
    r = rendu(evs)
    assert r["prompt"] == "bonjour « été »" and r["argv"] == ["run", "--format", "json", "--auto"]
    argv = rendu(asyncio.run(collecter(h, session="ses_1", modele="openai/gpt-6")))["argv"]
    assert argv[-4:] == ["-s", "ses_1", "-m", "openai/gpt-6"]
    evs = asyncio.run(collecter(h, session="ses_1", deriver=True))
    assert rendu(evs)["argv"][-3:] == ["-s", "ses_1", "--fork"] and evs[0].session == "ses_fourche"


def test_opencode_erreur(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, opencode, FAUX_OPENCODE, HarnaisOpencode)
    evs = asyncio.run(collecter(h, env={"FAUX_ERREUR": "1"}))
    assert [e.type for e in evs] == ["session", "erreur"] and evs[-1].texte == "refusé"


def test_opencode_decouverte_des_modeles(tmp_path, monkeypatch):
    script = tmp_path / "modeles.py"
    script.write_text('print("opencode/big-pickle\\nopenai/gpt-6\\n\\nINFO bruit")', encoding="utf-8")
    monkeypatch.setattr(opencode, "resoudre", lambda c: [sys.executable, str(script)])
    assert HarnaisOpencode({"dossier": str(tmp_path)}).decouvrir_modeles() == [
        "opencode/big-pickle", "openai/gpt-6"]


# --- flux réels enregistrés --------------------------------------------------------------
def rejouer(analyser, fichier: str):
    etat: dict = {}
    lignes = (DONNEES / fichier).read_text("utf-8").splitlines()
    return [ev for ligne in lignes for ev in analyser(json.loads(ligne), etat)], etat


def test_extraits_reels_codex():
    evs, _ = rejouer(codex.analyser, "codex-premier.jsonl")
    assert [(e.type, e.texte) for e in evs][1:] == [("texte", "ok"), ("fin", "ok")]
    assert evs[0].session == evs[-1].session == "00000000-0000-4000-8000-000000000005"
    # L'item `error` (modèle d'une autre session) n'est qu'un avertissement.
    evs, _ = rejouer(codex.analyser, "codex-reprise-modele.jsonl")
    assert [e.type for e in evs] == ["session", "texte", "fin"]
    evs, _ = rejouer(codex.analyser, "codex-derive-outil.jsonl")
    assert [e.type for e in evs] == ["session", "texte", "outil", "texte", "fin"]
    assert evs[0].session == "00000000-0000-4000-8000-000000000003"
    assert evs[2].texte.startswith("command_execution:") and "echo salut" in evs[2].texte
    evs, etat = rejouer(codex.analyser, "codex-erreur.jsonl")
    assert evs[-1].type == "erreur" and "not supported" in evs[-1].texte and etat["conclu"]


def test_extraits_reels_opencode():
    evs, etat = rejouer(opencode.analyser, "opencode-outil.jsonl")
    assert [e.type for e in evs] == ["session", "outil", "texte"]
    assert evs[1].texte == "bash: echo salut" and etat["dernier"] == "ok"
    assert not etat.get("conclu")  # la fin vient du code de sortie
    evs, _ = rejouer(opencode.analyser, "opencode-reprise.jsonl")
    assert evs[0].session == "ses_essai00000000000000000008"
    evs, _ = rejouer(opencode.analyser, "opencode-derive.jsonl")
    assert evs[0].session == "ses_essai00000000000000000006" and evs[-1].texte == "fourche"
    evs, etat = rejouer(opencode.analyser, "opencode-erreur.jsonl")
    assert [e.type for e in evs] == ["session", "erreur"] and "not supported" in evs[1].texte


# --- résolution d'un lanceur npm ---------------------------------------------------------
def test_resoudre_lanceur_cmd_vise_le_vrai_point_d_entree(tmp_path):
    if sys.platform != "win32":
        pytest.skip("lanceurs .cmd : Windows")
    (tmp_path / "oc.cmd").write_text(
        '@ECHO off\r\n"%dp0%\\node_modules\\oc\\bin\\oc.exe"   %*\r\n', encoding="utf-8")
    assert resoudre(str(tmp_path / "oc.cmd")) == [str(tmp_path / "node_modules/oc/bin/oc.exe")]
    (tmp_path / "node.exe").write_bytes(b"")
    (tmp_path / "cx.cmd").write_text(
        'IF EXIST "%dp0%\\node.exe" (\r\n) & "%_prog%"  "%dp0%\\node_modules\\cx\\bin\\cx.js" %*\r\n',
        encoding="utf-8")
    assert resoudre(str(tmp_path / "cx.cmd")) == [str(tmp_path / "node.exe"),
                                                  str(tmp_path / "node_modules/cx/bin/cx.js")]


# --- Claude : modèle ---------------------------------------------------------------------
def test_claude_avec_et_sans_modele():
    h = HarnaisClaude({"commande": sys.executable})
    assert "--model" not in h._argv(None, False, "")
    argv = h._argv("abc", False, "", "opus")
    assert argv[argv.index("--model") + 1] == "opus"
