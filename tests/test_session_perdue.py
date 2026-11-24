"""INV-SESSION-1 : « No conversation found with session ID » ne fait jamais échouer un tour."""

import asyncio

import pytest

from orchestrateur import session_perdue
from orchestrateur.harnais import Evenement
from orchestrateur.harnais.claude import HarnaisClaude
from orchestrateur.moteur import Moteur
from conftest import FauxHarnais, RENDU

ABSENTE = "No conversation found with session ID: 00000000-0000-4000-8000-000000000000"


class Reprise(FauxHarnais):
    """Refuse toute reprise (comme claude --resume sur un identifiant sans transcript)."""
    nom = "faux"
    appels: list = []

    async def lancer(self, message, *, session, deriver, consigne, env, modele=""):
        type(self).appels.append(session)
        if session:
            yield Evenement("session", session="neuve-fantome")  # claude l'émet avant d'échouer
            yield Evenement("erreur", texte=ABSENTE)
            return
        yield Evenement("session", session="neuve-ok")
        yield Evenement("fin", session="neuve-ok", texte=RENDU)


def _moteur(config, vault):
    Reprise.appels = []
    m = Moteur(config, vault, {"faux": Reprise})
    m._q = m.abonner()
    return m


def _journal(m):
    out = []
    while not m._q.empty():
        out.append(m._q.get_nowait())
    return out


async def _finir(m):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def test_no_conversation_found_repli_en_session_neuve_une_seule_fois(config, vault):
    vault.modifier("mere", {"session": "orpheline"})

    async def scenario():
        m = _moteur(config, vault)
        m.soumettre("mere", "go")
        await _finir(m)
        return _journal(m)

    evts = asyncio.run(scenario())
    assert Reprise.appels == ["orpheline", None]  # une reprise refusée, un seul repli
    assert vault.tache("mere").fm["session"] == "neuve-ok"
    fin = next(e for e in evts if e["type"] == "tour_fin")
    assert not fin.get("erreur")


def test_no_conversation_found_ne_declenche_pas_l_escalade(config, vault, monkeypatch):
    # Même quand le repli est impossible (dérivation), l'erreur n'est pas comptée comme échec.
    vu = []
    monkeypatch.setattr("orchestrateur.economie.Economie.issue",
                        lambda self, ident, statut, final: vu.append(statut))

    class Toujours(Reprise):
        async def lancer(self, message, *, session, deriver, consigne, env, modele=""):
            yield Evenement("erreur", texte=ABSENTE)

    async def scenario():
        m = Moteur(config, vault, {"faux": Toujours})
        m.soumettre("mere", "go")
        await _finir(m)

    asyncio.run(scenario())
    assert vu == []


@pytest.mark.parametrize("texte", [
    ABSENTE, "Error: session abc not found", "no saved session found", "thread xyz not found"])
def test_session_absente_reconnue(texte):
    assert session_perdue.session_absente(texte)


@pytest.mark.parametrize("texte", ["", None, "boum", "error_during_execution", "rate limit"])
def test_autres_erreurs_non_confondues(texte):
    assert not session_perdue.session_absente(texte)


def test_repli_pas_apres_une_sortie_utile():
    appels = []

    async def lancer(*, session, deriver, **kw):
        appels.append(session)
        yield Evenement("texte", texte="début")
        yield Evenement("erreur", texte=ABSENTE)

    async def tout():
        return [e.type async for e in session_perdue.avec_repli(
            lancer, lambda: "x", "s", False, message="m")]

    assert asyncio.run(tout()) == ["texte", "erreur"] and appels == ["s"]


def test_claude_lit_la_cause_dans_errors(tmp_path):
    """Windows et Linux : le texte d'erreur de claude vient de `errors` quand `result` manque."""
    import json, sys
    script = tmp_path / "faux_claude.py"
    ligne = {"type": "result", "subtype": "error_during_execution", "is_error": True,
             "num_turns": 0, "errors": [ABSENTE], "session_id": "x"}
    script.write_text(f"import sys, json\nsys.stdin.read()\nprint(json.dumps({ligne!r}))\n",
                      encoding="utf-8")
    h = HarnaisClaude({"commande": sys.executable, "arguments": [str(script)],
                       "dossier": str(tmp_path)})

    async def tout():
        return [e async for e in h.lancer("m", session="s", deriver=False, consigne="", env={})]

    erreurs = [e for e in asyncio.run(tout()) if e.type == "erreur"]
    assert erreurs and session_perdue.session_absente(erreurs[0].texte)
