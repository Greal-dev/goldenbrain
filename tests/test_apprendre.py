"""INV-APPRENDRE-1 : mode « Apprendre » — consigne ajoutée seulement si actif, réglage de tâche prioritaire, fiche `retenir`."""

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, apprendre, fiches
from orchestrateur.apprendre import ConfigApprendre
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Vault
from test_api import H

T = "Projets/C1-Alpha/taches/"


@pytest.fixture
def moteur(config, racine, faux):
    ecrire(racine, T + "libre.md", tache_md("a-faire", titre="Libre"))
    ecrire(racine, T + "oui.md", tache_md("a-faire", titre="Oui", extra="apprendre: oui\n"))
    ecrire(racine, T + "non.md", tache_md("a-faire", titre="Non", extra="apprendre: non\n"))
    return Moteur(config, Vault(config.vault), {"faux": faux})


def test_inactif_la_consigne_est_inchangee(moteur):
    assert "Apprendre" not in moteur._consigne("libre")
    assert apprendre.consigne(moteur.config, {}) == ""


def test_actif_la_consigne_demande_explications_et_retenir(moteur):
    moteur.config.apprendre.actif = True
    c = moteur._consigne("libre")
    assert c.endswith(apprendre.texte_consigne()) and "[!apprendre]" in c and "retenir:" in c
    assert "Apprendre" not in moteur._consigne("non")


def test_reglage_de_tache_l_emporte(moteur):
    assert "Apprendre" in moteur._consigne("oui") and "Apprendre" not in moteur._consigne("non")
    moteur.config.apprendre.actif = True
    assert "Apprendre" in moteur._consigne("oui") and "Apprendre" not in moteur._consigne("non")


def test_valeur_invalide_refusee():
    with pytest.raises(ValueError, match="apprendre.actif"):
        ConfigApprendre(actif="oui")


def test_fiche_retenir_aller_retour_et_absente_sans_mode():
    texte = "<fiche>\nstatut: terminee\nfait: x\nretenir: a ; b ; c\n</fiche>"
    f = fiches.analyser_rendu(texte)
    assert f["retenir"] == "a ; b ; c"
    bloc = fiches.rendre_bloc(f)
    assert "- **Ce que vous pouvez retenir** : a ; b ; c" in bloc
    assert fiches.lire_fiche(bloc)["retenir"] == "a ; b ; c"
    sans = fiches.rendre_bloc(fiches.analyser_rendu("<fiche>\nstatut: terminee\nfait: x\n</fiche>"))
    assert "retenir" not in sans


def test_api_general_et_tache(moteur, config, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[vault]\nracine = \"x\"\n", encoding="utf-8")
    config.chemin = cfg
    with TestClient(api.creer_app(config, moteur), base_url="http://127.0.0.1:8399") as c:
        assert c.get("/api/apprendre").json() == {"actif": False}
        assert c.put("/api/apprendre", headers=H, json={"actif": True}).json() == {"actif": True}
        assert "[apprendre]\nactif = true" in cfg.read_text(encoding="utf-8")
        assert config.apprendre.actif
        t = c.post("/api/taches/libre/apprendre", headers=H, json={"valeur": False}).json()
        assert t["frontmatter"]["apprendre"] == "non" and "Apprendre" not in moteur._consigne("libre")
        t = c.post("/api/taches/libre/apprendre", headers=H, json={"valeur": None}).json()
        assert "apprendre" not in t["frontmatter"] and "Apprendre" in moteur._consigne("libre")
        assert c.put("/api/apprendre", headers=H, json={"actif": "peut-être"}).status_code in (400, 422)


@pytest.mark.parametrize("code", ["en", "de", "es"])
def test_consigne_servie_dans_la_langue_reglee(code):
    """INV-LANGUE-1 : la consigne suit la langue ; encadré `[!apprendre]` et champ `retenir:` restent tels quels."""
    from orchestrateur import langues
    fr = apprendre.texte_consigne()
    try:
        langues.regler(code)
        x = apprendre.texte_consigne()
    finally:
        langues.regler("fr")
    assert x != fr and "[!apprendre]" in x and "retenir:" in x and "<fiche>" in x and "prochain_pas" in x
