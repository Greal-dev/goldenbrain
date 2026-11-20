"""Moteurs par rôle : résolution, repli journalisé (INV-MOTEUR-2), compteurs, application au conseil,
aux personas, aux mandats et au jardinage. Faux harnais seulement."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, roles
from orchestrateur import config as cfg_mod
from orchestrateur.config import ConfigConseil, ConfigRole
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import FauxHarnais, scenario_ok
from test_conseil import bloc
from test_moteur import executer, finir, moteur
from test_revues import OK, evs, multi, persona, tout_finir

H = {"X-Orchestrateur": "1"}
QUOTA = [Evenement("session", session="r-1"), Evenement("erreur", texte="429 quota exceeded")]


@pytest.fixture(autouse=True)
def _executables(monkeypatch):
    monkeypatch.setattr(roles, "resoudre", lambda commande: [commande])


@pytest.fixture
def rapide():
    return type("Rapide", (FauxHarnais,), {"scenario": list(QUOTA), "lances": [], "arrets": [],
                                            "liberer": None})


@pytest.fixture
def reg(config, faux, rapide):
    config.harnais = {"faux": {}, "rapide": {}}
    config.moteurs_par_role = {"conseil": ConfigRole("rapide", "flash", repli_modele="haiku"),
                               "persona": ConfigRole("rapide", "flash"),
                               "jardinage": ConfigRole("rapide", "flash"),
                               "mandat": ConfigRole("rapide", "flash")}
    return {"faux": faux, "rapide": rapide}


# --- configuration et résolution ---------------------------------------------------------
def test_role_inconnu_refuse():
    with pytest.raises(ValueError, match="rôle inconnu : voyou"):
        cfg_mod._roles({"voyou": {"harnais": "agy"}})
    assert cfg_mod._roles({"conseil": {"harnais": "agy", "modele": "m"}})["conseil"].repli is True


def test_exemple_rapide_sur_gemini_jugement_sur_sonnet_par_agy_travail_sur_claude():
    c = cfg_mod.charger(cfg_mod.RACINE_DEPOT / "config.exemple.toml")
    assert {r: x.famille for r, x in c.moteurs_par_role.items()} == {
        "conseil": "rapide", "jardinage": "rapide", "fiche": "rapide", "persona": "sonnet", "mandat": "sonnet", "tri": "rapide",
        "notes": "rapide"}
    assert c.credits == {"rapide": ["agy", "claude"], "sonnet": ["agy", "claude"], "opus": ["agy", "claude"]}
    r = roles.Roles(c, {})
    assert r.choisir("conseil") == roles.Choix("agy", "gemini-3.8-flash-medium", (("claude", "haiku"),))
    assert r.choisir("persona") == roles.Choix("agy", "claude-sonnet-5-5-medium", (("claude", "sonnet"),))
    assert r.choisir("tache") is None and c.moteur.harnais_defaut == "claude"  # travail principal inchangé


def test_credits_et_familles_valides():
    assert cfg_mod._credits({"opus": ["claude"]})["opus"] == ["claude"]
    assert cfg_mod._credits({})["rapide"] == ["agy", "claude"]
    with pytest.raises(ValueError, match="credits : famille inconnue : lent"):
        cfg_mod._credits({"lent": ["agy"]})
    with pytest.raises(ValueError, match="liste de noms"):
        cfg_mod._credits({"rapide": "agy"})
    with pytest.raises(ValueError, match="famille inconnue : geant"):
        cfg_mod._roles({"persona": {"famille": "geant"}})


@pytest.fixture
def familles(config):
    config.harnais = {"agy": {"familles": {"rapide": "flash", "sonnet": "claude-sonnet-5-5-medium"}},
                      "claude": {"familles": {"rapide": "haiku", "sonnet": "sonnet", "opus": "opus"}},
                      "codex": {}}
    config.moteurs_par_role = {"conseil": ConfigRole(famille="rapide"), "persona": ConfigRole(famille="sonnet"),
                               "mandat": ConfigRole(famille="opus")}
    return roles.Roles(config, {})


def test_ordre_des_credits_par_famille_avec_le_modele_de_chaque_harnais(familles, config):
    assert familles.choisir("persona") == roles.Choix(
        "agy", "claude-sonnet-5-5-medium", (("claude", "sonnet"),))
    # agy n'a pas de modèle `opus` : ce harnais est sauté pour cette famille.
    assert familles.choisir("mandat") == roles.Choix("claude", "opus")
    config.credits["rapide"] = ["claude", "agy", "codex"]  # inversé ; codex sans modèle de famille : sauté
    assert familles.choisir("conseil") == roles.Choix("claude", "haiku", (("agy", "flash"),))
    config.moteurs_par_role["conseil"] = ConfigRole(famille="rapide", repli=False)
    assert familles.choisir("conseil") == roles.Choix("claude", "haiku")


def test_harnais_explicite_l_emporte_sur_la_famille(familles, config):
    config.moteurs_par_role["persona"] = ConfigRole("claude", "opus", famille="sonnet")
    assert familles.choisir("persona").harnais == "claude" and familles.choisir("persona").modele == "opus"


def test_conversation_ouverte_garde_son_harnais_en_tete(familles):
    # Une conversation ne change pas de harnais en cours de route : l'ordre ne vaut qu'au premier tour.
    assert familles.choisir("persona", prefere="claude") == roles.Choix(
        "claude", "sonnet", (("agy", "claude-sonnet-5-5-medium"),))
    assert familles.choisir("persona", prefere="autre").harnais == "agy"


def test_chaine_de_trois_moteurs_deux_replis_journalises(config, reg):
    config.harnais["tiers"] = {}
    tiers = type("Tiers", (FauxHarnais,), {"scenario": scenario_ok("t-1"), "lances": [], "arrets": [],
                                            "liberer": None})
    r = roles.Roles(config, {**reg, "tiers": tiers})
    choix = roles.Choix("rapide", "a", (("rapide", "b"), ("tiers", "c")))

    async def flux():
        return [ev async for ev in r.lancer("conseil", choix, "m", consigne="", env={},
                                            sur_harnais=lambda h, n: None)]

    evs = executer(flux())
    assert [e.type for e in evs] == ["session", "repli", "repli", "session", "texte", "outil", "fin"]
    # Le 1er échec (quota) met `rapide` en panne : sa 2e entrée est sautée sans lancement.
    assert [x["vers"] for x in r.replis] == ["rapide", "tiers"] and tiers.lances[0]["modele"] == "c"
    assert r.tours[("rapide", "conseil")] == 1 and r.tours[("tiers", "conseil")] == 1
    assert "quota" in r.replis[1]["motif"]


def test_modeles_claude_d_antigravity_sont_acceptes_et_proposes(monkeypatch):
    from orchestrateur import catalogue
    from orchestrateur.harnais.agy import HarnaisAgy
    ids = ["gemini-3.8-flash-medium", "claude-sonnet-5-5-medium", "claude-opus-5-5-high"]
    monkeypatch.setattr(HarnaisAgy, "decouvrir_modeles", lambda self: ids)
    monkeypatch.setattr(catalogue, "resoudre", lambda commande: [commande])
    cat = catalogue.Catalogue({"agy": {"modeles": "auto"}}, {"agy": HarnaisAgy})
    agy = next(x for x in executer(cat.lister()) if x["nom"] == "agy")
    assert agy["modeles"] == ids and all(catalogue.modele_valide(m) == m for m in ids)


def test_choisir(config, reg):
    r = roles.Roles(config, reg)
    assert r.choisir("conseil") == roles.Choix("rapide", "flash", (("faux", "haiku"),))
    assert r.choisir("fiche") is None  # non réglé : moteur habituel
    assert r.choisir("persona", "claude", "opus") == roles.Choix("claude", "opus")  # moteur fixé : pas de repli
    assert r.choisir("fiche", defaut=("claude", "haiku")) == roles.Choix("claude", "haiku")
    config.moteurs_par_role["conseil"] = ConfigRole("faux", "m")  # = moteur par défaut : rien à replier
    assert r.choisir("conseil").repli == ()
    config.moteurs_par_role["conseil"] = ConfigRole("rapide", "m", repli=False)
    assert r.choisir("conseil").repli == ()


# --- conseil -----------------------------------------------------------------------------
@pytest.fixture
def client(config, vault, reg):
    config.conseil = ConfigConseil(harnais="faux", modele="petit", delai_s=5)
    app = api.creer_app(config, Moteur(config, vault, reg))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        yield c


def avis(client):
    return client.post("/api/conseil", headers=H, json={"action": "promouvoir", "tache": "mere"}).json()


def test_conseil_part_sur_le_harnais_du_role_et_se_compte(client, reg):
    reg["rapide"].scenario = [Evenement("fin", session="e", texte=bloc("favorable"))]
    assert avis(client)["avis"] == "favorable"
    assert reg["rapide"].lances[0]["modele"] == "flash" and not reg["faux"].lances
    assert {"harnais": "rapide", "role": "conseil", "tours": 1} in client.get("/api/etat").json()["roles"]["tours"]


def test_conseil_repli_journalise_sur_erreur_de_quota_puis_harnais_evite(client, reg, config):
    reg["faux"].scenario = [Evenement("fin", session="e", texte=bloc("defavorable"))]
    assert avis(client)["avis"] == "defavorable"
    assert len(reg["rapide"].lances) == 1 and reg["faux"].lances[0]["modele"] == "haiku"
    etat = client.get("/api/etat").json()["roles"]
    assert etat["replis"][0]["role"] == "conseil" and etat["replis"][0]["de"] == "rapide"
    assert "quota" in etat["replis"][0]["motif"]
    journal = "".join(f.read_text("utf-8") for f in (config.donnees / "journal").rglob("conseil-*.jsonl"))
    assert '"type": "repli"' in journal
    avis(client)  # harnais en quota : évité d'emblée, sans nouveau lancement
    assert len(reg["rapide"].lances) == 1 and len(reg["faux"].lances) == 2


def test_conseil_repli_si_le_harnais_est_introuvable(client, reg, monkeypatch):
    reg["rapide"].commande = "rapide"
    reg["faux"].scenario = [Evenement("fin", session="e", texte=bloc("favorable"))]
    monkeypatch.setattr(roles, "resoudre", lambda c: (_ for _ in ()).throw(FileNotFoundError(c)) if c == "rapide" else [c])
    assert avis(client)["avis"] == "favorable" and not reg["rapide"].lances


def test_conseil_sans_repli_reste_indisponible(client, reg, config):
    config.moteurs_par_role["conseil"] = ConfigRole("rapide", "flash", repli=False)
    r = avis(client)
    assert r["avis"] == "indisponible" and "quota" in r["motif"]
    assert not reg["faux"].lances  # INV-MOTEUR-1 : jamais de repli sans réglage explicite


def test_conseil_sans_reglage_de_role_suit_la_section_conseil(client, reg, config):
    config.moteurs_par_role = {}
    reg["faux"].scenario = [Evenement("fin", session="e", texte=bloc("favorable"))]
    assert avis(client)["avis"] == "favorable" and reg["faux"].lances[0]["modele"] == "petit"


# --- persona -----------------------------------------------------------------------------
def revue(config, vault, reg, fixe=""):
    reg["faux"].scenario = evs("p-1", OK)

    async def scenario():
        m = Moteur(config, vault, reg)
        for p in m.revues.equipe.lister():
            m.revues.equipe.retirer(p["id"])
        persona(m, "rssi", "RSSI", **({"harnais": fixe} if fixe else {}))
        return m, await m.revues._tour("mere", m.revues.equipe.lister()[0], "revue")

    return executer(scenario())


def test_persona_par_role_se_replie_sur_le_moteur_par_defaut(config, vault, reg):
    m, avis_ = revue(config, vault, reg)
    assert avis_["verdict"] == "ok" and len(reg["rapide"].lances) == 1 and len(reg["faux"].lances) == 1
    assert m.roles.tours[("faux", "persona")] == 1 and m.roles.replis[0]["role"] == "persona"


def test_persona_qui_fixe_son_moteur_ne_se_replie_jamais(config, vault, reg):
    m, avis_ = revue(config, vault, reg, fixe="rapide")
    assert avis_["verdict"] == "echec" and "quota" in avis_["points"][0]
    assert not reg["faux"].lances and not m.roles.replis  # INV-MOTEUR-1


# --- mandat et jardinage : tour éphémère, repli sur le moteur de la tâche ---------------------
def lancer(config, vault, reg, role):
    async def scenario():
        m = Moteur(config, vault, reg)
        m.soumettre("mere", "x", role=role)
        await finir(m)
        return m

    return executer(scenario())


def test_jardinage_part_sur_son_moteur_sans_toucher_la_session_de_la_tache(config, vault, reg):
    reg["rapide"].scenario = scenario_ok("r-9")
    m = lancer(config, vault, reg, "jardinage")
    t = vault.tache("mere")
    assert reg["rapide"].lances[0]["session"] is None and reg["rapide"].lances[0]["modele"] == "flash"
    assert not reg["faux"].lances and "session" not in t.fm  # la conversation de la tâche reste intacte
    assert m.roles.tours[("rapide", "jardinage")] == 1


def test_mandat_se_replie_sur_le_moteur_de_la_tache(config, vault, reg):
    reg["faux"].scenario = scenario_ok("s-2")
    m = lancer(config, vault, reg, "mandat")
    assert len(reg["rapide"].lances) == 1 and len(reg["faux"].lances) == 1
    assert vault.tache("mere").fm["session"] == "s-2"  # le repli est un tour ordinaire de la tâche
    assert m.roles.replis[0]["role"] == "mandat" and m.etat_de("mere") == "inactif"
    assert m.roles.tours[("faux", "tache")] == 1


def test_pas_de_repli_apres_un_outil_ni_sans_reglage(config, vault, reg):
    reg["rapide"].scenario = [Evenement("session", session="r"), Evenement("outil", texte="Write: x"),
                              Evenement("erreur", texte="429 quota")]
    m = lancer(config, vault, reg, "jardinage")
    assert not reg["faux"].lances and not m.roles.replis  # effet de bord possible : l'erreur remonte
    config.moteurs_par_role = {}
    lancer(config, vault, reg, "jardinage")
    assert reg["faux"].lances  # sans réglage : moteur de la tâche, comme avant
