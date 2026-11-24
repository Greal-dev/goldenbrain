"""Porte complète avec reçu : `python scripts/porte.py` lance, `python scripts/porte.py verifier` contrôle.

Rôle : lance la porte complète (`check.py` puis `check_ui.py`) et, seulement si elle est verte sur un
arbre git propre, écrit un reçu signé de l'arbre testé (empreinte de l'arbre, date, résumé des tests)
dans le dossier d'état local. La CI locale le relit : un reçu valable pour l'arbre exact de `origin/mvp`
et vieux de moins de 24 h dispense de rejouer la suite (INV-PORTE-1). L'intégration emploie ce script.
Frontières : n'écrit rien dans le dépôt ; le dossier d'état (`GOLDENBRAIN_ETAT_LOCAL`, sinon
`$XDG_STATE_HOME/goldenbrain`, sinon `~/.local/state/goldenbrain`, `%LOCALAPPDATA%\\GoldenBrain` sous
Windows) porte la clé de signature (créée à droits 0600) et les reçus. La signature (HMAC-SHA256) arrête
l'affirmation sans preuve et la copie d'un reçu vers un autre arbre ; elle n'arrête pas un processus
qui lirait la clé avec les droits de l'utilisateur.
Invariants portés : INV-PORTE-1.
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
AGE_MAX_H = 24.0  # au-delà, la CI rejoue la suite (un passage complet au moins une fois par jour)
CONSERVATION_J = 7
AVERTISSEMENT_SENSIBLE = "`.sensible` absent ou vide"  # sortie de check.py : INV-PUB-1 non contrôlé


def dossier_etat() -> Path:
    if (d := os.environ.get("GOLDENBRAIN_ETAT_LOCAL")):
        return Path(d)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "GoldenBrain"
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state"
    return Path(base) / "goldenbrain"


def _git(dossier: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=dossier, capture_output=True, text=True, encoding="utf-8",
                       timeout=120)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} : {r.stderr.strip()}")
    return r.stdout.strip()


def arbre(dossier: Path, rev: str = "HEAD") -> str:
    """Empreinte de l'arbre git d'une révision (celle de l'arbre testé, indépendante de l'historique)."""
    return _git(dossier, "rev-parse", f"{rev}^{{tree}}")


def propre(dossier: Path) -> bool:
    """Aucun fichier suivi modifié, aucun fichier non suivi non ignoré : l'arbre testé EST le commit."""
    return not _git(dossier, "status", "--porcelain")


def _cle(etat: Path, creer: bool) -> bytes | None:
    chemin = etat / "cle"
    if not chemin.exists() and creer:
        etat.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(secrets.token_bytes(32))
    try:
        return chemin.read_bytes() or None
    except OSError:
        return None


def _signer(cle: bytes, corps: dict) -> str:
    canon = json.dumps(corps, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    return hmac.new(cle, canon, hashlib.sha256).hexdigest()


def ecrire_recu(etat: Path, arbre_teste: str, commit: str, resume: dict, motifs_personnels: bool,
                maintenant: float | None = None) -> Path:
    """Écrit le reçu signé ; purge les reçus de plus de `CONSERVATION_J` jours."""
    t = time.time() if maintenant is None else maintenant
    corps = {"arbre": arbre_teste, "commit": commit, "epoch": int(t),
             "date": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)), "resume": resume,
             "motifs_personnels": motifs_personnels}
    cle = _cle(etat, creer=True)
    if cle is None:
        raise RuntimeError("clé de signature illisible")
    recus = etat / "recus"
    recus.mkdir(parents=True, exist_ok=True)
    for vieux in recus.glob("*.json"):
        if t - vieux.stat().st_mtime > CONSERVATION_J * 86400:
            vieux.unlink(missing_ok=True)
    fichier = recus / f"{arbre_teste}.json"
    fichier.write_text(json.dumps({**corps, "signature": _signer(cle, corps)}, indent=1), encoding="utf-8")
    return fichier


