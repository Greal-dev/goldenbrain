"""INV-ALIGN-2 : un déplacement de dossier ne bloque que les tours qui touchent ce dossier ;
acceptation d'une proposition « operation » (INV-ARBRE-2) sous le même verrou."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from conftest import PORT, tache_md
from orchestrateur import api
from orchestrateur.config import Config, ConfigAlignement, ConfigMoteur, ConfigVault
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit
from test_alignement import FICHIERS, H, MOTIFS, ctx, faire, git

CITANTE = tache_md(titre="Citante") + "Voir Projets/Vieux/C1-Loin/l.md\n"
BASE = f"http://127.0.0.1:{PORT}"


def config_de(tmp_path, fichiers=None, base=None) -> Config:
    faire(tmp_path, {**(base or FICHIERS), **(fichiers or {})})
    return Config(port=PORT, vault=ConfigVault(racine=tmp_path / "vault", taches=MOTIFS),
                  moteur=ConfigMoteur(simultanes_max=2, harnais_defaut="faux"),
                  harnais={"faux": {}}, consigne="{titre}", donnees=tmp_path / "donnees",
                  alignement=ConfigAlignement(externes=[]))


def client(cfg, faux) -> TestClient:
    return TestClient(api.creer_app(cfg, Moteur(cfg, None, {"faux": faux})), base_url=BASE)


def lancer_tour(c, ident: str) -> None:
    assert c.post(f"/api/taches/{ident}/messages", headers=H, json={"texte": "go"}).status_code == 202


def appliquer(c, conteneur: str):
    plan = c.post("/api/alignement/plan", headers=H, json={"conteneurs": [conteneur]}).json()
    return c.post("/api/alignement/appliquer", headers=H,
                  json={"jeton": plan["jeton"], "point_git": False})


def test_tour_ailleurs_le_geste_passe(tmp_path, faux):
    faux.scenario = ["attendre"]
    cfg = config_de(tmp_path)
    with client(cfg, faux) as c:
        lancer_tour(c, "t1")  # t1 est dans Projets/C1-ORION : ailleurs que le dossier déplacé
        r = appliquer(c, "Projets/Vieux/C1-Loin")
        assert r.status_code == 200, r.text
        assert not (cfg.vault.racine / "Projets/Vieux/C1-Loin").exists()
        c.post("/api/taches/t1/arret", headers=H)


def test_tour_dans_le_dossier_409_nomme_la_tache(tmp_path, faux):
    faux.scenario = ["attendre"]
    cfg = config_de(tmp_path)
    with client(cfg, faux) as c:
        lancer_tour(c, "t1")
        r = appliquer(c, "Projets/C1-ORION")
        assert r.status_code == 409
        assert "ORION un" in r.json()["detail"] and "(t1)" in r.json()["detail"]
        assert (cfg.vault.racine / "Projets/C1-ORION/taches/t1.md").is_file()
        c.post("/api/taches/t1/arret", headers=H)


def test_tour_sur_un_fichier_reecrit_409(tmp_path, faux):
    faux.scenario = ["attendre"]
    cfg = config_de(tmp_path, {"_meta/taches/citante.md": CITANTE})
    fichier = cfg.vault.racine / "_meta/taches/citante.md"
    with client(cfg, faux) as c:
        lancer_tour(c, "citante")
        r = appliquer(c, "Projets/Vieux/C1-Loin")  # la tâche n'est pas déplacée, mais réécrite
        assert r.status_code == 409 and "Citante" in r.json()["detail"]
        assert (cfg.vault.racine / "Projets/Vieux/C1-Loin").is_dir()
        assert "Projets/Vieux/C1-Loin/l.md" in fichier.read_text("utf-8")  # pas réécrit
        c.post("/api/taches/citante/arret", headers=H)


def test_sans_tour_le_fichier_cite_est_reecrit(tmp_path, faux):
    cfg = config_de(tmp_path, {"_meta/taches/citante.md": CITANTE})
    with client(cfg, faux) as c:
        assert appliquer(c, "Projets/Vieux/C1-Loin").status_code == 200
    texte = (cfg.vault.racine / "_meta/taches/citante.md").read_text("utf-8")
    assert "Projets/Vieux/C1-Loin" not in texte


def test_demarrage_refuse_pendant_l_application_dans_les_dossiers_concernes(tmp_path, faux):
    asyncio.run(_demarrage(config_de(tmp_path), faux))


async def _demarrage(cfg, faux):
    m = Moteur(cfg, None, {"faux": faux})
    async with m.exclusif(["Projets/C1-ORION"], []):
        m.soumettre("t1", "dedans")  # dans le dossier déplacé : attend la fin du geste
        m.soumettre("t0", "ailleurs")  # ailleurs : démarre
        for _ in range(50):
            await asyncio.sleep(0.01)
            if faux.lances:
                break
        await asyncio.sleep(0.05)
        assert [x["message"] for x in faux.lances] == ["ailleurs"]
        with pytest.raises(Conflit, match="déjà en cours"):
            async with m.exclusif(["Projets/Vieux"], []):
                pass
    for _ in range(50):
        await asyncio.sleep(0.01)
        if len(faux.lances) == 2:
            break
    assert sorted(x["message"] for x in faux.lances) == ["ailleurs", "dedans"]
    while m.occupe():
        await asyncio.sleep(0.01)


# --- proposition « operation » : le dossier se déplace -----------------------------------
# Vault minimal, entièrement aligné : un projet, et une opération « Op » lue sur le disque.
OPS = {
    "Projets/C1-Alpha/contexte.md": ctx("C1", "Vague"),
    "Projets/C1-Alpha/taches/a.md": tache_md(titre="Alpha un"),
    "Projets/Op/C1-Beta/contexte.md": ctx("C1"),
    "Projets/Op/C1-Beta/taches/b.md": tache_md(titre="Beta un"),
    "Projets/C1-Gamma/contexte.md": ctx("C1"),
    "Projets/C1-Gamma/taches/g.md": tache_md(titre="Gamma un"),
}


def depot(cfg) -> None:
    """L'acceptation prend un point de restauration git : le vault de test devient un dépôt."""
    git(cfg.vault.racine, "init", "-q")
    git(cfg.vault.racine, "config", "user.email", "t@example.org")
    git(cfg.vault.racine, "config", "user.name", "T")


