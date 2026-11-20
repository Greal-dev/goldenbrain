"""Curseur Performance ↔ Économie (INV-ECO-1, INV-ECO-2) : défaut explicite, profil, escalade et
descente, curseur, indice de rythme et hystérésis, équilibrage entre fournisseurs, moteur imposé,
aucune bascule en cours de conversation, proposition de bascule, mesure par harnais, routes."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, conso, economie
from orchestrateur.conso import Conso, Fenetre
from orchestrateur.moteur import Moteur
from conftest import ecrire, tache_md

FAMILLES = {"rapide": "petit", "sonnet": "moyen", "opus": "grand"}
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def m(config, vault, faux):
    config.harnais = {"faux": {"familles": FAMILLES}, "autre": {"familles": {"sonnet": "autre-moyen"}}}
    config.credits = {f: ["faux", "autre"] for f in FAMILLES}
    return Moteur(config, vault, {"faux": faux, "autre": faux})


def tourner(mot, ident, texte="go"):
    async def scenario():
        mot.soumettre(ident, texte)
        while any(not b.done() for b in mot.boucles.values()):
            await asyncio.gather(*mot.boucles.values(), return_exceptions=True)
    asyncio.run(scenario())


def fenetre(part, ecoule, duree=7 * 86400):
    """Fenêtre dont `ecoule` (0..1) du temps est passé et `part` du crédit consommée."""
    return Fenetre("hebdomadaire", part, duree, time.time() + (1 - ecoule) * duree)


def quotas(mot, monkeypatch, par_harnais):
    monkeypatch.setattr(mot.economie.conso, "fenetres", lambda h: par_harnais.get(h, []))


# --- défaut explicite et profil -----------------------------------------------------------
def test_tache_sans_modele_part_sur_la_famille_par_defaut_jamais_le_defaut_implicite(m, faux, vault):
    tourner(m, "mere")
    assert faux.lances[0]["modele"] == "moyen"
    assert vault.tache("mere").fm["moteur_motif"].startswith("sonnet — famille par défaut")


def test_modele_pose_a_la_main_l_emporte(m, faux):
    m.changer_moteur("mere", modele="grand-special")
    tourner(m, "mere")
    assert faux.lances[0]["modele"] == "grand-special"


@pytest.mark.parametrize("texte,depot,oracle,attendu", [
    ("Trier les mails de la semaine", False, False, "rapide"),
    ("Refonte de l'architecture du moteur", False, False, "opus"),
    ("Corriger l'affichage", True, False, "sonnet"),
    ("Rédiger une note", False, False, "sonnet"),
    ("Refonte du module", True, True, "sonnet"),  # descente : le contrôle requis sert d'oracle
    ("Rédiger " + "x" * 7000, False, False, "opus"),  # tâche longue : un cran au-dessus
    ("Intégrer les branches du lot dans mvp " + "x" * 7000, True, False, "sonnet"),  # jamais opus : on délègue
    ("Rejeu de la porte après fusion des correctifs", True, False, "sonnet"),
])
def test_profil_regles_deterministes(texte, depot, oracle, attendu):
    assert economie.profil(texte, depot, oracle, "sonnet")[0] == attendu


def test_escalade_apres_deux_echecs_puis_retour_apres_succes(m, vault):
    t = vault.tache("mere")
    m.economie.issue("mere", "bloque", None)
    assert m.economie.decider(t).famille == "sonnet"
    m.economie.issue("mere", "retour-humain", "x\n<fiche>\nstatut: terminee\n</fiche>")  # « Terminée » refusée
    d = m.economie.decider(t)
    assert (d.famille, d.modele) == ("opus", "grand") and "escalade après 2 échecs" in d.motif
    m.economie.issue("mere", "fait", "x\n<fiche>\nstatut: terminee\n</fiche>")
    assert m.economie.decider(t).famille == "sonnet"
    assert json.loads(m.economie.fichier.read_text(encoding="utf-8")) == {}


# --- curseur ------------------------------------------------------------------------------
@pytest.mark.parametrize("position,famille", [("economie_max", "rapide"), ("economie", "rapide"),
                                               ("performance", "opus"), ("performance_max", "opus")])
def test_curseur_decale_la_famille(m, vault, position, famille):
    m.config.economie.position = position
    assert m.economie.decider(vault.tache("mere")).famille == famille


def test_position_de_la_tache_puis_du_contexte_l_emportent(m, vault, racine):
    t = vault.tache("mere")
    assert m.economie.position(t) == "intelligent"
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nparent: \"[[Operation-X]]\"\neconomie: performance\n---\n")
    assert m.economie.position(t) == "performance"
    t.fm["economie"] = "economie_max"
    assert m.economie.position(t) == "economie_max"


# --- indice de rythme et hystérésis -------------------------------------------------------
def test_rythme_absent_si_fenetre_trop_jeune_ou_renouvelee():
    now = time.time()
    assert fenetre(0.5, 0.5).rythme(now) == pytest.approx(1.0, rel=0.01)
    assert fenetre(0.1, 0.01).rythme(now) is None
    assert Fenetre("5 h", 0.9, 18000, now - 10).rythme(now) is None


def test_intelligent_sans_donnee_reste_neutre(m, monkeypatch):
    quotas(m, monkeypatch, {})
    assert m.economie.intelligent("faux") == (0, "pas de donnée de crédit d'utilisation fiable pour faux")


def test_intelligent_glisse_vers_economie_puis_hysteresis(m, monkeypatch):
    quotas(m, monkeypatch, {"faux": [fenetre(0.6, 0.5)]})  # P = 1,2 > 1,15
    assert m.economie.intelligent("faux")[0] == -1
    quotas(m, monkeypatch, {"faux": [fenetre(0.555, 0.5)]})  # P = 1,11 : reste en économie
    assert m.economie.intelligent("faux")[0] == -1
    quotas(m, monkeypatch, {"faux": [fenetre(0.5, 0.5)]})  # P = 1,0 : retour au neutre
    assert m.economie.intelligent("faux")[0] == 0


def test_intelligent_passe_en_performance_pres_du_renouvellement(m, monkeypatch, vault):
    quotas(m, monkeypatch, {"faux": [fenetre(0.6, 0.9)]})  # P = 0,67, 10 % de la semaine restant
    pas, motif = m.economie.intelligent("faux")
    assert pas == 1 and motif.startswith("Intelligent → Performance : 40 % du crédit hebdomadaire restant")
    assert m.economie.decider(vault.tache("mere")).famille == "opus"
    quotas(m, monkeypatch, {"faux": [fenetre(0.3, 0.5)]})  # sous-consommation loin du renouvellement
    assert m.economie.intelligent("faux")[0] == 0


# --- équilibrage entre fournisseurs -------------------------------------------------------
def test_tache_neuve_part_sur_le_fournisseur_le_moins_tendu(m, monkeypatch, vault, faux):
    quotas(m, monkeypatch, {"faux": [fenetre(0.82, 0.5)], "autre": [fenetre(0.3, 0.5)]})
    m.config.economie.position = "economie"
    d = m.economie.decider(vault.tache("mere"))
    assert d.harnais == "autre" and "Prévu : faux ; parti sur autre : faux à 82 %" in d.motif
    m.config.economie.position = "performance"  # hors positions d'équilibrage : le prévu reste
    assert m.economie.decider(vault.tache("mere")).harnais == "faux"


def test_pas_de_bascule_sans_donnee_sur_le_prevu(m, monkeypatch, vault):
    quotas(m, monkeypatch, {"autre": [fenetre(0.1, 0.5)]})
    assert m.economie.decider(vault.tache("mere")).harnais == "faux"


def test_moteur_impose_jamais_rebascule(m, monkeypatch, vault):
    quotas(m, monkeypatch, {"faux": [fenetre(0.9, 0.5)], "autre": [fenetre(0.1, 0.5)]})
    m.changer_moteur("mere", harnais="faux")
    assert vault.tache("mere").fm["moteur_impose"] == "oui"
    assert m.economie.decider(vault.tache("mere")).harnais == "faux"
    m.changer_moteur("mere", harnais="", modele="")  # retour au défaut : l'imposition tombe
    assert "moteur_impose" not in vault.tache("mere").fm


def test_conversation_commencee_garde_son_harnais_et_propose_la_bascule(m, monkeypatch, vault, faux):
    tourner(m, "mere")  # la session s-1 est écrite
    quotas(m, monkeypatch, {"faux": [fenetre(0.9, 0.5)], "autre": [fenetre(0.1, 0.5)]})
    tourner(m, "mere")
    assert [x["session"] for x in faux.lances] == [None, "s-1"]
    assert vault.tache("mere").fm["harnais"] == "faux"
    d = m.economie.decider(vault.tache("mere"))
    assert d.harnais == "faux" and d.bascule["vers"] == "autre"


# --- mesure -------------------------------------------------------------------------------
def test_mesure_claude_et_codex_cumulees_par_harnais(config):
    c = Conso(config)
    c.mesurer("claude", {"type": "result", "total_cost_usd": 0.5,
                         "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 7}})
    c.mesurer("codex", {"type": "turn.completed", "usage": {"input_tokens": 40, "output_tokens": 4}})
    c.mesurer("agy", {"type": "fin"})  # format non vérifié : rien n'est inventé
    c.mesurer("claude", {"type": "assistant"})
    assert c.periode() == {"claude": {"tours": 1, "entree": 100, "sortie": 7, "cout": 0.5},
                           "codex": {"tours": 1, "entree": 40, "sortie": 4, "cout": 0.0}}


def test_quotas_codex_lus_dans_le_journal_de_session(config, tmp_path):
    j = tmp_path / "sessions" / "2026" / "11" / "15" / "rollout-x.jsonl"
    j.parent.mkdir(parents=True)
    rl = {"primary": {"used_percent": 40.0, "window_minutes": 300, "resets_at": 1794771165},
          "secondary": {"used_percent": 26.0, "window_minutes": 10080, "resets_at": 1794864058}}
    j.write_text('{"type":"x"}\n' + json.dumps({"type": "event_msg", "payload": {"type": "token_count",
                                                                               "rate_limits": rl}}) + "\n", encoding="utf-8")
    config.harnais = {"codex": {"transcripts": str(tmp_path / "sessions")}}
    f = Conso(config).fenetres("codex")
    assert [(x.nom, x.part, x.duree_s) for x in f] == [("5 h", 0.4, 18000), ("hebdomadaire", 0.26, 604800)]


def test_quotas_fichier_au_format_de_la_ligne_d_etat(config, tmp_path):
    p = tmp_path / "rl.json"
    p.write_text(json.dumps({"rate_limits": {"five_hour": {"used_percentage": 12, "resets_at": 2e9}}}), encoding="utf-8")
    config.economie.quotas = {"claude": {"source": "fichier", "chemin": str(p)}}
    assert [(f.nom, f.part) for f in Conso(config).fenetres("claude")] == [("5 h", 0.12)]
    p.write_text("illisible", encoding="utf-8")
    c = Conso(config)
    assert c.fenetres("claude") == []  # INV-ECO-2


def test_sans_source_aucune_fenetre(config):
    assert Conso(config).fenetres("claude") == [] and conso.SOURCE_DEFAUT == {"codex": "codex"}


# --- routes -------------------------------------------------------------------------------
def test_routes_lire_regler_et_moteur_prevu(m, config, tmp_path):
    config.chemin = tmp_path / "config.toml"
    config.chemin.write_text("[serveur]\nport = 1\n", encoding="utf-8")
    with TestClient(api.creer_app(config, m), base_url="http://127.0.0.1:8399") as c:
        assert c.get("/api/economie").json()["position"] == "intelligent"
        r = c.put("/api/economie", json={"position": "economie"}, headers=H)
        assert r.status_code == 200 and r.json()["position"] == "economie"
        assert 'position = "economie"' in config.chemin.read_text(encoding="utf-8")
        assert c.put("/api/economie", json={"position": "folle"}, headers=H).status_code == 400
        d = c.get("/api/taches/mere/economie").json()
        assert (d["famille"], d["modele"], d["position"]) == ("rapide", "petit", "economie")
    assert "moteur_motif" not in m.vault.tache("mere").fm  # la lecture n'écrit rien


# --- toute conversation neuve (précision du 15/11) ----------------------------------------
def test_role_ephemere_suit_le_curseur_et_l_equilibrage(m, monkeypatch):
    from orchestrateur.config import ConfigRole
    m.config.harnais["autre"]["familles"] = {"rapide": "autre-petit", "sonnet": "autre-moyen"}
    m.config.moteurs_par_role = {"conseil": ConfigRole(famille="sonnet")}
    assert (m.roles.choisir("conseil").harnais, m.roles.choisir("conseil").modele) == ("faux", "moyen")
    m.config.economie.position = "economie"
    assert m.roles.choisir("conseil").modele == "petit"
    quotas(m, monkeypatch, {"faux": [fenetre(0.9, 0.5)], "autre": [fenetre(0.1, 0.5)]})
    c = m.roles.choisir("conseil")
    assert (c.harnais, c.modele) == ("autre", "autre-petit") and c.repli == (("faux", "petit"),)
    assert m.roles.choisir("conseil", prefere="faux").harnais == "faux"  # conversation ouverte gardée
    assert m.roles.choisir("persona", "faux", "x").harnais == "faux"  # harnais fixé par le persona


def test_tache_enfant_et_derivee_sans_fil_choisies_derivee_avec_fil_gardee(m, monkeypatch, vault):
    quotas(m, monkeypatch, {"faux": [fenetre(0.9, 0.5)], "autre": [fenetre(0.1, 0.5)]})
    enfant = m.creer("Sous-travail", parent="mere")
    assert m.economie.decider(vault.tache(enfant)).harnais == "autre"
    vault.modifier("mere", {"session": "s-1", "harnais": "faux"})
    sans_fil = m.deriver("mere", "Dérivée", "enfant", False)
    assert m.economie.decider(vault.tache(sans_fil)).harnais == "autre"
    avec_fil = m.deriver("mere", "Dérivée avec fil", "enfant", True)
    assert m.economie.decider(vault.tache(avec_fil), avec_fil in m.a_deriver).harnais == "faux"


def test_profil_integration_porte_le_motif_de_delegation():
    assert "délégué" in economie.profil("Fusionner les branches du lot", True, False, "sonnet")[1]


def test_consigne_de_tour_demande_de_trancher_seul():
    import tomllib
    from pathlib import Path
    g = tomllib.loads((Path(__file__).parent.parent / "config.exemple.toml").read_text("utf-8"))["consigne"]["gabarit"]
    assert "Trancher seul" in g and "vérifie d'abord" not in g.lower().split("trancher seul")[0]
    assert "envoi, une dépense, une décision de fond ou un secret" in g and "(mvp)" in g and "`en_cours`" in g
