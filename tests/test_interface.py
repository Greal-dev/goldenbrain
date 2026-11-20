"""Mode simple / avancé : drapeaux par famille, routes en 409, persistance de `[interface]`."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, liens
from orchestrateur.api_interface import ecrire_section
from orchestrateur.config import ConfigInterface, charger
from orchestrateur.moteur import Moteur
from conftest import ecrire
from test_liens import propager
from test_revues import OK, evs, lancer_tache, multi, persona, rendu

H = {"X-Orchestrateur": "1"}


def test_sans_section_une_installation_existante_reste_avancee():
    i = ConfigInterface()
    assert i.mode == "avance" and i.actif("equipe") and i.politique() == "montrer"


def test_mode_simple_debraie_tout_et_un_drapeau_explicite_l_emporte():
    i = ConfigInterface(mode="simple", notes=True)
    assert i.actif("notes") and not i.actif("equipe") and not i.actif("moteurs")
    assert i.politique() == "ignorer"
    assert ConfigInterface(mode="simple", propositions="accepter").politique() == "accepter"


def test_valeurs_inconnues_refusees():
    with pytest.raises(ValueError):
        ConfigInterface(mode="expert")
    with pytest.raises(ValueError):
        ConfigInterface(propositions="peut-etre")


def test_la_configuration_se_lit_depuis_le_toml(tmp_path, racine):
    f = tmp_path / "c.toml"
    f.write_text(f'[vault]\nracine = "{racine.as_posix()}"\ntaches = []\n'
                 '[interface]\nmode = "simple"\nliens = true\n', encoding="utf-8")
    c = charger(f)
    assert c.interface.mode == "simple" and c.interface.actif("liens") and c.chemin == f


def test_liens_debraies_aucune_propagation(config, vault, faux):
    config.interface = ConfigInterface(mode="simple")
    vault.modifier("mere", {"alimente": ["x"]})
    assert [t for t, _ in propager(config, vault, faux)] == ["mere"]


def test_equipe_debrayee_aucune_revue_et_la_tache_attend_l_humain(config, vault, faux):
    config.interface = ConfigInterface(mode="simple")
    multi(faux, {"": evs("s-1", rendu()), "rssi": evs("p-1", OK)})
    lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    assert [x["persona"] for x in faux.lances] == [""]
    assert vault.tache("mere").statut == "fait"


def test_jardinage_debraye_ne_lance_rien(config, vault, faux):
    from orchestrateur.jardinage import Jardinier
    config.interface = ConfigInterface(mode="simple")
    j = Jardinier(Moteur(config, vault, {"faux": faux}))
    j.cfg.rythme = "quotidien"
    assert j.verifier() is None and faux.lances == []


@pytest.mark.parametrize("politique,etat,nb", [("ignorer", "ignoree", 0), ("montrer", "en_attente", 1),
                                               ("accepter", "acceptee", 1)])
def test_politique_des_propositions(config, vault, faux, politique, etat, nb):
    config.interface = ConfigInterface(propositions=politique)
    m = Moteur(config, vault, {"faux": faux})
    assert m.proposer("lier", "mere", "alimente:x")["etat"] == etat
    assert len(m.propositions.liste) == nb
    assert bool(liens.refs(vault.index()[0], "x")["alimente_par"]) == (politique == "accepter")


@pytest.fixture
def client(config, vault, faux, tmp_path):
    config.chemin = tmp_path / "config.toml"
    config.chemin.write_text('# mes réglages\n[serveur]\nport = 8399\n\n[harnais.claude]\nmodele = "x"\n',
                             encoding="utf-8")
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        yield c


def test_route_lit_et_bascule_en_simple_sans_toucher_aux_autres_reglages(client, config):
    assert client.get("/api/interface").json()["mode"] == "avance"
    r = client.put("/api/interface", headers=H, json={"mode": "simple"})
    assert r.json()["familles"]["equipe"] is False and r.json()["propositions"] == "ignorer"
    texte = config.chemin.read_text(encoding="utf-8")
    assert texte.startswith('# mes réglages\n[serveur]\nport = 8399\n\n[harnais.claude]\nmodele = "x"\n')
    assert '[interface]\nmode = "simple"\n' in texte
    client.put("/api/interface", headers=H, json={"familles": {"notes": True}, "propositions": "montrer"})
    assert charger_interface(config).actif("notes") and not charger_interface(config).actif("liens")
    client.put("/api/interface", headers=H, json={"mode": "avance"})  # le mode remet les familles
    assert config.interface.notes is None and config.interface.actif("equipe")
    assert config.chemin.read_text(encoding="utf-8").count("[interface]") == 1


def charger_interface(config):
    import tomllib
    return ConfigInterface(**tomllib.loads(config.chemin.read_text(encoding="utf-8"))["interface"])


def test_valeurs_invalides_400(client):
    assert client.put("/api/interface", headers=H, json={"mode": "x"}).status_code == 400
    assert client.put("/api/interface", headers=H, json={"familles": {"zzz": True}}).status_code == 400
    assert client.get("/api/interface").json()["mode"] == "avance"


def test_routes_des_familles_debrayees_409(client, racine):
    client.put("/api/interface", headers=H, json={"mode": "simple"})
    for methode, url, corps in [
            ("post", "/api/taches/mere/liens", {"type": "alimente", "cible": "x"}),
            ("post", "/api/taches/mere/solliciter", {"persona": "p"}),
            ("put", "/api/equipe/p", {}),
            ("post", "/api/taches/mere/promouvoir", {}),
            ("post", "/api/conteneurs/reduire", {"conseil": 1, "conteneur": "Projets/C1-Alpha"}),
            ("get", "/api/alignement", None), ("post", "/api/jardinage", None),
            ("get", "/api/vault/notes", None)]:
        r = getattr(client, methode)(url, headers=H, **({"json": corps} if corps is not None else {}))
        assert r.status_code == 409 and "désactivée" in r.json()["detail"], url
    assert client.get("/api/equipe").status_code == 200  # lire reste possible
    assert client.get("/api/arbre").status_code == 200
    assert client.post("/api/conseil", headers=H, json={"action": "promouvoir", "tache": "mere"}
                       ).json()["avis"] == "indisponible"
    client.put("/api/interface", headers=H, json={"familles": {"alignement": True}})
    assert client.get("/api/alignement").status_code == 200


def test_moteurs_debraye_ignore_le_harnais_demande(client, vault):
    client.put("/api/interface", headers=H, json={"mode": "simple"})
    r = client.post("/api/taches", headers=H, json={"titre": "T", "harnais": "inconnu"})
    assert r.status_code == 201 and not vault.tache(r.json()["id"]).fm.get("harnais")


def test_ecrire_section_garde_le_reste_octet_pour_octet(tmp_path):
    f = tmp_path / "c.toml"
    f.write_bytes(b'[a]\r\nx = 1\r\n[interface]\r\nmode = "avance"\r\nliens = false\r\n# fin\r\n[b]\r\ny = 2\r\n')
    ecrire_section(f, ConfigInterface(mode="simple", notes=True))
    assert f.read_bytes() == (b'[a]\r\nx = 1\r\n[interface]\r\nmode = "simple"\r\nnotes = true\r\n\r\n'
                              b'[b]\r\ny = 2\r\n')
    g = tmp_path / "vide.toml"
    ecrire_section(g, ConfigInterface(mode="simple"))
    assert g.read_text(encoding="utf-8") == '[interface]\nmode = "simple"\n'