def controler(etat: Path, arbre_attendu: str, age_max_h: float = AGE_MAX_H,
              maintenant: float | None = None) -> tuple[bool, str]:
    """Le reçu de cet arbre existe, est authentique, récent, et la porte avait ses motifs INV-PUB-1."""
    t = time.time() if maintenant is None else maintenant
    cle = _cle(etat, creer=False)
    if cle is None:
        return False, "aucune clé de signature : pas de reçu"
    try:
        recu = json.loads((etat / "recus" / f"{arbre_attendu}.json").read_text(encoding="utf-8"))
        signature = recu.pop("signature")
    except (OSError, ValueError, KeyError, AttributeError):
        return False, f"aucun reçu lisible pour l'arbre {arbre_attendu[:12]}"
    if not hmac.compare_digest(str(signature), _signer(cle, recu)):
        return False, "signature invalide : reçu altéré ou forgé"
    if recu.get("arbre") != arbre_attendu:
        return False, "le reçu porte un autre arbre"
    age_h = (t - float(recu.get("epoch", 0))) / 3600
    if age_h < -0.1:
        return False, "reçu daté du futur"
    if age_h > age_max_h:
        return False, f"reçu trop ancien ({age_h:.1f} h > {age_max_h:g} h)"
    if not recu.get("motifs_personnels"):
        return False, "porte lancée sans `.sensible` : INV-PUB-1 non contrôlé"
    return True, f"reçu valable : porte verte il y a {age_h:.1f} h ({recu['resume'].get('tests', '?')})"


def _passer(dossier: Path, script: str) -> tuple[int, str]:
    """Lance un script de porte, recopie sa sortie en direct et la rend."""
    p = subprocess.Popen([sys.executable, str(dossier / "scripts" / script)], cwd=dossier,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
    sortie = []
    for ligne in p.stdout:
        print(ligne, end="", flush=True)
        sortie.append(ligne)
    return p.wait(), "".join(sortie)


def _tests(sortie: str) -> str:
    """Totaux pytest (« 12 passed … ») de la sortie, pour le résumé du reçu."""
    return " + ".join(m.group(0) for m in re.finditer(r"\d+ passed(?:, \d+ \w+)*", sortie)) or "sans total"


def lancer(dossier: Path, etat: Path) -> int:
    """Porte complète ; reçu seulement si verte ET sur un arbre propre, identique avant et après."""
    avant, commit, net = arbre(dossier), _git(dossier, "rev-parse", "HEAD"), propre(dossier)
    code, s1 = _passer(dossier, "check.py")
    if code:
        return code
    code, s2 = _passer(dossier, "check_ui.py")
    if code:
        return code
    if not net or not propre(dossier) or arbre(dossier) != avant:
        print("PORTE : verte, mais l'arbre n'est pas propre (ou a bougé) : aucun reçu écrit")
        return 0
    f = ecrire_recu(etat, avant, commit, {"controle": "vert", "interface": "vert",
                                          "tests": _tests(s1 + s2)}, AVERTISSEMENT_SENSIBLE not in s1)
    print(f"PORTE : vert ; reçu {f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", nargs="?", choices=["lancer", "verifier"], default="lancer")
    ap.add_argument("--arbre", help="verifier : empreinte d'arbre attendue (défaut : HEAD)")
    ap.add_argument("--dossier", default=str(RACINE), help="dépôt git testé (défaut : celui du script)")
    ap.add_argument("--age-max-h", type=float, default=AGE_MAX_H)
    a = ap.parse_args()
    dossier, etat = Path(a.dossier), dossier_etat()
    if a.action == "lancer":
        return lancer(dossier, etat)
    ok, motif = controler(etat, a.arbre or arbre(dossier), a.age_max_h)
    print(("RECU : " if ok else "PAS DE RECU : ") + motif)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
