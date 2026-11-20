"""Modèles de tâches (INV-MODELES-1) : un fichier Markdown par modèle, lecture seule, fichier illisible écarté,
tri par `ordre` ; les modèles livrés couvrent la galerie demandée et la démonstration des premiers pas."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrateur import modeles


def _ecrire(dossier, nom, texte):
    (dossier / nom).write_text(texte, encoding="utf-8")


def test_lister_trie_par_ordre_et_ecarte_les_fichiers_invalides(tmp_path):
    _ecrire(tmp_path, "b.md", "---\ntitre: Bêta\nresume: second\nordre: 20\n---\nFaire B.\n")
    _ecrire(tmp_path, "a.md", "---\ntitre: Alpha\nordre: 10\n---\n\nFaire A.\n")
    _ecrire(tmp_path, "sans-ordre.md", "---\ntitre: Zêta\n---\nFaire Z.\n")
    _ecrire(tmp_path, "sans-titre.md", "---\nresume: rien\n---\nCorps.\n")
    _ecrire(tmp_path, "vide.md", "---\ntitre: Vide\n---\n\n")
    _ecrire(tmp_path, "casse.md", "---\ntitre: [non fermé\n---\nCorps.\n")
    _ecrire(tmp_path, "gros.md", "---\ntitre: Gros\n---\n" + "x" * (modeles.MAX_OCTETS + 1))
    _ecrire(tmp_path, "note.txt", "---\ntitre: Pas un modèle\n---\nCorps.\n")
    liste = modeles.lister(tmp_path)
    assert [m["id"] for m in liste] == ["a", "b", "sans-ordre"]
    assert liste[0] == {"id": "a", "titre": "Alpha", "resume": "", "mission": "Faire A.", "ordre": 10}
    assert liste[1]["resume"] == "second" and liste[2]["ordre"] == 999


def test_dossier_absent_donne_une_liste_vide(tmp_path):
    assert modeles.lister(tmp_path / "absent") == []


def test_modeles_livres_couvrent_la_galerie_et_la_demonstration():
    liste = modeles.lister()
    ids = [m["id"] for m in liste]
    assert ids[0] == "premiere-tache"  # la démonstration des premiers pas en dépend (web/premiers-pas.js)
    attendus = {"creer-un-petit-site", "analyser-un-tableau", "rediger-un-courrier", "automatiser-une-tache",
                "resumer-des-documents", "apprendre-une-notion"}
    assert attendus <= set(ids)
    assert all(m["titre"] and m["resume"] and m["mission"] for m in liste)


def test_route_sert_les_modeles_du_dossier(tmp_path):
    _ecrire(tmp_path, "un.md", "---\ntitre: Un\n---\nMission.\n")
    app = FastAPI()
    app.include_router(modeles.routes(tmp_path))
    with TestClient(app) as c:
        r = c.get("/api/modeles")
    assert r.status_code == 200 and [m["id"] for m in r.json()] == ["un"]


def test_modele_lu_dans_la_langue_avec_repli_sur_le_francais(tmp_path):
    """INV-LANGUE-1 : `<dossier>/<code>/<nom>` traduit un modèle ; absent ou invalide, le français sert."""
    _ecrire(tmp_path, "a.md", "---\ntitre: Alpha\nordre: 1\n---\nFaire A.\n")
    _ecrire(tmp_path, "b.md", "---\ntitre: Bêta\nordre: 2\n---\nFaire B.\n")
    _ecrire(tmp_path, "c.md", "---\ntitre: Gamma\nordre: 3\n---\nFaire C.\n")
    (tmp_path / "en").mkdir()
    _ecrire(tmp_path / "en", "a.md", "---\ntitre: Alpha EN\nordre: 1\n---\nDo A.\n")
    _ecrire(tmp_path / "en", "c.md", "---\nresume: sans titre\n---\nDo C.\n")
    _ecrire(tmp_path / "en", "seul.md", "---\ntitre: Orphelin\n---\nIgnoré.\n")
    en = modeles.lister(tmp_path, "en")
    assert [(m["id"], m["titre"], m["mission"]) for m in en] == [("a", "Alpha EN", "Do A."), ("b", "Bêta", "Faire B."), ("c", "Gamma", "Faire C.")]
    assert [m["titre"] for m in modeles.lister(tmp_path, "de")] == ["Alpha", "Bêta", "Gamma"]
    assert [m["titre"] for m in modeles.lister(tmp_path, "fr")] == ["Alpha", "Bêta", "Gamma"]


def test_modeles_livres_traduits_dans_chaque_langue():
    fr = {m["id"]: m for m in modeles.lister(langue="fr")}
    for code in ("en", "de", "es"):
        assert sorted(p.name for p in (modeles.DOSSIER / code).glob("*.md")) == sorted(f"{i}.md" for i in fr)
        traduits = modeles.lister(langue=code)
        assert [m["id"] for m in traduits] == list(fr)  # même ordre : la démonstration reste en tête
        assert all(m["titre"] != fr[m["id"]]["titre"] and m["mission"] for m in traduits)
