"""Le temps : échéance, priorité, retard, vue « Aujourd'hui », propositions, CLI."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, cli, fiches, recherche, temps
from orchestrateur import vault as V
from orchestrateur.moteur import Moteur

JOUR = dt.date(2026, 11, 14)
UN_JOUR = dt.timedelta(days=1)
H = {"X-Orchestrateur": "1"}


@pytest.fixture(autouse=True)
def horloge(monkeypatch):
    monkeypatch.setattr(V, "aujourdhui", lambda: JOUR)


def poser(vault, ident, **maj):
    vault.modifier(ident, maj)


def taches_de(noeuds):
    for n in noeuds:
        if n["type"] == "tache":
            yield n
        yield from taches_de(n["enfants"])


def test_lecture_tolerante(vault):
    poser(vault, "mere", echeance=JOUR, priorite="normale")
    t = vault.tache("mere")
    assert temps.echeance_de(t.fm) == JOUR and temps.priorite_de(t.fm) == "normale"
    assert temps.rang("normale") == temps.rang("moyenne") < temps.rang("basse") < temps.rang("")
    # Valeurs illisibles : ni échéance ni erreur (INV-TEMPS-1).
    assert temps.echeance_de({"echeance": "bientôt"}) is None
    assert temps.echeance_de({"echeance": "2026-11-20T10:00:00"}) == dt.date(2026, 11, 20)


def test_ecriture_stricte():
    assert temps.valider("2026-11-20", "Haute") == {"echeance": dt.date(2026, 11, 20),
                                                    "priorite": "haute"}
    assert temps.valider("", "") == {"echeance": None, "priorite": None}
    assert temps.valider(None, None) == {}
    for mauvais in (("20/11/2026", None), ("2026-13-40", None), (None, "normale")):
        with pytest.raises(V.Invalide):
            temps.valider(*mauvais)


def test_pose_ligne_a_ligne_et_retrait(vault, racine):
    chemin = racine / "Projets/C1-Alpha/taches/mere.md"
    avant = chemin.read_text("utf-8")
    vault.poser_temps("mere", temps.valider("2026-11-20", "haute"))
    texte = chemin.read_text("utf-8")
    assert "echeance: 2026-11-20\n" in texte and "priorite: haute\n" in texte
    assert fiches.frontmatter(texte)["echeance"] == "2026-11-20"
    sans = texte.replace("echeance: 2026-11-20\n", "").replace("priorite: haute\n", "")
    assert sans.replace("updated: 2026-11-14\n", "") == avant  # le reste, octet pour octet
    vault.poser_temps("mere", temps.valider("", ""))
    assert "echeance" not in chemin.read_text("utf-8")


def test_retard_seulement_si_ouverte(vault):
    poser(vault, "mere", echeance=JOUR - UN_JOUR)
    poser(vault, "fermee", echeance=JOUR - UN_JOUR)
    poser(vault, "enfant", echeance=JOUR)
    assert temps.vue(vault, vault.tache("mere"))["retard"] is True
    assert temps.vue(vault, vault.tache("fermee"))["retard"] is False
    assert temps.vue(vault, vault.tache("enfant"))["retard"] is False
    assert temps.nb_retard(vault) == 1


def groupes(vault):
    return {x["cle"]: [t["id"] for t in x["taches"]] for x in temps.aujourdhui(vault)["groupes"]}


def test_vue_aujourdhui_groupes_et_tri(vault):
    poser(vault, "mere", echeance=JOUR - 3 * UN_JOUR, priorite="basse")
    poser(vault, "enfant", echeance=JOUR - UN_JOUR, priorite="haute")
    poser(vault, "petit", echeance=JOUR)
    poser(vault, "x", echeance=JOUR + 7 * UN_JOUR, priorite="normale")
    poser(vault, "fermee", echeance=JOUR)  # fermée : exclue
    beta = next(k for k, t in vault.index()[0].items() if t.titre == "Doublon Beta")
    poser(vault, beta, statut="retour-humain")  # « à moi », sans échéance
    assert temps.aujourdhui(vault)["date"] == "2026-11-14"
    g = groupes(vault)
    assert g["retard"] == ["enfant", "mere"]  # priorité haute avant basse
    assert (g["aujourdhui"], g["semaine"], g["amoi"]) == (["petit"], ["x"], [beta])


def test_a_moi_expose_resultat_et_essai_de_la_fiche(vault):
    beta = next(k for k, t in vault.index()[0].items() if t.titre == "Doublon Beta")
    vault.modifier(beta, {"statut": "fait", "session": "s-1"},
                   fiche={"resultat": "branche gb/x", "essai": "ouvrir la page"})
    ligne = next(x for g in temps.aujourdhui(vault)["groupes"] if g["cle"] == "amoi"
                 for x in g["taches"] if x["id"] == beta)
    assert ligne["a_valider"]
    assert (ligne["resultat"], ligne["essai"]) == ("branche gb/x", "ouvrir la page")


def test_hors_horizon_exclu_et_a_moi_une_seule_fois(vault):
    poser(vault, "mere", statut="retour-humain", echeance=JOUR)
    poser(vault, "x", echeance=JOUR + 8 * UN_JOUR)
    g = groupes(vault)
    assert g["aujourdhui"] == ["mere"] and "mere" not in g["amoi"]
    assert all("x" not in ids for ids in g.values())


def test_arbre_recherche_et_etat_portent_le_temps(config, vault, faux):
    poser(vault, "mere", echeance=JOUR - 2 * UN_JOUR, priorite="haute")
    n = next(n for n in taches_de(vault.arbre(True)) if n["id"] == "mere")
    assert (n["echeance"], n["priorite"], n["retard"]) == ("2026-11-12", "haute", True)
    assert recherche.chercher(vault, "mere")[0]["echeance"] == "2026-11-12"
    assert Moteur(config, vault, {"faux": faux}).etat_global()["en_retard"] == 1


def test_creation_avec_temps(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    ident = m.creer("Avec temps", echeance="2026-12-01", priorite="basse")
    assert vault.tache(ident).fm["echeance"] == "2026-12-01"
    assert vault.tache(ident).fm["priorite"] == "basse"
    with pytest.raises(V.Invalide):
        m.creer("Mauvaise", echeance="demain")


def test_proposition_echeance_jamais_ecrite_seule(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    with pytest.raises(V.Invalide):
        m.proposer("echeance", "mere", "demain")
    p = m.proposer("echeance", "mere", "2026-11-30", motif="avant la réunion")
    assert "echeance" not in vault.tache("mere").fm  # INV-EXEC-5 : rien sans geste humain
    m.trancher(p["n"], True)
    assert vault.tache("mere").fm["echeance"] == "2026-11-30"


def test_api_temps(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        r = c.post("/api/taches/mere/temps", json={"echeance": "2026-11-10", "priorite": "haute"},
                   headers=H)
        assert r.status_code == 200 and r.json()["retard"] is True
        assert c.post("/api/taches/mere/temps", json={"echeance": "10/11"},
                      headers=H).status_code == 400
        assert c.post("/api/taches/mere/temps", json={"priorite": ""},
                      headers=H).json()["priorite"] == ""
        assert c.get("/api/taches/mere").json()["echeance"] == "2026-11-10"
        assert c.get("/api/aujourdhui").json()["groupes"][0]["taches"][0]["id"] == "mere"
        assert c.get("/api/etat").json()["en_retard"] == 1
        n = c.post("/api/taches", json={"titre": "T", "echeance": "2026-12-01"}, headers=H)
        assert n.status_code == 201 and n.json()["echeance"] == "2026-12-01"


def test_cli_montre_l_echeance():
    noeuds = [{"type": "tache", "id": "t1", "statut": "a-faire", "titre": "T", "enfants": [],
               "echeance": "2026-11-10", "retard": True},
              {"type": "tache", "id": "t2", "statut": "a-faire", "titre": "U", "enfants": []}]
    assert cli.rendre_arbre(noeuds) == [
        "- t1 [a-faire] T — échéance 2026-11-10 (en retard)", "- t2 [a-faire] U"]
    r = {"id": "t1", "titre": "T", "fil_ariane": ["C1"], "echeance": "2026-11-20"}
    assert cli.rendre_recherche([r]) == ["- t1 [?] T (C1) — échéance 2026-11-20"]
