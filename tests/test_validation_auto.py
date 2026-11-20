"""INV-VALID-2 : validation automatique par périmètre — héritage du réglage, clôture seulement sur
contrôle réussi + revue IA indépendante GO + fiche R1, refus motivé sinon, exclusions, journal,
« Rouvrir », audit par échantillon."""

import asyncio
import subprocess

import pytest
from fastapi.testclient import TestClient

from conftest import FauxHarnais, ecrire, scenario_ok, tache_md
from orchestrateur import validation_auto
from orchestrateur.api import creer_app
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur

VERIF = "import pathlib, sys\nsys.exit(0 if pathlib.Path('ok.txt').read_text().strip() == 'ok' else 3)\n"
GO = "Relu.\n<avis>\nverdict: ok\npoints:\n- [P2] nom flou\n</avis>"
P1 = "Relu.\n<avis>\nverdict: reserves\npoints:\n- [P1] INV-X violé : données perdues\n</avis>"
R1 = "resultat: branche gb/x\nessai: lancer x, attendu y\n"


def rendu(extra=R1):
    return f"Fini.\n<fiche>\nstatut: terminee\nfait: livré\n{extra}situation: prête\n</fiche>"


def git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


@pytest.fixture
def depot_git(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, "init", "-q")
    (d / "verif.py").write_text(VERIF, encoding="utf-8")
    (d / "ok.txt").write_text("ok", encoding="utf-8")
    git(d, "add", ".")
    git(d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return d


def contexte(racine, rel="Projets/C1-Alpha", **cles):
    corps = "".join(f"{k}: {v}\n" for k, v in cles.items())
    ecrire(racine, f"{rel}/contexte.md", f"---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\n{corps}---\n")


def projet_auto(racine, depot, controle='"{python} verif.py"', **cles):
    contexte(racine, depot=f'"{depot}"', controle=controle, validation="automatique",
             validation_accord='"posé à la main"', **cles)


def relecteur(texte):
    return type("Autre", (FauxHarnais,), {"nom": "autre", "lances": [], "arrets": [], "liberer": None,
                                          "scenario": [Evenement("fin", session="r-1", texte=texte)]})


def tour(config, vault, faux, autre=None, texte=None, ident="mere"):
    faux.scenario = scenario_ok(rendu=texte or rendu())
    registre = {"faux": faux}
    if autre:
        config.harnais["autre"] = {}
        registre["autre"] = autre

    async def scenario():
        m = Moteur(config, vault, registre)
        for p in m.revues.equipe.lister():
            m.revues.equipe.retirer(p["id"])
        m.soumettre(ident, "go")
        for _ in range(100):
            en_cours = [b for b in m.boucles.values() if not b.done()] + list(m.revues._fond)
            if not en_cours:
                break
            await asyncio.gather(*en_cours, return_exceptions=True)
        return m

    return asyncio.run(scenario())


# --- réglage et héritage ---------------------------------------------------------------------
def test_reglage_herite_du_projet_surcharge_par_sous_conteneur_et_tache(racine, vault):
    assert validation_auto.reglage(vault, "mere")["mode"] == "manuelle"  # défaut
    contexte(racine, validation="automatique", validation_echantillon=3)
    contexte(racine, "Projets/C1-Alpha/Sous", parent="C1 > C1-Alpha")
    vault.cfg.taches.append("Projets/*/*/taches/*.md")
    ecrire(racine, "Projets/C1-Alpha/Sous/taches/fille.md", tache_md(titre="Fille"))
    ecrire(racine, "Projets/C1-Alpha/Sous/taches/fils.md", tache_md(titre="Fils", extra="validation: manuelle\n"))
    r = validation_auto.reglage(vault, "fille")
    assert (r["mode"], r["declare_par"], r["echantillon"]) == ("automatique", "Projets/C1-Alpha", 3)
    assert validation_auto.reglage(vault, "fils")["mode"] == "manuelle"  # surcharge par tâche
    contexte(racine, "Projets/C1-Alpha/Sous", parent="C1 > C1-Alpha", validation="manuelle")
    assert validation_auto.reglage(vault, "fille")["mode"] == "manuelle"  # le plus proche l'emporte
    contexte(racine, validation="n-importe")
    assert validation_auto.reglage(vault, "mere")["mode"] == "manuelle"  # jamais présumée


def test_exclusions_par_defaut_et_reglables(racine, vault):
    ecrire(racine, "Projets/C1-Alpha/taches/dep.md", tache_md(titre="Déploiement en production du site"))
    t = vault.tache("dep")
    assert validation_auto.exclusion(t, list(validation_auto.EXCLUSIONS_DEFAUT)) == "deploi*"
    assert validation_auto.exclusion(vault.tache("mere"), list(validation_auto.EXCLUSIONS_DEFAUT)) == ""
    contexte(racine, validation="automatique", validation_exclusions="[mère]")
    r = validation_auto.reglage(vault, "mere")
    assert validation_auto.exclusion(vault.tache("mere"), r["exclusions"]) == "mère"


def test_exclusion_garde_de_publication_non_exclue_mais_publier_oui(racine, vault):
    ecrire(racine, "Projets/C1-Alpha/taches/g.md", tache_md(titre="Garde de publication : recenser les chemins"))
    ecrire(racine, "Projets/C1-Alpha/taches/p.md", tache_md(titre="Publier l'article"))
    ecrire(racine, "Projets/C1-Alpha/taches/m.md", tache_md(titre="Mailing interne, mailbox"))
    ecrire(racine, "Projets/C1-Alpha/taches/e.md", tache_md(titre="Envoi du courrier"))
    d = list(validation_auto.EXCLUSIONS_DEFAUT)
    assert validation_auto.exclusion(vault.tache("g"), d) == ""
    assert validation_auto.exclusion(vault.tache("p"), d) == "publier"
    assert validation_auto.exclusion(vault.tache("m"), d) == ""  # mot entier : « mail » n'attrape pas « mailing »
    assert validation_auto.exclusion(vault.tache("e"), d) == "envoi"


def test_exemptions_par_contexte_levent_une_exclusion(racine, vault):
    ecrire(racine, "Projets/C1-Alpha/taches/f.md", tache_md(titre="Facture de test interne"))
    contexte(racine, validation="automatique", validation_exemptions="[facture de test]")
    r = validation_auto.reglage(vault, "f")
    assert validation_auto.exclusion(vault.tache("f"), r["exclusions"], r["exemptions"]) == ""
    assert validation_auto.exclusion(vault.tache("f"), r["exclusions"]) == "facture"


def test_reevaluer_ecrit_un_motif_par_tache_sans_rien_clore(racine, config, vault, faux, depot_git):
    projet_auto(racine, depot_git)
    ecrire(racine, "Projets/C1-Alpha/taches/a.md", tache_md("fait", titre="Garde de publication"))
    ecrire(racine, "Projets/C1-Alpha/taches/b.md", tache_md("fait", titre="Publier l'article"))
    ecrire(racine, "Projets/C1-Alpha/taches/c.md", tache_md("a-faire", titre="Pas faite"))
    m = Moteur(config, vault, {"faux": faux})
    notes = m.validation_auto.reevaluer()
    assert set(notes) == {"a", "b"}
    assert "R1" in notes["a"]["motif"] and "exclusion « publier »" in notes["b"]["motif"]
    assert vault.tache("a").statut == "fait" and vault.tache("b").statut == "fait"
    assert m.validation_auto.journal.reevaluations().keys() == notes.keys()
    assert m.validation_auto.journal.entrees() == []


def test_relecteur_independant_autre_harnais_puis_autre_modele(config):
    config.harnais = {"faux": {}, "autre": {"familles": {"opus": "o-2"}}}
    c = validation_auto.relecteur(config, "faux", "")
    assert (c.harnais, c.modele) == ("autre", "o-2")
    config.harnais = {"faux": {"familles": {"opus": "m-a", "sonnet": "m-b"}}}
    assert validation_auto.relecteur(config, "faux", "m-a").modele == "m-b"
    config.harnais = {"faux": {}}
    assert validation_auto.relecteur(config, "faux", "") is None
    config.validation.revue_harnais = "faux"
    assert validation_auto.relecteur(config, "faux", "") is None  # même moteur que l'auteur


# --- clôture automatique -----------------------------------------------------------------------
def test_cloture_si_controle_revue_et_fiche_puis_journal_et_rouvrir(racine, config, vault, faux, depot_git):
    projet_auto(racine, depot_git)
    autre = relecteur(GO)
    m = tour(config, vault, faux, autre)
    assert vault.tache("mere").statut == "cloture"
    (e,) = m.validation_auto.clos_recents()
    assert e["tache"] == "mere" and e["revue"]["harnais"] == "autre" and e["revue"]["verdict"] == "ok"
    assert "@" in e["controle"]["reference"] and e["auteur"]["harnais"] == "faux"

    client = TestClient(creer_app(config, m), base_url=f"http://127.0.0.1:{config.port}")
    d = client.get("/api/decisions").json()
    assert [x["tache"] for x in d["clos_auto"]] == ["mere"]
    r = client.post("/api/validation-auto/rouvrir", json={"tache": "mere"}, headers={"X-Orchestrateur": "1"})
    assert r.status_code == 200 and vault.tache("mere").statut == "fait"
    assert m.validation_auto.clos_recents() == []
    assert client.post("/api/validation-auto/rouvrir", json={"tache": "mere"},
                       headers={"X-Orchestrateur": "1"}).status_code == 409


@pytest.mark.parametrize("cas, motif", [
    ("p1", "revue IA : 1 P1"),
    ("sans_essai", "fiche sans Résultat ou sans Essai"),
    ("controle_rouge", "contrôle requis non réussi"),
    ("sans_controle", "aucun contrôle automatique"),
    ("sans_relecteur", "aucun relecteur indépendant"),
])
def test_refus_laisse_a_valider_avec_motif(racine, config, vault, faux, depot_git, cas, motif):
    projet_auto(racine, depot_git, **({"validation_echantillon": 99}))
    texte, autre = None, relecteur(GO)
    if cas == "p1":
        autre = relecteur(P1)
    elif cas == "sans_essai":
        texte = rendu("resultat: branche gb/x\n")
    elif cas == "controle_rouge":
        (depot_git / "ok.txt").write_text("faux", encoding="utf-8")
    elif cas == "sans_controle":
        contexte(racine, depot=f'"{depot_git}"', validation="automatique")
    elif cas == "sans_relecteur":
        autre = None
    m = tour(config, vault, faux, autre, texte)
    statut = vault.tache("mere").statut
    assert statut == ("retour-humain" if cas == "controle_rouge" else "fait")
    if cas != "controle_rouge":  # un contrôle rouge rend déjà la main (INV-CONTROLE-1) : pas de cycle
        (e, *_) = m.validation_auto.journal.entrees()
        assert e["issue"] == "refus" and motif in e["motif"]
        client = TestClient(creer_app(config, m), base_url=f"http://127.0.0.1:{config.port}")
        (ligne,) = [d for d in client.get("/api/decisions").json()["decisions"] if d["tache"] == "mere"]
        assert ligne["genre"] == "validation" and motif in ligne["auto"]["motif"]


def _essai_tour(racine, config, vault, faux, depot_git, essai, fm=""):
    projet_auto(racine, depot_git, validation_echantillon=99)
    if fm:
        p = vault.tache("mere").chemin
        p.write_text(p.read_text(encoding="utf-8").replace("type: tache\n", f"type: tache\n{fm}", 1),
                     encoding="utf-8")
    return tour(config, vault, faux, relecteur(GO), rendu(f"resultat: branche gb/x\nessai: {essai}\n"))


def test_validation_auto_laisse_a_valider_un_essai_dans_l_interface(racine, config, vault, faux, depot_git):
    m = _essai_tour(racine, config, vault, faux, depot_git, "ouvrir 127.0.0.1:8310, cliquer le bouton Valider")
    assert vault.tache("mere").statut == "fait"
    (e, *_) = m.validation_auto.journal.entrees()
    assert e["issue"] == "refus" and "démontrable" in e["motif"]


def test_validation_auto_clot_un_essai_par_commande(racine, config, vault, faux, depot_git):
    _essai_tour(racine, config, vault, faux, depot_git, "pytest tests/test_x.py, attendu : vert")
    assert vault.tache("mere").statut == "cloture"


def test_marqueur_demontrable_oui_garde_un_essai_par_commande_a_valider(racine, config, vault, faux, depot_git):
    _essai_tour(racine, config, vault, faux, depot_git, "pytest tests/test_x.py", "demontrable: oui\n")
    assert vault.tache("mere").statut == "fait"


def test_marqueur_demontrable_non_force_l_automatique_malgre_l_interface(racine, config, vault, faux, depot_git):
    _essai_tour(racine, config, vault, faux, depot_git, "cliquer le bouton", "demontrable: non\n")
    assert vault.tache("mere").statut == "cloture"


def test_exclusion_ne_lance_pas_la_revue(racine, config, vault, faux, depot_git):
    projet_auto(racine, depot_git, validation_exclusions="[mère]")
    autre = relecteur(GO)
    m = tour(config, vault, faux, autre)
    assert vault.tache("mere").statut == "fait" and autre.lances == []
    assert "exclusion « mère »" in m.validation_auto.journal.entrees()[0]["motif"]


def test_echantillon_garde_une_cloture_sur_n_pour_l_utilisateur(racine, config, vault, faux, depot_git):
    projet_auto(racine, depot_git, validation_echantillon=1)
    m = tour(config, vault, faux, relecteur(GO))
    assert vault.tache("mere").statut == "fait"
    e = m.validation_auto.journal.entrees()[0]
    assert e["issue"] == "echantillon" and e["revue"]["verdict"] == "ok"


def test_validation_manuelle_ne_ferme_jamais(racine, config, vault, faux, depot_git):
    contexte(racine, depot=f'"{depot_git}"', controle='"{python} verif.py"')
    autre = relecteur(GO)
    m = tour(config, vault, faux, autre)
    assert vault.tache("mere").statut == "fait" and autre.lances == []
    assert m.validation_auto.journal.entrees() == []


def test_reglage_depuis_l_interface_trace_l_accord_sans_toucher_le_reste(racine, config, vault, faux):
    contexte(racine, depot='"X"', autre_cle="garde")
    m = Moteur(config, vault, {"faux": faux})
    client = TestClient(creer_app(config, m), base_url=f"http://127.0.0.1:{config.port}")
    h = {"X-Orchestrateur": "1"}
    r = client.post("/api/validation-auto/reglage", json={"conteneur": "Projets/C1-Alpha", "mode": "automatique"}, headers=h)
    assert r.status_code == 200
    texte = (racine / "Projets/C1-Alpha/contexte.md").read_text("utf-8")
    assert "validation: automatique" in texte and "validation_accord:" in texte and "autre_cle: garde" in texte
    assert client.get("/api/validation-auto/reglage", params={"conteneur": "Projets/C1-Alpha"}).json()["mode"] == "automatique"
    assert validation_auto.reglage(vault, "mere")["mode"] == "automatique"
    assert client.post("/api/validation-auto/reglage", json={"conteneur": "Projets/C1-Alpha", "mode": "x"},
                       headers=h).status_code == 400
    assert client.post("/api/validation-auto/reglage", json={"conteneur": "Projets/Inconnu", "mode": "manuelle"},
                       headers=h).status_code == 404