def accepter_operation(c, tache: str, valeur: str):
    n = c.post("/api/propositions", headers=H, json={"type": "operation", "tache": tache,
                                                      "valeur": valeur}).json()["n"]
    return n, c.post(f"/api/propositions/{n}/accepter", headers=H)


def test_operation_nouvelle_acceptee_deplace_le_dossier_sans_ecrire_parent(tmp_path, faux):
    cfg = config_de(tmp_path, base=OPS)
    depot(cfg)
    racine = cfg.vault.racine
    with client(cfg, faux) as c:
        n, r = accepter_operation(c, "a", "Opération Neuve > Lot")
        assert r.status_code == 200, r.text
        assert r.json()["etat"] == "acceptee"
    assert (racine / "Projets/Opération Neuve/Lot/C1-Alpha/taches/a.md").is_file()
    assert not (racine / "Projets/C1-Alpha").exists()
    neuf = (racine / "Projets/Opération Neuve/Lot/C1-Alpha/contexte.md").read_text("utf-8")
    assert "parent:" not in neuf  # INV-ARBRE-2 : le dossier fait foi, l'ancien parent: est retiré


def test_operation_existante_rejoint_son_dossier(tmp_path, faux):
    cfg = config_de(tmp_path, base=OPS)
    depot(cfg)
    with client(cfg, faux) as c:
        _, r = accepter_operation(c, "a", "op")  # casse indifférente
        assert r.status_code == 200, r.text
    assert (cfg.vault.racine / "Projets/Op/C1-Alpha/taches/a.md").is_file()


def test_operation_tour_ailleurs_passe_tour_dans_le_projet_bloque(tmp_path, faux):
    faux.scenario = ["attendre"]
    cfg = config_de(tmp_path, base=OPS)
    depot(cfg)
    with client(cfg, faux) as c:
        lancer_tour(c, "g")  # Gamma : ailleurs
        _, r = accepter_operation(c, "a", "Op")
        assert r.status_code == 200, r.text
        lancer_tour(c, "b")  # Beta est maintenant frère d'Alpha, pas dedans : on bloque Alpha
        lancer_tour(c, "a")
        n, r = accepter_operation(c, "a", "Neuve")
        assert r.status_code == 409 and "Alpha un" in r.json()["detail"]
        etats = [p["etat"] for p in c.get("/api/propositions").json() if p["n"] == n]
        assert etats == ["en_attente"]  # INV-EXEC-5 : un refus laisse la proposition en attente
        assert (cfg.vault.racine / "Projets/Op/C1-Alpha").is_dir()
        for i in ("a", "b", "g"):
            c.post(f"/api/taches/{i}/arret", headers=H)


def test_operation_sans_contexte_409_et_toujours_en_attente(tmp_path, faux):
    cfg = config_de(tmp_path, {"Projets/Sans/taches/x.md": tache_md(titre="X")}, base=OPS)
    with client(cfg, faux) as c:
        n, r = accepter_operation(c, "x", "Op")
        assert r.status_code == 409 and "promouvez" in r.json()["detail"]
        assert [p["etat"] for p in c.get("/api/propositions").json() if p["n"] == n] == ["en_attente"]
