"""Guide d'utilisation (INV-GUIDE-1) : route en texte brut, `orch guide`, porte rouge si une section manque."""

from fastapi.testclient import TestClient

from orchestrateur import api, cli, guide
from orchestrateur.moteur import Moteur


def test_route_rend_le_guide_en_texte_brut(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        r = c.get("/api/guide")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text.startswith("# Guide de GoldenBrain") and "## Pour un agent IA" in r.text


def test_orch_guide_imprime_le_guide_sans_serveur(capsys):
    assert cli.main(["guide"]) == 0
    assert capsys.readouterr().out.startswith("# Guide de GoldenBrain")


def test_le_guide_du_depot_couvre_tout_le_registre():
    assert guide.manquements(guide.lire()) == []


def test_section_retiree_rend_la_porte_rouge():
    texte = guide.lire().replace("### Routines\n", "### Routines programmées\n")
    assert any("« Routines »" in e for e in guide.manquements(texte))


def test_date_de_mise_a_jour_absente_rend_la_porte_rouge():
    texte = guide.lire().replace("Mis à jour le", "Revu le", 1)
    assert any("Mis à jour le" in e for e in guide.manquements(texte))


def test_ancre_incoherente_avec_son_titre_est_signalee():
    assert guide.manquements("## Réglages\nMis à jour le 2026-01-01.\n", {"parametres": "Réglages"})


def test_titre_reformule_garde_son_ancre_explicite():
    texte = "## Ordinateurs d'appoint {#executeurs-distants}\nMis à jour le 2026-01-01.\n"
    assert guide.manquements(texte, {"executeurs-distants": "Ordinateurs d'appoint"}) == []
    assert guide.manquements(texte, {"autre": "Ordinateurs d'appoint"})


def test_ancre_sans_accents_ni_ponctuation():
    assert guide.ancre("Mise à jour d'un clic") == "mise-a-jour-d-un-clic"
    assert guide.ancre("Service au démarrage (Linux)") == "service-au-demarrage-linux"
