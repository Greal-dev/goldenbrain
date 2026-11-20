"""Essai réel de la pause RAM (INV-SIMULT-1) : `python scripts/essai_pause_ram.py [Mo]`.

Rôle : lancer un agent factice (un processus qui garde `Mo` mégaoctets en mémoire et un enfant),
le suspendre par `poste_ram` comme le ferait la veille, mesurer sa mémoire de travail avant, pendant
et après, vérifier qu'il ne progresse plus en pause et reprend ensuite, puis l'arrêter.
Frontières : hors porte ; aucun harnais, aucun vault, aucun port ; Windows seulement.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from orchestrateur import poste_ram  # noqa: E402

AGENT = r"""
import subprocess, sys, time
from pathlib import Path
enfant = subprocess.Popen([sys.executable, "-c", "import time; b = bytearray({mo} * 2**19); time.sleep(600)"])
bloc = bytearray({mo} * 2**20)
compteur = Path(sys.argv[1])
i = 0
while True:
    for k in range(0, len(bloc), 4096):
        bloc[k] = i % 256  # garde toute la mémoire « chaude », comme un agent actif
    i += 1
    compteur.write_text(str(i))
    time.sleep(0.2)
"""

Mo = lambda o: f"{o / 2**20:,.0f} Mo".replace(",", " ")  # noqa: E731


def main() -> int:
    if not poste_ram.WINDOWS:
        print("ESSAI : Windows seulement")
        return 2
    mo = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    compteur = Path(tempfile.mkdtemp()) / "compteur.txt"
    proc = subprocess.Popen([sys.executable, "-c", AGENT.format(mo=mo), str(compteur)])
    try:
        time.sleep(4)
        pids = poste_ram.arbre(proc.pid)
        m = poste_ram.mesurer()
        avant = poste_ram.memoire_travail(pids)
        print(f"poste : {Mo(m.occupee)} occupés sur {Mo(m.total)} ; arbre du tour : {pids}")
        print(f"mémoire de travail avant la pause : {Mo(avant)}")
        assert len(pids) >= 2, "l'enfant n'est pas vu dans l'arbre"
        assert poste_ram.suspendre(pids), "suspension refusée"
        c1 = compteur.read_text(encoding="utf-8")
        time.sleep(3)
        pendant = poste_ram.memoire_travail(pids)
        c2 = compteur.read_text(encoding="utf-8")
        print(f"mémoire de travail en pause (vidée) : {Mo(pendant)} ; compteur figé : {c1} -> {c2}")
        assert c1 == c2, "le processus a progressé pendant la pause"
        assert proc.poll() is None, "le processus est mort pendant la pause"
        assert poste_ram.reprendre(pids), "reprise refusée"
        time.sleep(3)
        apres = poste_ram.memoire_travail(pids)
        c3 = compteur.read_text(encoding="utf-8")
        print(f"mémoire de travail après reprise : {Mo(apres)} ; compteur reparti : {c2} -> {c3}")
        assert int(c3) > int(c2), "le processus ne reprend pas"
        print(f"ESSAI : vert — libéré pendant la pause : {Mo(avant - pendant)}")
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
