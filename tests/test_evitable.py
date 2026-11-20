"""Pastille « évitable ? » de Décisions : réglage persisté, critères, seuil, exclusion sensible (INV-EVITABLE-1)."""

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, decisions, evitable
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from test_api import BASE, H


@pytest.fixture
def monde(config, vault, faux, racine):
    t = "Projets/C1-Alpha/taches/"
    ecrire(racine, t + "v-ok.md", tache_md("fait", "session: s-1\n", "Ranger les notes"))
    ecrire(racine, t + "v-demo.md", tache_md("fait", "session: s-2\n", "Afficher la page"))
    ecrire(racine, t + "v-sens.md", tache_md("fait", "session: s-3\n", "Envoyer la facture"))
    ecrire(racine, t + "v-vide.md", tache_md("fait", "session: s-4\n", "Sans fiche"))
    ecrire(racine, t + "q-perm.md", tache_md("retour-humain", 'commentaire: "Veux-tu que je procède ?"\n', "Q perm"))
    for ident, essai in (("v-ok", "lancer pytest"), ("v-demo", "ouvrir la page"), ("v-sens", "lancer pytest")):
        vault.modifier(ident, {}, {**vault.tache(ident).fiche, "resultat": "src/x.py", "essai": essai, "fait": "fait"})
    return Moteur(config, vault, {"faux": faux})


def pastilles(monde) -> dict:
    return {d["tache"]: d.get("evitable") for d in decisions.rassembler(monde)["decisions"]}


def test_defaut_active_75_et_critères_listés(monde):
    assert evitable.lire(monde.config.donnees) == {"actif": True, "seuil": 75}
    ev = pastilles(monde)["v-ok"]
    assert (ev["score"], ev["sur"]) == (3, 4)  # pas de contrôle déclaré : un critère manque
    assert "✗ contrôle réussi et non périmé" in ev["motif"] and "✓ fiche avec Résultat et Essai" in ev["motif"]


def test_demontrable_exclusion_et_fiche_vide_sans_pastille(monde):
    p = pastilles(monde)
    assert p["v-demo"] is None  # 2/4 sous le seuil
    assert p["v-sens"] is None  # « facture » : exclusion sensible, toujours écartée
    assert p["v-vide"] is None  # fiche vide


def test_question_de_permission_dans_perimetre_automatique(monde, racine):
    assert pastilles(monde)["q-perm"] is None  # 1/2 : périmètre non automatique
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nparent: \"[[Operation-X]]\"\nnom: Alpha\nvalidation: automatique\n---\n")
    assert pastilles(monde)["q-perm"]["sur"] == 2


def test_seuil_et_desactivation_changent_le_resultat(monde):
    d = monde.config.donnees
    evitable.regler(d, seuil=100)
    assert pastilles(monde)["v-ok"] is None  # 3/4 < 100 %
    evitable.regler(d, seuil=50)
    assert pastilles(monde)["v-demo"] is not None  # 2/4 atteint 50 %
    evitable.regler(d, actif=False)
    assert all(v is None for v in pastilles(monde).values())


def test_reglage_valide_et_tolere_un_fichier_illisible(monde):
    d = monde.config.donnees
    with pytest.raises(Invalide):
        evitable.regler(d, seuil=10)
    (d / "etat" / "evitable.json").write_text("{pas du json", encoding="utf-8")
    assert evitable.lire(d) == {"actif": True, "seuil": 75}


def test_routes_get_put(monde):
    with TestClient(api.creer_app(monde.config, monde), base_url=BASE) as c:
        _routes(c)


def _routes(c):
    assert c.get(BASE + "/api/decisions/evitable").json() == {"actif": True, "seuil": 75}
    assert c.put(BASE + "/api/decisions/evitable", headers=H, json={"seuil": 60}).json() == {"actif": True, "seuil": 60}
    assert c.put(BASE + "/api/decisions/evitable", headers=H, json={"seuil": 5}).status_code == 400
    assert c.get(BASE + "/api/decisions/evitable").json()["seuil"] == 60
