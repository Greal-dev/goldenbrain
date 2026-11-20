"""Point d'entrée : `python -m orchestrateur` démarre uvicorn sur 127.0.0.1.

Rôle : charger la configuration (`config.toml` à la racine du dépôt, ou `ORCH_CONFIG`) et servir
l'API ; sortir avec le code 3 si un redémarrage a été demandé (`lancer.cmd` relance alors).
Frontières : aucune logique.
Invariants portés : INV-API-1 (écoute sur 127.0.0.1), INV-DISTANT-1 (plus, sur option, une
adresse d'interface précise pour les exécuteurs et les appareils — jamais toutes), INV-DISTANT-7
(cette adresse sert en HTTPS quand le certificat Tailscale est posé, la boucle locale reste en
HTTP), INV-VERSION-1 (sortie 3 après la fermeture propre).
"""

import asyncio
import socket
import sys

import uvicorn

from .api import creer_app
from .config import charger


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
