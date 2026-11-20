"""Compactage automatique (INV-COMPACT-1) : seuil, héritage, traduction par harnais, repli, mesure."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from conftest import RENDU, ecrire, tache_md
from orchestrateur import compactage, fiches
from orchestrateur.config import ConfigCompactage
from orchestrateur.harnais import Evenement
from orchestrateur.harnais.agy import analyser as analyser_agy
from orchestrateur.harnais.claude import HarnaisClaude, _contexte
from orchestrateur.harnais.codex import HarnaisCodex, analyser as analyser_codex
from orchestrateur.harnais.opencode import analyser as analyser_opencode
from orchestrateur.moteur import Moteur

DONNEES = Path(__file__).parent / "donnees"


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


# --- fenêtre, seuil, configuration --------------------------------------------------------
def test_fenetre_par_modele_defauts_et_table_reglable():
    f = compactage.fenetre
    assert f("claude-opus-5-5") == 200_000 and f("sonnet") == 200_000
    assert f("opus[1m]") == 1_000_000  # la variante à un million l'emporte sur la famille
    assert f("gpt-6-astra@high") == 272_000  # l'effort n'entre pas dans la recherche
    assert f("gemini-3.8-flash-low") == 1_048_576
    assert f("modele-inconnu") == compactage.FENETRE_INCONNUE
    assert f("claude-opus-5-5", {"opus": 777}) == 777  # la table réglable prime
    assert f("claude-opus-5-5", {"claude": 1, "claude-opus": 2}) == 2  # motif le plus précis d'abord


def test_seuil_premier_atteint_du_pourcentage_et_du_plafond():
    assert compactage.seuil_jetons(45, 0, 1_000_000) == 450_000  # défaut : 45 % de un million
    assert compactage.seuil_jetons(45, 0, 200_000) == 90_000
    assert compactage.seuil_jetons(45, 300_000, 1_000_000) == 300_000  # le plafond est atteint d'abord
    assert compactage.seuil_jetons(45, 900_000, 1_000_000) == 450_000  # le pourcentage est atteint d'abord


def test_configuration_valide_ses_bornes():
    assert ConfigCompactage().pct == 45 and ConfigCompactage().plafond == 0
    for mauvais in ({"pct": 0}, {"pct": 101}, {"pct": "x"}, {"plafond": -1}, {"plafond": 1.5},
                    {"fenetres": {"m": 0}}, {"ordres": {"h": 3}}):
        with pytest.raises(ValueError):
            ConfigCompactage(**mauvais)


# --- héritage tâche -> projet -> général --------------------------------------------------
def test_heritage_tache_puis_projet_puis_general(config, vault, racine, faux):
    m = Moteur(config, vault, {"faux": faux})
    s = m.seuil_de(vault.tache("mere"), "faux", "")
    assert s["seuil"] == 90_000 and s["origine"] == {"pct": "general", "plafond": "general"}
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\nnom: Alpha\ncompactage_pct: 30\ncompactage_plafond: 50000\n---\n")
    s = m.seuil_de(vault.tache("mere"), "faux", "")
    assert s["pct"] == 30 and s["plafond"] == 50_000 and s["seuil"] == 50_000
    assert s["origine"] == {"pct": "projet", "plafond": "projet"}
    # Clés posées à la main dans la fiche (hors clés gérées, INV-VAULT-1) : la tâche prime, champ par champ.
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md", tache_md(extra="compactage_pct: 80\n", titre="Mère"))
    s = m.seuil_de(vault.tache("mere"), "faux", "")
    assert s["pct"] == 80 and s["origine"] == {"pct": "tache", "plafond": "projet"} and s["seuil"] == 50_000
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md", tache_md(extra="compactage_pct: beaucoup\n", titre="Mère"))
    assert m.seuil_de(vault.tache("mere"), "faux", "")["pct"] == 30
    assert m.seuil_de(vault.tache("doublon"), "faux", "opus[1m]")["seuil"] == 450_000  # autre projet : général


# --- traduction par harnais ---------------------------------------------------------------
def test_codex_recoit_la_limite_en_jetons_calculee_depuis_la_fenetre():
    h = HarnaisCodex({"commande": sys.executable})  # un exécutable existant : le test ne suppose pas codex installé
    assert not any("auto_compact" in a for a in h._argv(None, False, "gpt-6"))
    h.compactage = (45.0, 450_000)
    argv = h._argv("th-1", False, "gpt-6")
    assert argv[argv.index("-c") + 1] == "model_auto_compact_token_limit=450000"
    assert argv.index("resume") < argv.index("--json") < argv.index("-c")


def test_claude_recoit_le_pourcentage_par_variable_d_environnement():
    h = HarnaisClaude({})
    assert h._env_compactage() == {}
    h.compactage = (45.0, 90_000)
    assert h._env_compactage() == {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "45"}
    h.compactage = (22.4, 44_800)  # plafond absolu converti en % de la fenêtre
    assert h._env_compactage() == {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "22"}


def test_moteur_pose_le_seuil_sur_l_adaptateur_du_tour(config, vault, racine, faux):
    posees = []
    classe = type("Faux3", (faux,), {"lances": [], "arrets": []})
    origine = classe.lancer

    async def lancer(self, *a, **k):
        posees.append(self.compactage)
        async for ev in origine(self, *a, **k):
            yield ev
    classe.lancer = lancer
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md",
           tache_md(extra="compactage_pct: 50\ncompactage_plafond: 60000\n", titre="Mère"))

    async def scenario():
        m = Moteur(config, vault, {"faux": classe})
        m.soumettre("mere", "go")
        await finir(m)
    asyncio.run(scenario())
    assert posees == [(30.0, 60_000)]  # 60 000 jetons sur 200 000 : 30 % de la fenêtre


# --- mesures lues dans les flux des harnais ----------------------------------------------
def test_contexte_claude_somme_entree_et_caches_du_dernier_appel():
    u = {"usage": {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 90}}
    assert _contexte(u) == 1100 and _contexte({}) is None and _contexte(None) is None


def test_mesure_des_flux_codex_opencode_agy_observes_en_reel():
    ev = analyser_codex({"type": "turn.completed", "usage": {"input_tokens": 25313}}, {})[0]
    assert ev.type == "fin" and ev.mesure["contexte"] == 25313

    etat = {}
    for ligne in (DONNEES / "opencode-outil.jsonl").read_text("utf-8").splitlines():
        analyser_opencode(json.loads(ligne), etat)
    assert etat["contexte"] == 233 + 30720  # dernier appel : entrée + cache lu

    etat, fin = {}, None
    for ligne in (DONNEES / "agy-reprise-outil.jsonl").read_text("utf-8").splitlines():
        for ev in analyser_agy(json.loads(ligne), etat):
            fin = ev if ev.type == "fin" else fin
    assert fin.mesure["contexte"] == 2226 + 7063  # dernier appel, pas le cumul du tour


# --- repli commun : ordre de compactage entre deux tours ---------------------------------
def _fin(contexte):
    return [Evenement("session", session="s-1"), Evenement("texte", texte="ok"),
            Evenement("fin", session="s-1", texte=RENDU, mesure={"contexte": contexte, "cout": 0.5})]


def _faux_repli(faux, contextes, **attrs):
    """Faux harnais sans mécanisme natif ; chaque lancement rend le contexte suivant de la liste."""
    suite = iter(contextes)
    classe = type("FauxRepli", (faux,), {"lances": [], "arrets": [], "compactage_natif": False,
                                         "ordre_compactage": "/compact", **attrs})
    origine = classe.lancer

    async def lancer(self, message, **k):
        self.scenario = _fin(next(suite))
        async for ev in origine(self, message, **k):
            yield ev
    classe.lancer = lancer
    return classe


def _jouer(config, vault, classe, messages):
    async def scenario():
        m = Moteur(config, vault, {"faux": classe})
        for texte in messages:
            m.soumettre("mere", texte)
            await finir(m)
        return m
    return asyncio.run(scenario())


def _mesures(m):
    """Lignes de tour (les lignes `type` : attente, gel, sont de l'instrumentation)."""
    tous = [json.loads(ligne) for ligne in m.mesures.fichier.read_text("utf-8").splitlines()]
    return [t for t in tous if "type" not in t]


def test_repli_envoie_l_ordre_de_compactage_puis_rappelle_la_fiche(config, vault, faux):
    classe = _faux_repli(faux, [150_000, 20_000, 30_000])  # 150 000 > seuil de 90 000
    m = _jouer(config, vault, classe, ["premier", "second"])
    envoyes = [lance["message"] for lance in classe.lances]
    assert envoyes[0].endswith("premier") and envoyes[1] == "/compact"
    assert "vient d'être compacté" in envoyes[2] and envoyes[2].endswith("second")
    assert str(vault.tache("mere").chemin) in envoyes[2]
    tours = _mesures(m)
    assert [t["compactage"] for t in tours] == [False, True, False]
    assert [t["apres_compactage"] for t in tours] == [False, False, True]  # le tour suivant est marqué
    assert tours[0]["contexte"] == 150_000 and tours[0]["seuil"] == 90_000 and tours[0]["cout"] == 0.5


def test_repli_n_envoie_rien_sous_le_seuil(config, vault, faux):
    classe = _faux_repli(faux, [80_000, 80_000])
    _jouer(config, vault, classe, ["premier", "second"])
    assert [lance["message"].endswith(t) for lance, t in zip(classe.lances, ["premier", "second"])] == [True, True]
    assert len(classe.lances) == 2


def test_pas_de_repli_pour_un_harnais_natif_ni_sans_ordre(config, vault, faux):
    for attrs in ({"compactage_natif": True}, {"ordre_compactage": ""}):
        classe = _faux_repli(faux, [150_000, 150_000], **attrs)
        _jouer(config, vault, classe, ["premier", "second"])
        assert len(classe.lances) == 2


def test_ordre_reglable_par_la_configuration(config, vault, faux):
    config.compactage = ConfigCompactage(ordres={"faux": "/condense"})
    classe = _faux_repli(faux, [150_000, 1, 1])
    _jouer(config, vault, classe, ["premier", "second"])
    assert classe.lances[1]["message"] == "/condense"


def test_pas_de_second_ordre_avant_que_le_contexte_ait_redepasse_le_seuil(config, vault, faux):
    classe = _faux_repli(faux, [150_000, 120_000, 120_000, 120_000, 120_000])  # le compactage ne réduit rien
    _jouer(config, vault, classe, ["a", "b", "c"])
    envoyes = [lance["message"] for lance in classe.lances]
    # a ; (ordre, b) ; (ordre, c) : un ordre par message qui suit un dépassement, jamais en boucle sur le même
    assert envoyes.count("/compact") == 2 and len(envoyes) == 5


def test_l_ordre_de_compactage_ne_touche_ni_statut_ni_fiche(config, vault, faux):
    classe = _faux_repli(faux, [150_000, 10_000, 10_000])

    async def scenario():
        m = Moteur(config, vault, {"faux": classe})
        m.soumettre("mere", "premier")
        await finir(m)
        avant = (vault.tache("mere").statut, fiches_lire(vault, "mere"))
        m.soumettre("mere", "second")  # précédé de l'ordre, dont le texte rendu n'est pas une fiche
        await finir(m)
        return m, avant
    m, avant = asyncio.run(scenario())
    assert any(t["compactage"] for t in _mesures(m))
    assert (vault.tache("mere").statut, fiches_lire(vault, "mere")) == avant


def fiches_lire(vault, ident):
    return fiches.lire_fiche(fiches.lire(vault.tache(ident).chemin))


# --- journal de mesure --------------------------------------------------------------------
def test_mesure_d_un_tour_en_echec_porte_le_signal(config, vault, faux):
    classe = type("FauxEchec", (faux,), {"lances": [], "arrets": [], "scenario": [Evenement(
        "erreur", texte="boom")]})
    m = _jouer(config, vault, classe, ["go"])
    (t,) = _mesures(m)
    assert t["signaux"] == ["tour_en_echec"] and t["contexte"] is None and t["harnais"] == "faux"
    assert t["duree_s"] >= 0 and t["tache"] == "mere" and t["fenetre"] == 200_000 and not t["compactage"]


def test_mesure_marque_la_baisse_de_contexte_d_un_compactage_natif(config, vault, faux):
    classe = _faux_repli(faux, [150_000, 40_000], compactage_natif=True)  # le harnais a compacté seul
    m = _jouer(config, vault, classe, ["a", "b"])
    assert [t["apres_compactage"] for t in _mesures(m)] == [False, True]


def test_synthese_par_harnais_et_tranche_de_contexte(tmp_path):
    j = compactage.Mesures(tmp_path / "m.jsonl")
    for h, ctx, d, sig, apres, comp in [
            ("claude", 30_000, 10, [], False, False), ("claude", 40_000, 20, ["tour_en_echec"], False, False),
            ("claude", 150_000, 60, [], True, False), ("claude", 90_000, 5, [], False, True),
            ("codex", None, 7, ["relance"], False, False), ("codex", 500_000, 9, ["interrompu"], False, False)]:
        j.ajouter({"harnais": h, "contexte": ctx, "duree_s": d, "signaux": sig, "apres_compactage": apres,
                   "compactage": comp})
    s = {(x["harnais"], x["tranche"]): x for x in j.synthese()}
    assert s["claude", "0–50 k"] == {"harnais": "claude", "tranche": "0–50 k", "tours": 2,
                                     "duree_moyenne_s": 15.0, "taux_echec": 0.5, "apres_compactage": 0,
                                     "compactages": 1}
    assert s["claude", "100–200 k"]["apres_compactage"] == 1
    assert s["codex", "inconnue"]["taux_echec"] == 1.0
    assert s["codex", "≥ 400 k"]["taux_echec"] == 0.0  # « interrompu » est un geste humain, pas un échec
    assert [x["tranche"] for x in j.synthese() if x["harnais"] == "claude"] == ["0–50 k", "100–200 k"]


def test_journal_de_mesure_absent_ou_abime_se_lit_vide(tmp_path):
    j = compactage.Mesures(tmp_path / "rien" / "m.jsonl")
    assert j.lire() == [] and j.synthese() == []
    (tmp_path / "m.jsonl").write_text('pas du json\n{"harnais": "a", "contexte": 1}\n[1]\n', encoding="utf-8")
    assert len(compactage.Mesures(tmp_path / "m.jsonl").lire()) == 1


# --- routes -------------------------------------------------------------------------------
def test_routes_lire_regler_persister_et_refuser(config, vault, faux, tmp_path):
    from fastapi.testclient import TestClient
    from orchestrateur import api
    chemin = tmp_path / "config.toml"
    chemin.write_text("[moteur]\nsauts_max = 3\n", encoding="utf-8")
    config.chemin = chemin
    c = TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url="http://127.0.0.1:8399")
    h = {"X-Orchestrateur": "1"}
    lu = c.get("/api/compactage").json()
    assert lu["pct"] == 45 and lu["plafond"] == 0 and lu["mesure"] == []
    assert lu["fenetres"]["claude"] == 200_000 and lu["harnais"]["faux"]["natif"] is False
    r = c.put("/api/compactage", headers=h, json={"pct": 50, "plafond": 300_000})
    assert r.status_code == 200 and r.json()["pct"] == 50 and config.compactage.plafond == 300_000
    texte = chemin.read_text("utf-8")
    assert "[compactage]" in texte and "pct = 50.0" in texte and "plafond = 300000" in texte
    assert "sauts_max = 3" in texte
    for mauvais in ({"pct": 0}, {"pct": 101}, {"plafond": -5}):
        assert c.put("/api/compactage", headers=h, json=mauvais).status_code == 400
        assert config.compactage.pct == 50 and config.compactage.plafond == 300_000  # rien n'a changé
    assert chemin.read_text("utf-8") == texte  # rien d'écrit sur une valeur refusée


