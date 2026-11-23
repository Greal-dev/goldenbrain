"""Point d'entrée : `python -m orchestrateur` démarre uvicorn sur 127.0.0.1.

Rôle : charger la configuration (`config.toml` à la racine du dépôt, ou `ORCH_CONFIG`) et servir
l'API ; sortir avec le code 3 si un redémarrage a été demandé (`lancer.cmd` relance alors).
Frontières : seule logique, le verrou d'instance (un moteur par vault).
Invariants portés : INV-API-1 (écoute sur 127.0.0.1), INV-DISTANT-1 (plus, sur option, une
adresse d'interface précise pour les exécuteurs et les appareils — jamais toutes), INV-DISTANT-7
(cette adresse sert en HTTPS quand le certificat Tailscale est posé, la boucle locale reste en
HTTP), INV-VERSION-1 (sortie 3 après la fermeture propre), INV-INSTANCE-1 (un seul moteur par
vault : un second refuse de démarrer).
"""

import asyncio
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

import uvicorn

from .api import creer_app
from .config import charger
from .propositions import maintenant

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

_OCTET_VERROU = 1 << 30  # Windows : l'octet verrouillé est hors du texte, que l'autre instance lit


def fichier_verrou(racine: Path) -> Path:
    """INV-INSTANCE-1 : un fichier par vault (clé = chemin résolu), dans le dossier de cache de
    l'utilisateur ; un vault temporaire (essais) a son propre verrou et ne gêne personne."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "goldenbrain" / "verrous"
    cle = hashlib.sha256(str(Path(racine).resolve()).encode("utf-8")).hexdigest()[:16]
    return base / f"{cle}.lock"


def _verrouiller(f) -> None:
    if sys.platform == "win32":
        f.seek(_OCTET_VERROU)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def prendre_verrou(chemin: Path, racine: Path, port: int):
    """INV-INSTANCE-1 : verrou système exclusif sur `chemin` (rendu par le système à la mort du
    processus, même brutale : jamais de verrou périmé). Refus : SystemExit avec un message qui
    dit qui le tient (PID, port, depuis quand) et comment l'arrêter. Garder le fichier ouvert."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    f = open(chemin, "a+", encoding="utf-8")
    try:
        _verrouiller(f)
    except OSError:
        f.seek(0)
        try:
            info = json.loads(f.read() or "{}")
        except ValueError:
            info = {}
        f.close()
        pid, depuis = info.get("pid", "inconnu"), info.get("depuis", "date inconnue")
        sys.exit(f"GoldenBrain est déjà lancé sur ce vault ({racine}) : processus {pid}, port "
                 f"{info.get('port', 'inconnu')}, depuis {depuis}. Deux moteurs sur un même vault "
                 f"exécuteraient chaque routine deux fois. Arrêtez l'autre instance (fermez-la, "
                 f"ou `kill {pid}`, ou `systemctl --user stop goldenbrain`) puis relancez.")
    f.seek(0)
    f.truncate()
    f.write(json.dumps({"pid": os.getpid(), "port": port, "vault": str(racine), "depuis": maintenant()}))
    f.flush()
    return f


def adresses(config) -> tuple[list[str], list[str]]:
    """(adresses en HTTP, adresses en HTTPS). INV-DISTANT-1 : jamais une adresse joker."""
    distante = [config.executeurs.ecoute] if config.executeurs.ecoute else []
    if config.distant.certificat:
        return ["127.0.0.1"], distante
    return ["127.0.0.1"] + distante, []


async def _servir(paires: list) -> None:
    async def un(serveur, prises):
        try:
            await serveur.serve(sockets=prises)
        finally:  # l'un s'arrête, tous s'arrêtent (signal, redémarrage)
            for s, _ in paires:
                s.should_exit = True
    await asyncio.gather(*(un(s, p) for s, p in paires))


def main() -> None:
    config = charger()
    verrou = prendre_verrou(fichier_verrou(config.vault.racine), config.vault.racine, config.port)  # noqa: F841
    app = creer_app(config)
    clair, chiffre = adresses(config)
    # INV-API-1 : la boucle locale ; INV-DISTANT-1 : plus l'adresse `executeurs.ecoute` si posée.
    # Délai de grâce borné : un flux SSE ouvert ne retient pas l'arrêt indéfiniment.
    paires = [(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=config.port, timeout_graceful_shutdown=5)),
               [socket.create_server((a, config.port)) for a in clair])]
    if chiffre:  # INV-DISTANT-7 : second serveur, même application, cycle de vie porté par le premier
        paires.append((uvicorn.Server(uvicorn.Config(
            app, lifespan="off", timeout_graceful_shutdown=5, ssl_certfile=config.distant.certificat,
            ssl_keyfile=config.distant.cle)), [socket.create_server((a, config.port)) for a in chiffre]))
    # INV-VERSION-1 : `should_exit` = arrêt normal d'uvicorn (lifespan, tours arrêtés).
    app.state.version.arreter = lambda: [setattr(s, "should_exit", True) for s, _ in paires]
    asyncio.run(_servir(paires))
    if app.state.version.code_sortie:
        sys.exit(app.state.version.code_sortie)


if __name__ == "__main__":
    main()
