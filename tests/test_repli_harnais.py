"""Harnais absent du poste (INV-QUOTA-1), cause « Harnais non installé » (INV-INCIDENT-1), file d'une
tâche bloquée retenue puis rejouée (INV-EXEC-11), reconnaissance Telegram sans second lecteur
(INV-TELEGRAM-5). Faux harnais, faux Telegram et vault temporaire seulement."""

import pytest

from orchestrateur import echecs, incidents, roles, telegram_connexion
from orchestrateur.config import ConfigRole
from orchestrateur.moteur import Moteur
from conftest import FauxHarnais, scenario_ok
from test_moteur import executer, finir
from test_telegram import CHAT, relever, tg, une_releve  # noqa: F401 — `tg` est une fixture

ABSENT = FileNotFoundError("exécutable introuvable : faux")


def harnais(nom, scenario):
    return type(nom.capitalize(), (FauxHarnais,), {"nom": nom, "commande": nom, "scenario": scenario,
                                                    "lances": [], "arrets": [], "liberer": None})


@pytest.fixture
def poste(monkeypatch):
    """Exécutables présents sur le poste ; les autres lèvent comme `processus.resoudre`."""
    presents = {"claude", "secours"}

    def resoudre(commande):
        if commande not in presents:
            raise FileNotFoundError(f"exécutable introuvable : {commande}")
        return [commande]

    monkeypatch.setattr(roles, "resoudre", resoudre)
    return presents


# --- point 2 : la cause ------------------------------------------------------------------------
def test_harnais_absent_classe_non_installe_et_jamais_reseau():
    motif = "FileNotFoundError: exécutable introuvable : agy"
    assert not echecs.RESEAU.search(motif) and echecs.est_introuvable(motif)
    assert incidents.classer(motif)[:2] == ("absent", "Assistant IA non installé")
    assert incidents.classer("getaddrinfo ENOTFOUND api.example.com")[0] == "reseau"  # le réseau reste reconnu


def test_geste_nomme_le_harnais_a_installer(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    inc = m.incidents.noter("mere", "agy", "FileNotFoundError: exécutable introuvable : agy", "rien")
    assert inc["geste"] == "Installer agy (Réglages → Installation) ou retirer agy de [credits]."


# --- point 1 : jamais choisi, et bascule s'il l'était ----------------------------------------
def test_choix_d_un_role_et_equilibrage_ecartent_le_harnais_non_installe(config, vault, poste):
    config.harnais = {"agy": {"familles": {"rapide": "flash"}}, "claude": {"familles": {"rapide": "haiku"}}}
    config.credits = {**config.credits, "rapide": ["agy", "claude"]}
    config.moteurs_par_role = {"tri": ConfigRole(famille="rapide")}
    reg = {"agy": harnais("agy", []), "claude": harnais("claude", [])}
    r = roles.Roles(config, reg)
    assert not r.installe("agy") and r.installe("claude") and r.installe("inconnu")
    assert r.choisir("tri") == roles.Choix("claude", "haiku")
    m = Moteur(config, vault, reg)
    assert m.economie._candidats("claude", "rapide") == ["claude"]  # agy n'est jamais candidat


def test_harnais_absent_bascule_une_fois_meme_avec_un_modele_pose(config, vault, poste):
    config.harnais = {"faux": {"familles": {"rapide": "petit"}}, "secours": {"familles": {"rapide": "vif"}}}
    config.credits = {**config.credits, "rapide": ["faux", "secours"]}
    faux, secours = harnais("faux", [ABSENT]), harnais("secours", scenario_ok("s-2"))
    vault.modifier("mere", {"harnais": "faux", "modele": "petit"})  # posé à la création (tri Telegram)

    async def scenario():
        m = Moteur(config, vault, {"faux": faux, "secours": secours})
        m.soumettre("mere", "travaille")
        await finir(m)
        return m

    m = executer(scenario())
    assert len(secours.lances) == 1 and "travaille" in secours.lances[0]["message"]
    fm = vault.tache("mere").fm
    assert (fm["harnais"], fm["modele"], fm.get("moteur_impose")) == ("secours", "vif", None)
    assert not m.quota.epuise("faux")  # un harnais absent n'a pas de quota
    inc = m.incidents.public()[0]
    assert inc["cause"] == "absent" and inc["action"] == "assistant IA non installé : relancé une fois sur secours (vif)"
    assert not m.retenus


# --- point 3 : la file d'une tâche bloquée attend, puis repart -----------------------------------
def test_messages_recus_pendant_le_blocage_sont_rejoues_au_deblocage(config, vault, poste):
    config.harnais = {"faux": {}}  # aucun secours possible
    faux = harnais("faux", [ABSENT])

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "premier")
        await finir(m)
        m.soumettre("mere", "second")  # arrivé pendant le blocage (Telegram) : gardé, pas lancé
        await finir(m)
        etat = (len(faux.lances), [e.texte for e in m.files["mere"]], m.etat_de("mere"))
        poste.add("faux")
        faux.scenario = scenario_ok("s-1")
        m.changer_moteur("mere", "faux")  # geste humain : la file repart dans l'ordre
        await finir(m)
        return m, etat

    m, (lances, file, etat) = executer(scenario())
    assert lances == 1 and file == ["premier", "second"] and etat == "inactif"
    assert m.incidents.public()[0]["action"] == "tâche bloquée, message gardé en file jusqu'au déblocage"
    assert [x["message"] for x in faux.lances[1:]] == ["premier", "second"]
    assert not m.files["mere"] and not m.retenus


def test_message_humain_debloque_et_tache_close_vide_la_file(config, vault, poste):
    config.harnais = {"faux": {}}
    faux = harnais("faux", [ABSENT])

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "premier")
        m.soumettre("enfant", "a")
        await finir(m)
        poste.add("faux")
        faux.scenario = scenario_ok("s-1")
        m.soumettre("mere", "relance", humain=True)  # message tapé dans l'interface
        await finir(m)
        vault.poser_statut("enfant", "fait", humain=True)
        m.liberer("enfant")  # tâche close : la file retenue tombe, rien ne part
        await finir(m)
        return m

    m = executer(scenario())
    assert [x["message"] for x in faux.lances[2:]] == ["premier", "relance"]
    assert not m.files["enfant"] and not m.retenus and len(faux.lances) == 4


# --- point 4 : « Me reconnaître » ne double pas la boucle du connecteur -----------------------------
def test_reconnaissance_lit_les_discussions_vues_par_la_boucle_sans_getupdates(config, vault, faux, tg):
    tg.message(1, chat="777", text="bonjour", )
    tg.majs[-1]["message"]["chat"].update(first_name="Ada", username="ada")
    c, _ = relever(config, vault, faux, une_releve)
    lectures = sum(1 for meth, _ in tg.requetes if meth == "getUpdates")
    r = telegram_connexion.reconnaitre(c.client(), dict(c.vues))
    assert r["discussions"] == [{"id": "777", "nom": "Ada (@ada)"}]  # hors liste blanche, mais vue
    assert sum(1 for meth, _ in tg.requetes if meth == "getUpdates") == lectures  # aucun second lecteur
    assert CHAT not in c.vues
