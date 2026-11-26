"""Préchauffage (INV-FROID-1) : les caches du premier écran sont remplis au démarrage, sans jamais bloquer le serveur."""

import asyncio

from orchestrateur import prechauffage
from orchestrateur.moteur import Moteur


def test_prechauffage_remplit_les_caches_de_l_index(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    assert not vault._cache  # cache de lecture vide à froid
    prechauffage.chauffer(m)
    assert vault._cache


def test_prechauffage_ne_leve_jamais(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.vault = None  # démarrage cassé : le préchauffage journalise et rend la main
    prechauffage.chauffer(m)


def test_chauffer_tout_execute_les_lectures_lentes_et_borne_les_defaillantes(config, vault, faux, monkeypatch):
    m = Moteur(config, vault, {"faux": faux})
    faites = []

    async def lente():
        await asyncio.sleep(0.05)
        faites.append("lente")

    async def muette():  # réseau muet : coupée au délai, le démarrage continue
        await asyncio.sleep(30)

    async def cassee():
        raise OSError("outil absent")

    monkeypatch.setattr(prechauffage, "DELAI_S", 0.2)
    asyncio.run(prechauffage.chauffer_tout(m, lente, muette, cassee))
    assert faites == ["lente"] and vault._cache
