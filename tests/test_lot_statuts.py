"""Modification en bloc (INV-LOT-1) : tout ou rien, exclusion des tâches occupées, geste humain, annulation, trace."""

import json

import pytest
from conftest import ecrire, tache_md
from fastapi.testclient import TestClient

from orchestrateur import api, lot_statuts
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Invalide, NonTrouve

ALPHA = "Projets/C1-Alpha/taches/"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def moteur(config, vault, faux, racine):
    for n in ("a", "b", "c"):
        ecrire(racine, f"{ALPHA}{n}.md", tache_md(titre=n.upper()))
    vault._index = None
    return Moteur(config, vault, {"faux": faux})


def _st(m, i):
    return m.vault.tache(i).statut


def test_lot_change_le_statut_de_toutes_les_taches(moteur):
    r = lot_statuts.appliquer(moteur, ["a", "b"], statut="fait")
    assert sorted(r["changees"]) == ["a", "b"] and r["exclues"] == []
    assert _st(moteur, "a") == _st(moteur, "b") == "fait" and _st(moteur, "c") == "a-faire"


def test_lot_refuse_en_bloc_si_une_tache_est_inconnue_ou_le_statut_invalide(moteur):
    with pytest.raises(NonTrouve):
        lot_statuts.appliquer(moteur, ["a", "fantome"], statut="fait")
    with pytest.raises(Invalide):
        lot_statuts.appliquer(moteur, ["a"], statut="nimporte")
    with pytest.raises(Invalide):
        lot_statuts.appliquer(moteur, ["a"], echeance="demain")
    with pytest.raises(Invalide):
        lot_statuts.appliquer(moteur, ["a"])
    assert _st(moteur, "a") == "a-faire"  # rien d'écrit


def test_lot_tout_ou_rien_si_une_ecriture_echoue_en_route(moteur, monkeypatch):
    vrai = moteur.vault.poser_statut

    def casse(ident, statut, humain=False):
        if ident == "b":
            raise Conflit("panne")
        vrai(ident, statut, humain=humain)

    monkeypatch.setattr(moteur.vault, "poser_statut", casse)
    with pytest.raises(Conflit):
        lot_statuts.appliquer(moteur, ["a", "b"], statut="fait")
    monkeypatch.undo()
    assert _st(moteur, "a") == "a-faire"  # « a » avait été écrite : elle est revenue


def test_taches_occupees_exclues_et_signalees(moteur, monkeypatch):
    monkeypatch.setattr(type(moteur), "occupation", lambda self, i: {"tache": i, "titre": "B", "depuis": "x"} if i == "b" else None)
    r = lot_statuts.appliquer(moteur, ["a", "b"], statut="fait")
    assert r["changees"] == ["a"] and [e["id"] for e in r["exclues"]] == ["b"]
    assert _st(moteur, "b") == "a-faire"


def test_annulation_restaure_et_ne_s_applique_qu_une_fois(moteur):
    r = lot_statuts.appliquer(moteur, ["a", "b"], statut="en-cours", echeance="2026-12-01")
    assert str(moteur.vault.tache("a").fm["echeance"]) == "2026-12-01"
    moteur.vault.poser_statut("b", "bloque", humain=True)  # modifiée depuis : on ne l'écrase pas
    d = lot_statuts.annuler(moteur, r["lot"])
    assert d["restaurees"] == ["a"] and [x["id"] for x in d["ignorees"]] == ["b"]
    assert _st(moteur, "a") == "a-faire" and not moteur.vault.tache("a").fm.get("echeance")
    assert _st(moteur, "b") == "bloque"
    with pytest.raises(Conflit):
        lot_statuts.annuler(moteur, r["lot"])


def test_trace_au_journal_de_chaque_tache(moteur, config):
    r = lot_statuts.appliquer(moteur, ["a", "b"], statut="fait")
    for i in ("a", "b"):
        l = json.loads((config.donnees / "journal/statuts" / f"{i}.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert l["lot"] == r["lot"] and l["avant"]["statut"] == "a-faire" and l["apres"]["statut"] == "fait"


def test_rattachement_en_bloc(moteur):
    lot_statuts.appliquer(moteur, ["b", "c"], parent="a")
    assert moteur.vault.tache("b").parent_brut == "a" and moteur.vault.tache("c").parent_brut == "a"
    with pytest.raises(Conflit, match="cycle"):
        lot_statuts.appliquer(moteur, ["a"], parent="b")


def test_apercu_n_ecrit_rien(moteur):
    r = lot_statuts.apercu(moteur, ["a", "b"], statut="fait")
    assert r["retenues"] == ["a", "b"] and r["de"] == {"a-faire": 2} and _st(moteur, "a") == "a-faire"


def test_route_lot_humain_seulement_et_annulation(config, moteur):
    with TestClient(api.creer_app(config, moteur), base_url="http://127.0.0.1:8399") as c:
        agent = c.post("/api/lots", headers={**H, "X-Orch-Tache": "a"}, json={"taches": ["b"], "statut": "fait"})
        assert agent.status_code == 403 and _st(moteur, "b") == "a-faire"
        r = c.post("/api/lots", headers=H, json={"taches": ["b", "c"], "statut": "fait"})
        assert r.status_code == 200 and _st(moteur, "c") == "fait"
        assert c.post("/api/lots", headers=H, json={"taches": ["b"], "statut": "zzz"}).status_code == 400
        assert c.post(f"/api/lots/{r.json()['lot']}/annuler", headers={**H, "X-Orch-Tache": "a"}).status_code == 403
        assert c.post(f"/api/lots/{r.json()['lot']}/annuler", headers=H).json()["restaurees"] == ["b", "c"]
        assert _st(moteur, "c") == "a-faire"


def test_lot_et_annulation_sont_des_gestes_a_risque_a_distance():
    from orchestrateur import api_appareils
    assert api_appareils.risque("POST", "/api/lots") and api_appareils.risque("POST", "/api/lots/abc/annuler")
