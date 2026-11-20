"""MCP strict par défaut (INV-MCP-1) : argv de `claude -p` selon réglage et frontmatter."""

from types import SimpleNamespace

import orchestrateur.compactage as c
from orchestrateur.compactage import MixinCompactage
from orchestrateur.harnais.claude import HarnaisClaude

DRAPEAU = "--strict-mcp-config"


def argv(conf=None):
    h = HarnaisClaude({"commande": "python3", **(conf or {})})
    return h._argv(None, False, "")


def test_mcp_strict_par_defaut():
    a = argv()
    assert DRAPEAU in a and "--mcp-config" not in a


def test_mcp_heritage_retire_le_drapeau():
    assert DRAPEAU not in argv({"mcp": "heritage"})


def test_mcp_valeur_inconnue_reste_strict():
    assert DRAPEAU in argv({"mcp": "n'importe quoi"})


def _instancier(monkeypatch, fm, conf_harnais):
    vus = []
    soi = SimpleNamespace(
        vault=None, config=SimpleNamespace(harnais={"claude": conf_harnais}),
        seuil_de=lambda *a: {"seuil": 1, "fenetre": 2}, _suivi={},
        executeurs=SimpleNamespace(envelopper=lambda i, n, inst: inst))
    t = SimpleNamespace(fm=fm, chemin="x")

    def fabrique(conf):
        vus.append(conf)
        return SimpleNamespace(compactage=None)
    monkeypatch.setattr(c, "codespace", SimpleNamespace(conf_tour=lambda conf, *a: conf))
    monkeypatch.setattr(c, "depot", SimpleNamespace(conf_harnais=lambda v, conf, i: conf))
    MixinCompactage.instancier(soi, "t", t, "claude", "", fabrique)
    return vus[0]


def test_mcp_frontmatter_heritage_deroge_par_tache(monkeypatch):
    assert _instancier(monkeypatch, {"mcp": "heritage"}, {"mcp": "aucun"}).get("mcp") == "heritage"
    assert _instancier(monkeypatch, {}, {"mcp": "aucun"}).get("mcp") == "aucun"
    assert _instancier(monkeypatch, {"mcp": "aucun"}, {"mcp": "heritage"}).get("mcp") == "heritage"
