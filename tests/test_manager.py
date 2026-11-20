"""Volet « manager » (INV-MANAGER-1) : un message du volet arrive à l'assistant comme instruction ;
un geste sensible attend Confirmer ; le fil est commun avec Telegram ; le volet marche sans Telegram."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.config import ConfigTelegram
from orchestrateur.vault import Conflit
from orchestrateur.moteur import Moteur
from test_telegram import _bouton, relever, tg  # noqa: F401 (fixture)


def _sans_telegram(config):
    config.telegram = ConfigTelegram(actif=False, conteneur="Projets/C1-Alpha")


def test_message_du_volet_arrive_a_l_assistant_comme_instruction_sans_telegram(config, vault, faux):
    _sans_telegram(config)

    async def scenario(c):
        c.fil.instruction("Qu'est-ce qui m'attend ?")

    c, _ = relever(config, vault, faux, scenario)
    lance = faux.lances[-1]
    assert lance["env"]["ORCH_TACHE"] == c.etat["tache_tri"]
    assert "[Instruction du volet]\n[instruction] Qu'est-ce qui m'attend ?" in lance["message"]
    assert "Tu es l'assistant de l'utilisateur" in lance["message"]
    assert [(m["de"], m["canal"]) for m in c.fil.etat["messages"]] == [("vous", "volet")]


def test_reponse_et_geste_sans_telegram_attendent_confirmer_dans_le_volet(config, vault, faux):
    _sans_telegram(config)

    async def scenario(c):
        c.fil.instruction("Passe la mère en bloqué")
        await c.question(c.etat["tache_tri"], "Je la passe en bloqué ?", vise="mere", geste="statut=bloque")
        m = c.fil.etat["messages"][-1]
        assert m["de"] == "manager" and m["texte"].startswith("Je la passe en bloqué ?\n→ Mère")
        assert [b["data"] for b in m["boutons"]] == ["confirmer", "annuler"]
        assert vault.tache("mere").statut == "a-faire"  # rien avant le bouton
        c.fil.bouton(m["n"], "confirmer")
        with pytest.raises(Conflit):
            c.fil.bouton(m["n"], "confirmer")  # un bouton ne sert qu'une fois

    c, _ = relever(config, vault, faux, scenario)
    assert vault.tache("mere").statut == "bloque"
    assert c.fil.etat["messages"][-1]["issue"] == "Fait : statut = bloque"
    assert "[Geste Telegram] Confirmé par l'utilisateur : statut de mere" in faux.lances[-1]["message"]


def test_fil_commun_avec_telegram_et_bouton_consomme_une_fois(config, vault, faux, tg):
    async def scenario(c):
        tg.message(1, text="Où en est la mère ?")
        await c.relever()

    async def volet(c):
        c.fil.instruction("Et sa priorité ?")

    async def geste(c):
        await c.question(c.etat["tache_tri"], "Priorité haute ?", vise="mere", geste="priorite=haute")
        bot = tg.envoyes[-1]
        assert bot["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "confirmer"
        n = c.fil.etat["messages"][-1]["n"]
        _bouton(tg, 2, "confirmer", bot["message_id"])  # confirmé sur Telegram…
        await c.relever()
        with pytest.raises(Conflit):
            c.fil.bouton(n, "confirmer")  # …le volet ne l'applique pas une seconde fois

    c, _ = relever(config, vault, faux, scenario, volet, geste)
    tri = c.etat["tache_tri"]
    assert {lance["env"]["ORCH_TACHE"] for lance in faux.lances} == {tri}  # une seule conversation
    assert "Tu es l'assistant" not in faux.lances[1]["message"]  # même conversation, consigne non redite
    fil = [(m["de"], m["canal"], m["texte"].split("\n")[0]) for m in c.fil.etat["messages"]]
    assert fil == [("vous", "telegram", "Où en est la mère ?"), ("vous", "volet", "Et sa priorité ?"),
                   ("manager", "volet", "Priorité haute ?")]
    assert c.fil.etat["messages"][-1]["issue"] == "Fait : priorite = haute"
    assert str(vault.tache("mere").fm.get("priorite")) == "haute"


def test_nouveau_depuis_le_volet_ouvre_un_fil_neuf(config, vault, faux):
    _sans_telegram(config)

    async def scenario(c):
        c.fil.instruction("Bonjour")

    async def nouveau(c):
        c.fil.instruction("/nouveau")

    c, _ = relever(config, vault, faux, scenario, nouveau)
    assert not vault.tache(c.etat["tache_tri"]).fm.get("session")
    assert c.fil.etat["messages"][-1]["texte"].startswith("Fil neuf ouvert")
    assert len(faux.lances) == 1  # /nouveau ne lance aucun tour


def test_api_du_volet(config, vault, faux):
    _sans_telegram(config)
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url="http://127.0.0.1:8399") as client:
        _essai_api(client)


def _essai_api(client):
    h = {"X-Orchestrateur": "1"}
    assert client.get("/api/manager").json() == {"messages": [], "tache": None, "en_cours": False,
                                                 "telegram": False}
    assert client.post("/api/manager/message", json={"texte": "Bonjour"}).status_code == 403  # INV-API-1
    assert client.post("/api/manager/message", json={"texte": "  "}, headers=h).status_code == 400
    r = client.post("/api/manager/message", json={"texte": "Bonjour"}, headers=h)
    assert r.status_code == 200 and r.json()["de"] == "vous"
    lu = client.get("/api/manager").json()
    assert lu["tache"] and [m["texte"] for m in lu["messages"]] == ["Bonjour"]
    assert client.post("/api/manager/bouton", json={"n": 1, "choix": "confirmer"}, headers=h).status_code == 409


def _app(config, vault, faux):
    return TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url="http://127.0.0.1:8399")


def test_bouton_presse_par_un_agent_est_refuse_et_le_geste_non_applique(config, vault, faux, monkeypatch):
    _sans_telegram(config)
    appels = []
    monkeypatch.setattr("orchestrateur.manager.Fil.bouton", lambda self, n, choix: appels.append((n, choix)))
    with _app(config, vault, faux) as client:
        r = client.post("/api/manager/bouton", json={"n": 1, "choix": "confirmer"},
                        headers={"X-Orchestrateur": "1", "X-Orch-Tache": "mere"})
    assert r.status_code == 409 and "un agent ne presse pas les boutons" in r.text
    assert appels == []


def test_bouton_n_nul_est_refuse_par_la_validation(config, vault, faux):
    _sans_telegram(config)
    with _app(config, vault, faux) as client:
        r = client.post("/api/manager/bouton", json={"n": 0, "choix": "confirmer"}, headers={"X-Orchestrateur": "1"})
    assert r.status_code == 400  # le garde de validation de l'API traduit 422 en 400


def test_soumettre_qui_leve_laisse_le_fil_inchange_et_garde_le_resume(config, vault, faux, monkeypatch):
    _sans_telegram(config)

    async def scenario(c):
        c.etat["resume"] = "R"
        monkeypatch.setattr(c.moteur, "soumettre", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("panne")))
        with pytest.raises(RuntimeError):
            c.fil.instruction("Bonjour")
        assert c.fil.etat["messages"] == [] and c.etat["resume"] == "R"

    relever(config, vault, faux, scenario)
