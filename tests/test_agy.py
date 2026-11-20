"""Adaptateur Antigravity (`agy`) : faux exécutable Python (jamais le vrai CLI) et extraits réels
du 14/11 (agy 1.4.12, `tests/donnees/agy-*.jsonl`)."""

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from orchestrateur.harnais import HARNAIS, agy
from orchestrateur.harnais.agy import HarnaisAgy

DONNEES = Path(__file__).parent / "donnees"

FAUX_AGY = r'''
import json, os, sys, time
argv = sys.argv[1:]
if argv[:1] == ["models"]:
    print("Fetching available models...")
    print("gemini-3.8-flash-low\tGemini 3.8 Flash (Low)")
    print("claude-sonnet-5-5-medium\tClaude Sonnet 5.5 (Medium)")
    sys.exit(0)
entree = json.loads(sys.stdin.buffer.read().decode("utf-8").splitlines()[0])
sid = argv[argv.index("--conversation") + 1] if "--conversation" in argv else "conv-1"
def emettre(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
emettre({"event": "init", "conversation_id": sid, "init": {"model": "m"}})
if os.environ.get("FAUX_DORMIR"):
    time.sleep(60)
if os.environ.get("FAUX_ERREUR"):
    emettre({"event": "result", "result": {"conversation_id": sid, "status": "ERROR",
             "response": "", "error": "quota épuisé"}})
    sys.exit(1)
emettre({"event": "step_update", "step_update": {"step_index": 1, "state": "ACTIVE",
         "step_type": "tool", "tool_name": "run_command",
         "tool_info": {"name": "run_command", "parameters": {"CommandLine": "echo   salut"}}}})
texte = json.dumps({"entree": entree, "argv": argv})
emettre({"event": "step_update", "step_update": {"step_index": 2, "state": "ACTIVE",
         "step_type": "agent_response", "text_delta": texte[:10]}})
emettre({"event": "step_update", "step_update": {"step_index": 2, "state": "DONE",
         "step_type": "agent_response", "text_delta": texte[10:]}})
emettre({"event": "result", "result": {"conversation_id": sid, "status": "SUCCESS", "response": texte}})
'''


def faux(tmp_path, monkeypatch, **conf):
    chemin = tmp_path / "faux_agy.py"
    chemin.write_text(FAUX_AGY, encoding="utf-8")
    monkeypatch.setattr(agy, "resoudre", lambda commande: [sys.executable, str(chemin)])
    return HarnaisAgy({"dossier": str(tmp_path), **conf})


async def collecter(h, message="bonjour « été »\nligne 2", env=None, **kw):
    kw.setdefault("session", None)
    kw.setdefault("deriver", False)
    return [ev async for ev in h.lancer(message, consigne="CONSIGNE", env=env or {}, **kw)]


def test_registre_et_attributs():
    assert HARNAIS["agy"] is HarnaisAgy
    assert not HarnaisAgy.consigne_native and not HarnaisAgy.sait_deriver


def test_premier_tour_message_multiligne_par_stdin_en_ndjson(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, arguments=["--dangerously-skip-permissions"])
    evs = asyncio.run(collecter(h))
    assert [e.type for e in evs] == ["session", "outil", "texte", "texte", "fin"]
    assert evs[0].session == "conv-1" and evs[1].texte == "run_command: echo salut"
    rendu = json.loads(evs[-1].texte)
    assert rendu["entree"] == {"event": "user", "message": {"content": "bonjour « été »\nligne 2"}}
    assert rendu["argv"] == ["--input-format", "stream-json", "--output-format", "stream-json",
                             "--dangerously-skip-permissions"]
    assert evs[-1].session == "conv-1"


def test_reprise_et_modele(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    evs = asyncio.run(collecter(h, session="conv-7", modele="gemini-3.8-flash-low"))
    assert json.loads(evs[-1].texte)["argv"][-4:] == [
        "--conversation", "conv-7", "--model", "gemini-3.8-flash-low"]
    assert evs[0].session == "conv-7"


def test_erreur_du_resultat(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    evs = asyncio.run(collecter(h, env={"FAUX_ERREUR": "1"}))
    assert [e.type for e in evs] == ["session", "erreur"] and evs[-1].texte == "quota épuisé"


def test_arret_tue_le_processus(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)

    async def scenario():
        evs, debut = [], time.monotonic()
        async for ev in h.lancer("x", session=None, deriver=False, consigne="", env={"FAUX_DORMIR": "1"}):
            evs.append(ev)
            if ev.type == "session":
                await h.arreter()
        return evs, time.monotonic() - debut

    evs, duree = asyncio.run(scenario())
    assert duree < 30 and evs[-1].type == "erreur"


def test_executable_introuvable_rien_n_est_lance():
    h = HarnaisAgy({"commande": "introuvable-orch-xyz"})
    with pytest.raises(FileNotFoundError):
        asyncio.run(collecter(h))


def test_decouverte_des_modeles_transcript_et_terminal(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    assert h.decouvrir_modeles() == ["gemini-3.8-flash-low", "claude-sonnet-5-5-medium"]
    with pytest.raises(NotImplementedError):
        h.transcript("x", 10)
    assert h.commande_terminal("c-1") == "agy --conversation c-1"


def rejouer(fichier: str):
    etat: dict = {}
    lignes = (DONNEES / fichier).read_text("utf-8").splitlines()
    return [ev for ligne in lignes for ev in agy.analyser(json.loads(ligne), etat)]


def test_extraits_reels():
    evs = rejouer("agy-premier.jsonl")
    assert [(e.type, e.texte) for e in evs] == [
        ("session", ""), ("texte", "bonjour"), ("texte", "bonjour\n"), ("fin", "bonjour")]
    assert evs[0].session == evs[-1].session == "00000000-0000-4000-8000-000000000002"
    evs = rejouer("agy-reprise-outil.jsonl")
    assert [e.type for e in evs] == ["outil", "outil", "texte", "texte", "fin"]
    assert evs[0].texte.startswith("run_command: Get-ChildItem") and evs[-1].texte == "10"
    evs = rejouer("agy-erreur.jsonl")
    assert [e.type for e in evs] == ["session", "erreur"]
    assert "failed to decode stream input" in evs[-1].texte
