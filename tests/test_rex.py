"""INV-REX-1 : passe de REX après validation — déclenchement, absence de boucle, dérogation, interrupteur,
conversation triviale, trace dans la fiche, effort du modèle, relance manuelle."""

import asyncio

from conftest import FauxHarnais, ecrire, tache_md
from orchestrateur import rex
from orchestrateur.config import ConfigRole
from orchestrateur.harnais import Evenement, Message
from orchestrateur.moteur import Moteur

BLOC = ("Fait.\n<rex>\nbilan: deux détours sur les chemins\nmodifie:\n- ~/.claude/skills/x/SKILL.md — "
        "précisé\npropose:\n- aucun\n</rex>")
SESSION = "session: s-1\nharnais: faux\n"


def faux_rex(long=True):
    msgs = [Message("assistant", f"m{i}", ["Read"] if i else [], "2026-11-28T10:00:00") for i in range(5)]
    return type("FauxRex", (FauxHarnais,), {
        "scenario": [Evenement("session", session="r-1"), Evenement("fin", session="r-1", texte=BLOC)],
        "lances": [], "arrets": [], "liberer": None,
        "transcript": lambda self, session, limite: msgs if long else msgs[:1]})


def lancer(config, vault, faux, geste):
    config.moteurs_par_role["rex"] = ConfigRole(harnais="faux", modele="m")

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        geste(m)
        for _ in range(20):
            en_fond = list(m.rex._fond)
            if not en_fond:
                break
            await asyncio.gather(*en_fond, return_exceptions=True)
        return m

    return asyncio.run(scenario())


def tache(racine, statut="fait", extra=SESSION, ident="t"):
    ecrire(racine, f"Projets/C1-Alpha/taches/{ident}.md", tache_md(statut=statut, extra=extra, titre="T"))


def test_validation_humaine_declenche_un_rex_et_le_consigne(racine, config, vault):
    tache(racine, statut="en-cours")
    faux = faux_rex()
    m = lancer(config, vault, faux, lambda m: m.vault.poser_statut("t", "fait", humain=True))
    assert len(faux.lances) == 1 and faux.lances[0]["env"]["ORCH_PERSONA"] == "rex"
    assert m.rex.faits["t"]["issue"] == "fait"
    texte = vault.tache("t").chemin.read_text(encoding="utf-8")
    assert "REX : deux détours sur les chemins" in texte and "SKILL.md" in texte
    assert vault.tache("t").statut == "fait"  # le REX ne pose aucun statut


def test_pas_de_boucle_un_seul_rex_par_tache(racine, config, vault):
    tache(racine, statut="en-cours")
    faux = faux_rex()

    def gestes(m):
        m.vault.poser_statut("t", "fait", humain=True)
        m.vault.poser_statut("t", "cloture", humain=True)  # revalidation immédiate : déjà noté

    m = lancer(config, vault, faux, gestes)
    assert len(faux.lances) == 1
    assert m.rex.declencher("t") == "deja_fait"
    lancer(config, vault, faux, lambda m: m.vault.poser_statut("t", "fait", humain=True))
    assert len(faux.lances) == 1  # réouverture cloture -> fait : jamais un REX


def test_fin_du_tour_rex_ne_redeclenche_rien(racine, config, vault):
    tache(racine, statut="a-faire")
    faux = faux_rex()
    m = lancer(config, vault, faux, lambda m: m.vault.poser_statut("t", "cloture"))  # clôture automatique
    assert len(faux.lances) == 1 and not m.rex.en_cours and not m.rex._fond


def test_derogation_et_interrupteur_et_agent(racine, config, vault):
    tache(racine, statut="en-cours", extra=SESSION + "rex: non\n", ident="d")
    tache(racine, statut="en-cours", ident="i")
    tache(racine, statut="en-cours", ident="a")
    faux = faux_rex()
    config.validation.rex = False
    lancer(config, vault, faux, lambda m: (m.vault.poser_statut("d", "fait", humain=True),
                                           m.vault.poser_statut("i", "fait", humain=True)))
    assert faux.lances == []
    config.validation.rex = True
    m = lancer(config, vault, faux, lambda m: (m.vault.poser_statut("d", "fait", humain=True),
                                               m.vault.poser_statut("a", "fait")))  # agent : pas une validation
    assert faux.lances == [] and m.rex.refus("d") == "derogation"


def test_conversation_triviale_ou_sans_session_ignoree(racine, config, vault):
    tache(racine, statut="en-cours", ident="c")
    tache(racine, statut="en-cours", extra="", ident="n")
    faux = faux_rex(long=False)
    m = lancer(config, vault, faux, lambda m: (m.vault.poser_statut("c", "fait", humain=True),
                                               m.vault.poser_statut("n", "fait", humain=True)))
    assert faux.lances == [] and m.rex.faits["c"]["issue"] == "triviale" and "n" not in m.rex.faits
    assert m.rex.refus("n", force=True) == "sans_session"


def test_echec_du_tour_est_un_incident_sans_relance(racine, config, vault):
    tache(racine, statut="en-cours")
    faux = faux_rex()
    faux.scenario = [Evenement("erreur", texte="boom")]
    m = lancer(config, vault, faux, lambda m: m.vault.poser_statut("t", "fait", humain=True))
    assert m.rex.faits["t"]["issue"] == "echec" and len(faux.lances) == 1
    assert m.incidents.liste[-1]["role"] == "rex"


def test_effort_ajoute_au_modele_claude_seulement(racine, config, vault):
    m = Moteur(config, vault, {"faux": faux_rex()})
    config.moteurs_par_role["rex"] = ConfigRole(harnais="claude", modele="opus", repli=False)
    assert m.rex.choix().modele == "opus@high"
    config.moteurs_par_role["rex"] = ConfigRole(harnais="faux", modele="m")
    assert m.rex.choix().modele == "m"


def test_analyser_bloc_tolerant():
    r = rex.analyser(BLOC)
    assert r["bilan"].startswith("deux détours") and len(r["modifie"]) == 1 and r["propose"] == []
    assert rex.analyser("sans bloc")["bilan"] == "sans bloc"
