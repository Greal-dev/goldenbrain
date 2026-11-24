"""Fixtures : vault temporaire, configuration de test, harnais factice (jamais de vrai claude)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from orchestrateur.config import Config, ConfigMoteur, ConfigVault
from orchestrateur.harnais import Evenement, Message
from orchestrateur.vault import Vault

PORT = 8399


def ecrire(racine: Path, rel: str, texte: str) -> Path:
    p = racine / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texte.encode("utf-8"))
    return p


def tache_md(statut="a-faire", extra="", titre="Titre") -> str:
    return f"---\ntype: tache\nstatut: {statut}\n{extra}tags: []\n---\n\n# {titre}\n\nCorps.\n"


@pytest.fixture
def racine(tmp_path: Path) -> Path:
    r = tmp_path / "vault"
    ecrire(r, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nparent: \"[[Operation-X]]\"\nnom: Alpha\n---\n")
    ecrire(r, "Projets/C1-Alpha/taches/mere.md", tache_md(titre="Mère"))
    ecrire(r, "Projets/C1-Alpha/taches/enfant.md",
           tache_md(extra='parent: "[[mere]]"\n', titre="Enfant"))
    ecrire(r, "Projets/C1-Alpha/taches/petit.md", tache_md(extra="parent: enfant\n", titre="Petit"))
    ecrire(r, "Projets/C2-Beta/contexte.md", "---\ncasquette: C2-Patrimoine\n---\n")
    ecrire(r, "Projets/C2-Beta/taches/doublon.md", tache_md(titre="Doublon Beta"))
    ecrire(r, "_meta/taches/doublon.md", tache_md(titre="Doublon Meta"))
    ecrire(r, "_meta/taches/fermee.md", tache_md(statut="fait", titre="Fermée"))
    ecrire(r, "Projets/Sans/taches/x.md", tache_md(extra="casquette: META\n", titre="X"))
    ecrire(r, "Projets/Vide/contexte.md", "---\ncasquette: C3\n---\n")
    ecrire(r, "_meta/templates/taches/modele.md", tache_md(titre="Modèle"))
    return r


@pytest.fixture
def config(racine: Path, tmp_path: Path) -> Config:
    return Config(
        port=PORT,
        vault=ConfigVault(racine=racine, taches=["Projets/*/taches/*.md", "_meta/taches/*.md",
                                                 "_meta/templates/taches/*.md"],
                          exclure=["_meta/templates/*"], gabarit_tache={"palier": "P1"},
                          index_ttl_s=0),  # les tests écrivent des fiches à la main puis relisent aussitôt
        moteur=ConfigMoteur(simultanes_max=2, sauts_max=3, harnais_defaut="faux"),
        harnais={"faux": {}},
        consigne="Tâche {titre} ({chemin}) place {fil_ariane} orch {orch} inconnue {autre}",
        donnees=tmp_path / "donnees")


@pytest.fixture
def vault(config: Config) -> Vault:
    return Vault(config.vault)


class FauxHarnais:
    """Rejoue `scenario` ; l'élément "attendre" bloque jusqu'à `arreter()` ou `liberer`."""

    nom = "faux"
    scenario: list = []
    lances: list = []
    arrets: list = []
    liberer: asyncio.Event | None = None

    def __init__(self, conf: dict):
        self.stop = asyncio.Event()

    async def lancer(self, message, *, session, deriver, consigne, env, modele=""):
        type(self).lances.append({"message": message, "session": session, "deriver": deriver,
                                  "consigne": consigne, "env": env, "modele": modele})
        for ev in list(self.scenario):
            if ev == "attendre":
                attentes = [asyncio.ensure_future(self.stop.wait())]
                if type(self).liberer:
                    attentes.append(asyncio.ensure_future(type(self).liberer.wait()))
                await asyncio.wait(attentes, return_when=asyncio.FIRST_COMPLETED)
                for a in attentes:
                    a.cancel()
                if self.stop.is_set():
                    return
                continue
            if isinstance(ev, Exception):
                raise ev
            yield ev
            await asyncio.sleep(0)

    async def arreter(self):
        type(self).arrets.append(self)
        self.stop.set()

    def transcript(self, session, limite):
        return [Message("assistant", f"bonjour {session}", ["Read"], "2026-11-12T10:00:00")]

    def commande_terminal(self, session):
        return f"faux --resume {session}"


RENDU = ("Travail fait.\n<fiche>\nfait: lu le dossier\nsituation: en bonne voie\nreste: tout\n"
         "prochain_pas: écrire\nsous_taches:\n- [x] lire\n- [ ] écrire\n</fiche>")


def scenario_ok(session="s-1", rendu=RENDU) -> list:
    return [Evenement("session", session=session), Evenement("texte", texte="je lis"),
            Evenement("outil", texte="Read: x"), Evenement("fin", session=session, texte=rendu)]


@pytest.fixture
def faux():
    classe = type("Faux", (FauxHarnais,), {"scenario": scenario_ok(), "lances": [],
                                            "arrets": [], "liberer": None})
    return classe


@pytest.fixture(autouse=True)
def environnement_isole(monkeypatch):
    """La porte lancée par un agent hérite de ORCH_SAUTS, ORCH_TACHE, ORCH_URL… : au 3e saut elle
    était rouge sans défaut de code (test_feux_verts, test_pilotage). Aucune variable ORCH_* ne
    traverse : les tests qui en ont besoin la posent eux-mêmes."""
    for nom in [n for n in os.environ if n.startswith("ORCH_")]:
        monkeypatch.delenv(nom)


@pytest.fixture(autouse=True)
def amorcage_des_meres(request, monkeypatch):
    """Les scénarios antérieurs au chat de projet prennent `mere` pour une tâche quelconque et
    comparent le message exact : l'amorçage des tâches mères (INV-PILOTAGE-2) n'y est actif que
    dans `test_pilotage.py`."""
    from orchestrateur import pilotage
    if request.module.__name__.rsplit(".", 1)[-1] != "test_pilotage":
        monkeypatch.setattr(pilotage, "TACHES_MERES", False)
