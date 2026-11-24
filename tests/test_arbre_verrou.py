"""Arrêt de l'arbre de processus (POSIX) et verrou d'exemplaire unique de check_ui."""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verrou  # noqa: E402

from orchestrateur.harnais.processus import SESSION_PROPRE, Processus  # noqa: E402

PETIT_FILS = r'''
import subprocess, time
p = subprocess.Popen(["sleep", "60"])
print(p.pid, flush=True)
time.sleep(60)
'''


def _vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # zombie : mort, en attente de récolte
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2] != "Z"
    except OSError:
        return True


@pytest.mark.skipif(sys.platform == "win32", reason="killpg : POSIX seulement")
def test_arbre_arret_tue_le_petit_fils():
    async def scenario():
        p = Processus()
        p.proc = proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", PETIT_FILS, stdout=asyncio.subprocess.PIPE, **SESSION_PROPRE)
        petit_fils = int((await asyncio.wait_for(proc.stdout.readline(), 10)).decode())
        assert _vivant(petit_fils)
        await p.arreter()
        await proc.wait()
        for _ in range(50):
            if not _vivant(petit_fils):
                return True
            await asyncio.sleep(0.1)
        os.kill(petit_fils, 9)
        return False
    assert asyncio.run(scenario()), "le petit-fils a survécu à l'arrêt"


def test_verrou_la_seconde_acquisition_echoue():
    nom = f"test-{os.getpid()}-{time.time_ns()}"
    premier = verrou.prendre(nom)
    assert premier is not None
    try:
        assert verrou.prendre(nom) is None
    finally:
        premier.close()
    reprise = verrou.prendre(nom)  # libéré à la fermeture
    assert reprise is not None
    reprise.close()


def test_verrou_check_ui_sort_non_nul_si_un_autre_vit():
    racine = Path(__file__).resolve().parents[1]
    tenu = verrou.prendre("check_ui")
    if tenu is None:
        pytest.skip("un vrai check_ui tourne")
    try:
        # UTF-8 forcé côté fils : sous Windows il écrit dans la page de code locale (illisible en UTF-8).
        r = subprocess.run([sys.executable, "scripts/check_ui.py"], cwd=racine, capture_output=True,
                           text=True, encoding="utf-8", timeout=60,
                           env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    finally:
        tenu.close()
    assert r.returncode != 0 and "autre exemplaire" in r.stdout