def test_signaux_porte_rouge_et_terminee_refusee_quand_le_controle_requis_echoue(config, vault, faux):
    classe = type("FauxCtl", (faux,), {"lances": [], "arrets": []})
    classe.scenario = [Evenement("session", session="s-1"), Evenement(
        "fin", session="s-1", mesure={"contexte": 5, "cout": None}, texte=(
            "Fait.\n<fiche>\nstatut: terminee\nfait: x\nsituation: y\nreste: rien\nprochain_pas: z\n</fiche>"))]

    async def scenario():
        m = Moteur(config, vault, {"faux": classe})

        async def controle(ident, final, erreur, tour):  # le contrôle requis échoue pour ce tour
            m._verdicts_tour[ident] = {"verdict": "echoue"}
        m._controler = controle
        m.soumettre("mere", "go")
        await finir(m)
        return m
    m = asyncio.run(scenario())
    (t,) = _mesures(m)
    assert t["signaux"] == ["porte_rouge", "terminee_refusee"] and vault.tache("mere").statut == "retour-humain"


def test_tour_de_compactage_repris_apres_redemarrage_reste_un_ordre_de_compactage(config, vault, faux):
    from orchestrateur import reprise
    classe = _faux_repli(faux, [1])
    vault.modifier("mere", {"session": "s-1"})

    async def scenario():
        m = Moteur(config, vault, {"faux": classe})
        m.interrompus["mere"] = {"tache": "mere", "texte": "/compact", "role": "compactage", "sauts": 0}
        reprise._resoumettre(m, "mere", "redémarrage du serveur", auto=True)
        await finir(m)
        return m
    m = asyncio.run(scenario())
    assert [lance["message"] for lance in classe.lances] == ["/compact"]  # ni message de reprise, ni rappel
    assert _mesures(m)[0]["compactage"] is True


def test_le_pourcentage_claude_est_transmis_au_codespace():
    from orchestrateur.harnais import distant
    h = HarnaisClaude({})
    h.compactage = (45.0, 90_000)
    script = distant.script_distant(["claude", "-p"], {"ORCH_URL": "x", **h._env_compactage()}, "~", "claude", "cs")
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=45" in script and "ORCH_URL" not in script  # INV-CODESPACE-1
