"""Adaptateur GitHub Copilot CLI (faux exécutable Python, jamais le vrai CLI) : argv, reprise, modèle,
prompt, arrêt, absence. Le schéma JSONL réel n'est pas vérifié (pas de compte Copilot sur le poste)."""

import asyncio
import json
import sys
import time

import pytest

from orchestrateur.harnais import HARNAIS, copilot
from orchestrateur.harnais.copilot import HarnaisCopilot, analyser

FAUX_COPILOT = r'''
import json, os, sys, time
def emettre(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
if os.environ.get("FAUX_DORMIR"):
    emettre({"type": "tool.execution_start", "data": {"toolName": "bash"}}); time.sleep(60)
if os.environ.get("FAUX_ERREUR"):
    emettre({"type": "error", "data": {"message": "quota épuisé"}})
    sys.exit(1)
stdin = sys.stdin.read()
rendu = json.dumps({"argv": sys.argv[1:], "stdin": stdin})
emettre({"type": "tool.execution_start", "data": {"toolName": "bash", "arguments": {"command": "echo  salut"}}})
emettre({"type": "assistant.message", "data": {"content": rendu}})
if not os.environ.get("FAUX_SANS_RESULTAT"):
    emettre({"type": "result", "exitCode": 0})
'''


def faux(tmp_path, monkeypatch, **conf):
    chemin = tmp_path / "faux.py"
    chemin.write_text(FAUX_COPILOT, encoding="utf-8")
    monkeypatch.setattr(copilot, "resoudre", lambda commande: [sys.executable, str(chemin)])
    return HarnaisCopilot({"dossier": str(tmp_path), **conf})


async def collecter(h, message="bonjour « été »", env=None, **kw):
    kw.setdefault("session", None)
    kw.setdefault("deriver", False)
    return [ev async for ev in h.lancer(message, consigne="CONSIGNE", env=env or {}, **kw)]


def rendu(evs) -> dict:
    return json.loads(next(e.texte for e in reversed(evs) if e.type == "texte"))


def test_registre_et_attributs():
    assert HARNAIS["copilot"] is HarnaisCopilot
    assert not HarnaisCopilot.consigne_native and not HarnaisCopilot.sait_deriver
    assert not HarnaisCopilot.compactage_natif and HarnaisCopilot.ordre_compactage == ""


def test_premier_tour_session_choisie_droits_et_prompt(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    evs = asyncio.run(collecter(h))
    assert [e.type for e in evs] == ["session", "outil", "texte", "fin"]
    sid = evs[0].session
    assert evs[1].texte == "bash: echo salut" and evs[-1].session == sid
    r = rendu(evs)
    assert r["argv"] == ["--output-format=json", "--allow-all-tools", "--no-ask-user",
                         f"--session-id={sid}", "-p", "bonjour « été »"]
    assert r["stdin"] == ""


def test_reprise_modele_et_droits_reglables(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, arguments=["--allow-tool=write"])
    evs = asyncio.run(collecter(h, session="abc", modele="claude-sonnet-5.5"))
    assert evs[0].type == "outil"  # session déjà connue : aucun événement `session`
    assert rendu(evs)["argv"] == ["--output-format=json", "--allow-tool=write", "--resume=abc",
                                  "--model=claude-sonnet-5.5", "-p", "bonjour « été »"]
    assert evs[-1].session == "abc"


def test_prompt_par_stdin_a_la_demande(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch, prompt="stdin")
    r = rendu(asyncio.run(collecter(h)))
    assert "-p" not in r["argv"] and r["stdin"] == "bonjour « été »"


def test_fin_sur_code_de_sortie_sans_evenement_result(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    evs = asyncio.run(collecter(h, env={"FAUX_SANS_RESULTAT": "1"}))
    assert evs[-1].type == "fin" and json.loads(evs[-1].texte)["argv"]


def test_erreur_lisible(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    evs = asyncio.run(collecter(h, env={"FAUX_ERREUR": "1"}))
    assert evs[-1].type == "erreur" and evs[-1].texte == "quota épuisé"


def test_derivation_refusee(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)
    with pytest.raises(NotImplementedError):
        asyncio.run(collecter(h, session="abc", deriver=True))


def test_arret_tue_le_processus(tmp_path, monkeypatch):
    h = faux(tmp_path, monkeypatch)

    async def scenario():
        evs, debut = [], time.monotonic()
        async for ev in h.lancer("x", session=None, deriver=False, consigne="", env={"FAUX_DORMIR": "1"}):
            evs.append(ev)
            if ev.type == "outil":
                await h.arreter()
        return evs, time.monotonic() - debut

    evs, duree = asyncio.run(scenario())
    assert duree < 30 and evs[-1].type == "erreur"


def test_executable_introuvable_rien_n_est_lance():
    h = HarnaisCopilot({"commande": "introuvable-orch-xyz"})
    with pytest.raises(FileNotFoundError):
        asyncio.run(collecter(h))
    assert h._p.proc is None


def test_transcript_terminal_et_journal(tmp_path):
    h = HarnaisCopilot({"transcripts": str(tmp_path)})
    assert h.commande_terminal("abc") == "copilot --resume=abc" and h.chemin_transcript("abc") == ""
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "events.jsonl").write_text("{}", encoding="utf-8")
    assert h.chemin_transcript("abc").endswith("events.jsonl")
    with pytest.raises(NotImplementedError):
        h.transcript("abc", 10)


def test_analyser_resultat_en_echec():
    ev = analyser({"type": "result", "exitCode": 2}, {"erreur": "refusé"})
    assert ev[0].type == "erreur" and ev[0].texte == "refusé"
