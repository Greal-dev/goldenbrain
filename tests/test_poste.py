"""Réservation du poste (INV-POSTE-1) : prise, file des tâches lourdes, libération, expiration,
persistance, routes et commande `orch poste`."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from conftest import PORT, ecrire, tache_md
from orchestrateur import api, cli
from orchestrateur.moteur import Moteur
from orchestrateur.poste import Poste
from orchestrateur.vault import Conflit

H = {"X-Orchestrateur": "1"}


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def poste(tmp_path):
    h = Horloge()
    p = Poste(tmp_path / "etat" / "poste.json", 7200, h)
    p.h = h
    return p


def test_reserver_puis_liberer(poste):
    assert poste.actuelle() is None
    r = poste.reserver("a", "porte complète")
    assert r["tache"] == "a" and r["motif"] == "porte complète"
    assert poste.liberer("a") is True and poste.actuelle() is None
    assert poste.liberer("a") is False  # rien à rendre : sans erreur


def test_un_seul_titulaire(poste):
    poste.reserver("a")
    with pytest.raises(Conflit, match="déjà réservé par a"):
        poste.reserver("b")
    with pytest.raises(Conflit, match="réservé par a, pas par b"):
        poste.liberer("b")
    poste.reserver("a", "renouvelé")  # le titulaire renouvelle
    assert poste.actuelle()["motif"] == "renouvelé"


def test_geste_humain_libere_n_importe_quelle_reservation(poste):
    poste.reserver("a")
    assert poste.liberer() is True and poste.actuelle() is None


def test_expiration_apres_le_delai(poste):
    poste.reserver("a")
    poste.h.t += 7199
    assert poste.actuelle() is not None
    poste.h.t += 2
    assert poste.actuelle() is None
    poste.reserver("b")  # le poste expiré ne retient plus personne


def test_la_reservation_survit_au_redemarrage_et_son_expiration_aussi(poste, tmp_path):
    poste.reserver("a", "m")
    relu = Poste(tmp_path / "etat" / "poste.json", 7200, poste.h)
    assert relu.actuelle()["tache"] == "a"
    poste.h.t += 8000
    assert Poste(tmp_path / "etat" / "poste.json", 7200, poste.h).actuelle() is None


def test_fichier_illisible_vaut_poste_libre(tmp_path):
    f = tmp_path / "poste.json"
    f.write_text("{pas du json", encoding="utf-8")
    assert Poste(f, 60).actuelle() is None


def test_bloque_seulement_une_autre_tache_lourde(poste):
    poste.reserver("a")
    assert poste.bloque("b", {"epreuves": "lourdes"})["tache"] == "a"
    assert poste.bloque("b", {"epreuves": " Lourdes "}) is not None
    assert poste.bloque("b", {}) is None and poste.bloque("b", {"epreuves": "legeres"}) is None
    assert poste.bloque("a", {"epreuves": "lourdes"}) is None  # le titulaire n'est pas bloqué


# --- moteur ------------------------------------------------------------------------------
def moteur(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.INTERVALLE_POSTE_S = 0.01
    return m


@pytest.fixture
def lourdes(racine):
    ecrire(racine, "Projets/C1-Alpha/taches/lourde.md",
           tache_md(extra="epreuves: lourdes\n", titre="Épreuves lourdes"))


async def finir(m):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def test_tache_lourde_attend_la_liberation_puis_demarre(config, vault, faux, lourdes):
    async def scenario():
        m = moteur(config, vault, faux)
        m.poste.reserver("mere", "porte complète")
        m.soumettre("lourde", "go")
        await asyncio.sleep(0.1)
        attente = m.attente_poste("lourde")
        assert faux.lances == [] and m.etat_de("lourde") == "en_file"
        assert attente["par"] == "mere" and attente["titre"] == "Mère"
        m.poste.liberer("mere")
        await finir(m)
        return m

    m = asyncio.run(scenario())
    assert len(faux.lances) == 1 and m.attente_poste("lourde") is None


def test_tache_sans_marque_ne_attend_pas(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.poste.reserver("mere")
        m.soumettre("enfant", "go")
        await finir(m)

    asyncio.run(scenario())
    assert len(faux.lances) == 1


def test_la_file_attend_sans_tenir_de_creneau(config, vault, faux, lourdes):
    async def scenario():
        m = moteur(config, vault, faux)  # simultanes_max = 2
        m.poste.reserver("mere")
        m.soumettre("lourde", "go")
        await asyncio.sleep(0.05)
        assert m._sem.pris == 0  # l'attente ne retient aucun créneau
        m.soumettre("enfant", "go")  # une autre tâche passe devant
        await asyncio.sleep(0.1)
        n = len(faux.lances)
        m.poste.liberer()
        await finir(m)
        return n

    assert asyncio.run(scenario()) == 1


def test_la_reservation_est_rendue_a_la_fin_du_tour_du_titulaire(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.poste.reserver("mere")
        m.soumettre("mere", "go")
        await finir(m)
        return m

    assert asyncio.run(scenario()).poste.actuelle() is None  # rendue d'office


def test_la_reservation_d_une_autre_tache_survit_a_mon_tour(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.poste.reserver("enfant")
        m.soumettre("mere", "go")
        await finir(m)
        return m

    assert asyncio.run(scenario()).poste.actuelle()["tache"] == "enfant"


def test_une_reservation_expiree_ne_bloque_plus(config, vault, faux, lourdes):
    async def scenario():
        m = moteur(config, vault, faux)
        h = Horloge()
        m.__dict__["poste"] = Poste(config.donnees / "etat" / "poste.json", 60, h)
        m.poste.reserver("mere")
        m.soumettre("lourde", "go")
        await asyncio.sleep(0.05)
        assert faux.lances == []
        h.t += 61
        await finir(m)

    asyncio.run(scenario())
    assert len(faux.lances) == 1


def test_etat_global_porte_le_poste(config, vault, faux):
    m = moteur(config, vault, faux)
    assert m.etat_global()["poste"] is None
    m.poste.reserver("mere", "x")
    assert m.etat_global()["poste"]["tache"] == "mere"


def test_delai_regle_par_la_configuration(config, vault, faux):
    config.moteur.poste_delai_min = 5
    assert moteur(config, vault, faux).poste.delai_s == 300


# --- API et CLI --------------------------------------------------------------------------
BASE = f"http://127.0.0.1:{PORT}"


def test_routes_reserver_lire_liberer(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url=BASE) as c:
        assert c.get("/api/poste").json() == {"poste": None, "file": []}
        r = c.post("/api/poste/reserver", headers=H, json={"tache": "mere", "motif": "porte"})
        assert r.status_code == 200 and r.json()["poste"]["tache"] == "mere"
        assert c.get("/api/etat").json()["poste"]["motif"] == "porte"
        assert c.post("/api/poste/reserver", headers=H, json={"tache": "enfant"}).status_code == 409
        assert c.post("/api/poste/liberer", headers=H, json={"tache": "enfant"}).status_code == 409
        assert c.post("/api/poste/liberer", headers=H, json={}).json() == {"libere": True,
                                                                          "poste": None}
        inconnue = c.post("/api/poste/reserver", headers=H, json={"tache": "inconnue"})
        assert inconnue.status_code == 404
        assert c.post("/api/poste/reserver", json={"tache": "mere"}).status_code == 403  # INV-API-1


def test_detail_d_une_tache_en_attente_du_poste(config, vault, faux, lourdes):
    m = moteur(config, vault, faux)
    with TestClient(api.creer_app(config, m), base_url=BASE) as c:
        c.post("/api/poste/reserver", headers=H, json={"tache": "mere", "motif": "porte"})
        c.post("/api/taches/lourde/messages", headers=H, json={"texte": "go"})
        d = c.get("/api/taches/lourde").json()
        assert d["etat_execution"] == "en_file"
        assert d["attente_poste"]["par"] == "mere" and d["attente_poste"]["titre"] == "Mère"
        c.post("/api/poste/liberer", headers=H, json={})


def test_cli_poste(monkeypatch, capsys):
    appels = []
    reponses = {("POST", "/poste/reserver"): {"poste": {"tache": "t1"}},
                ("POST", "/poste/liberer"): {"libere": True},
                ("GET", "/poste"): {"poste": {"tache": "t1", "depuis": "2026-11-15T10:30:00",
                                              "motif": "porte"}}}

    def faux_appel(methode, chemin, corps=None):
        appels.append((methode, chemin, corps))
        return reponses[(methode, chemin)]

    monkeypatch.setattr(cli, "appeler", faux_appel)
    monkeypatch.setenv("ORCH_TACHE", "t1")
    assert cli.main(["poste", "reserver", "porte complète"]) == 0
    assert appels[-1] == ("POST", "/poste/reserver", {"tache": "t1", "motif": "porte complète",
                                                "attendre": True})
    assert cli.main(["poste", "liberer"]) == 0
    assert appels[-1] == ("POST", "/poste/liberer", {"tache": "t1"})
    assert cli.main(["poste", "etat"]) == 0
    assert "réservé par t1 depuis 10:30 : porte" in capsys.readouterr().out
    monkeypatch.delenv("ORCH_TACHE")
    assert cli.main(["poste", "reserver"]) == 1


# --- File d'attente (INV-POSTE-1) --------------------------------------------------------
def test_refus_inscrit_en_file_et_le_premier_arrive_passe_en_premier(poste):
    poste.reserver("a")
    assert poste.demander("b") is None and poste.demander("c") is None
    assert [poste.rang("b"), poste.rang("c")] == [1, 2]
    assert poste.demander("b") is None and poste.rang("b") == 1  # redemander ne double pas
    with pytest.raises(Conflit, match="en file, rang 2"):
        poste.reserver("c")
    poste.liberer("a")
    assert poste.demander("c") is None  # poste libre, mais b est devant
    assert poste.demander("b")["tache"] == "b" and poste.rang("b") is None
    assert poste.rang("c") == 1
    assert [e["tache"] for e in poste.file()] == ["c"]


def test_attendant_muet_quitte_la_file_et_le_suivant_passe(poste):
    poste.reserver("a")
    poste.demander("b")
    poste.h.t += 10
    poste.demander("c")
    poste.h.t += 10  # b muet depuis 20 s, c depuis 10 s
    assert poste.rang("b") is None and poste.rang("c") == 1
    poste.liberer("a")
    assert poste.demander("c")["tache"] == "c"


def test_expiration_du_titulaire_donne_le_poste_au_suivant(poste):
    poste.reserver("a")
    poste.demander("b")
    poste.h.t += 7201
    assert poste.actuelle() is None and poste.demander("b")["tache"] == "b"


def test_fin_de_tour_ou_annulation_sort_de_la_file(poste):
    poste.reserver("a")
    poste.demander("b")
    poste.demander("c")
    assert poste.rendre("b") is False and poste.rang("b") is None
    assert poste.retirer("c") is True and poste.retirer("c") is False


def test_routes_file_attendre_annuler(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url=BASE) as c:
        c.post("/api/poste/reserver", headers=H, json={"tache": "mere"})
        r = c.post("/api/poste/reserver", headers=H, json={"tache": "enfant", "attendre": True}).json()
        assert r["poste"] is None and r["rang"] == 1 and r["titulaire"]["tache"] == "mere"
        assert c.get("/api/poste").json()["file"][0]["tache"] == "enfant"
        assert c.get("/api/etat").json()["poste"]["file"][0]["tache"] == "enfant"
        assert c.get("/api/taches/enfant").json()["rang_poste"] == 1
        assert c.post("/api/poste/annuler", headers=H, json={"tache": "enfant"}).json() == {"retire": True}
        assert c.get("/api/taches/enfant").json()["rang_poste"] is None
        c.post("/api/poste/liberer", headers=H, json={})


def test_cli_poste_attend_son_tour_puis_obtient_le_poste(monkeypatch, capsys):
    reponses = iter([{"poste": None, "rang": 2, "titulaire": {"tache": "t0"}},
                     {"poste": None, "rang": 1, "titulaire": {"tache": "t0"}},
                     {"poste": {"tache": "t1"}}])
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: next(reponses))
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    monkeypatch.setenv("ORCH_TACHE", "t1")
    assert cli.main(["poste", "reserver", "porte"]) == 0
    cap = capsys.readouterr()
    assert "en attente du poste (rang 2), tenu par t0" in cap.err and "(rang 1)" in cap.err
    assert "poste réservé" in cap.out


def test_cli_poste_delai_depasse_quitte_la_file(monkeypatch, capsys):
    appels = []

    def faux_appel(m, c, corps=None):
        appels.append(c)
        return {"poste": None, "rang": 1, "titulaire": {"tache": "t0"}}

    monkeypatch.setattr(cli, "appeler", faux_appel)
    monkeypatch.setenv("ORCH_TACHE", "t1")
    assert cli.main(["poste", "reserver", "--attente", "0"]) == 1
    assert appels == ["/poste/reserver", "/poste/annuler"]
    assert "poste toujours pris après 0 min" in capsys.readouterr().err
