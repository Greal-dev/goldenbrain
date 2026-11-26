"""Lot 7 : promotion sur place, mandat de découpage (INV-TRANSFO-1), proposition « projet »."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, fiches
from orchestrateur import transformations as T
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import RENDU, ecrire, scenario_ok, tache_md
from test_moteur import executer, finir, moteur, vider

H = {"X-Orchestrateur": "1"}
PROJET = "Projets/C1-Alpha/Lancement"
DECOUPAGE = """Voici le découpage.
<decoupage>
resume: Lancer la   campagne d'automne.
- titre: Écrire le brief
  description: Un brief d'une page.
    Validé par l'utilisateur.
- titre: Choisir les canaux
  description: Trois canaux au plus.
- titre: Enfant
  description: déjà présent dans le projet
- titre: Mesurer
  description: Tableau de bord en place.
</decoupage>
"""


@pytest.fixture(autouse=True)
def sous_projets(config):
    config.vault.taches.append("Projets/*/*/taches/*.md")


def tickets(vault):
    return {t.titre: t for t in vault.index()[0].values() if t.conteneur == PROJET}


def promouvoir_et_finir(config, vault, faux, decouper=True):
    async def scenario():
        m = moteur(config, vault, faux)
        rel = T.promouvoir(m, "mere", "Lancement", decouper)
        await finir(m)
        return m, rel, vider(m)
    return executer(scenario())


# --- promotion sur place -----------------------------------------------------------------
def test_promotion_sur_place_arbre_et_fil_ariane(config, vault, faux, racine):
    ecrire(racine, "Projets/C1-Alpha/taches/autre.md", tache_md(titre="Autre"))
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        r = c.post("/api/taches/mere/promouvoir", headers=H, json={"nom": "Lancement",
                                                                   "decouper": False})
        assert r.status_code == 200 and r.json()["conteneur"] == PROJET
        assert r.json()["tache"]["fil_ariane"] == ["C1", "Operation-X", "Alpha", "Lancement"]
        alpha = trouver(c.get("/api/arbre").json()["noeuds"], "Projets/C1-Alpha")
        assert {(n["type"], n["id"]) for n in alpha["enfants"]} == {
            ("tache", "autre"), ("conteneur", PROJET)}
        projet = trouver(alpha["enfants"], PROJET)
        assert projet["titre"] == "Lancement"
        assert {n["id"] for n in projet["enfants"]} == {"mere", "enfant"}  # enfant devenu ticket
        r = c.post("/api/taches/autre/promouvoir", headers=H, json={"nom": "Lancement"})
        assert r.status_code == 409  # le dossier existe
    assert "parent" not in fiches.frontmatter(fiches.lire(racine / PROJET / "contexte.md"))


def trouver(noeuds, ident):
    for n in noeuds:
        if n["id"] == ident:
            return n
        if x := trouver(n["enfants"], ident):
            return x
    return None


def test_promotion_sans_nom_prend_le_titre_et_refuse_hors_motifs(config, vault, faux, racine):
    m = Moteur(config, vault, {"faux": faux})
    assert T.promouvoir(m, "x", None, decouper=False) == "Projets/Sans/X"
    config.vault.taches.remove("Projets/*/*/taches/*.md")
    avant = sorted(p.as_posix() for p in racine.rglob("*"))
    with pytest.raises(T.Conflit, match="motifs"):
        T.promouvoir(m, "mere", "Profond", decouper=False)
    assert sorted(p.as_posix() for p in racine.rglob("*")) == avant


def test_decouper_faux_aucun_message(config, vault, faux):
    m, rel, _ = promouvoir_et_finir(config, vault, faux, decouper=False)
    assert rel == PROJET and faux.lances == [] and m.mandats.attente == {}


# --- découpage ---------------------------------------------------------------------------
def test_decoupage_cree_les_tickets_ignore_le_doublon_et_ecrit_le_resume(config, vault, faux,
                                                                          racine):
    faux.scenario = scenario_ok(rendu=DECOUPAGE + RENDU)
    m, _, evts = promouvoir_et_finir(config, vault, faux)
    message = faux.lances[0]["message"]
    assert "élevée en projet « Lancement »" in message and "« Enfant »" in message
    assert "« Mère »" not in message  # la tâche promue n'est pas un ticket existant
    t = tickets(vault)
    assert {"Écrire le brief", "Choisir les canaux", "Mesurer"} <= set(t)
    assert sum(x.titre == "Enfant" for x in vault.index()[0].values()) == 1
    brief = t["Écrire le brief"]
    assert brief.statut == "a-faire" and brief.fm["palier"] == "P1"
    assert "Un brief d'une page.\nValidé par l'utilisateur." in fiches.lire(brief.chemin)
    assert m.etat_de(brief.id) == "inactif" and len(faux.lances) == 1  # non lancés
    fin = next(e for e in evts if e["type"] == "tour_fin")
    assert fin["decoupage"] == 3
    ctx = fiches.lire(racine / PROJET / "contexte.md")
    assert ctx.count("Résumé : ") == 1 and "Résumé : Lancer la campagne d'automne." in ctx
    assert json.loads((config.donnees / "etat" / "mandats.json").read_text("utf-8")) == {}


def test_resume_remplace(vault, racine):
    vault.cfg.taches.append("Projets/*/*/taches/*.md")
    rel = T.creer_projet(vault, "mere", "Lancement")
    T._ecrire_resume(vault, rel, "premier")
    T._ecrire_resume(vault, rel, "second")
    texte = fiches.lire(racine / rel / "contexte.md")
    assert "Résumé : second" in texte and "premier" not in texte
    assert "Issu de la tâche [[mere]]" in texte


@pytest.mark.parametrize("rendu", [
    "<decoupage>\nresume: r\n- titre: Seul\n  description: d\n</decoupage>\n" + RENDU,
    RENDU])
def test_decoupage_insuffisant_rien_cree(config, vault, faux, rendu):
    faux.scenario = scenario_ok(rendu=rendu)
    m, _, evts = promouvoir_et_finir(config, vault, faux)
    assert set(tickets(vault)) == {"Mère", "Enfant", "Petit"}
    assert next(e for e in evts if e["type"] == "tour_fin")["decoupage"] == "insuffisant"
    assert "Découpage insuffisant" in vault.tache("mere").fiche["situation"]
    # Seconde chance : le mandat attend la relance, puis s'efface si elle échoue aussi.
    assert m.mandats.attente["mere"]["essais"] == 1
    from orchestrateur import transformations
    assert transformations.conclure(m, "mere", rendu, {}) == "insuffisant"
    assert m.mandats.attente == {}


def test_mandat_persistant_tour_interrompu_jamais_relance(config, vault, faux):
    faux.scenario = [Evenement("session", session="s"), "attendre"]

    async def scenario():
        m1 = moteur(config, vault, faux)
        T.promouvoir(m1, "mere", "Lancement")
        while not faux.lances:
            await asyncio.sleep(0)
        await m1.arreter("mere")  # interrompu : le mandat reste en attente
        await finir(m1)
        assert m1.mandats.attente["mere"]["type"] == "decoupage"
        m2 = Moteur(config, vault, {"faux": faux})  # « redémarrage »
        await asyncio.sleep(0.02)
        assert m2.mandats.attente["mere"]["projet"] == "Lancement"
        assert len(faux.lances) == 1 and m2.boucles == {}  # INV-TRANSFO-1 : rien relancé
        # Geste humain : un message ordinaire ; le tour qui suit répond au mandat.
        faux.scenario = scenario_ok(rendu=DECOUPAGE + RENDU)
        m2.soumettre("mere", "reprends le découpage")
        await finir(m2)
        return m2

    m2 = executer(scenario())
    assert m2.mandats.attente == {} and "Mesurer" in tickets(vault)


def test_bloc_decoupage_retire_du_texte_affiche():
    affiche = fiches.sans_rendu("Avant.\n" + DECOUPAGE + RENDU)
    assert affiche.startswith("Avant.\nVoici le découpage.") and affiche.endswith("Travail fait.")
    assert "decoupage>" not in affiche and "Écrire le brief" not in affiche


def test_analyse_tolerante():
    resume, t = T.analyser_decoupage("<decoupage>\n- titre: A\ndescription: x\nRésumé: R\n"
                                     "- titre:  \n- titre: B\n</decoupage>")
    assert resume == "R" and t == [{"titre": "A", "description": "x"},
                                   {"titre": "B", "description": ""}]
    assert T.analyser_decoupage("rien") is None


def test_proposition_projet_acceptee_promeut_et_mandate(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.trancher(m.proposer("projet", "mere", "Lancement", de="mere")["n"], True)
        await finir(m)

    executer(scenario())
    assert vault.tache("mere").conteneur == PROJET
    assert "élevée en projet « Lancement »" in faux.lances[0]["message"]


# --- nouveau groupe ----------------------------------------------------------------------
def _client(config, vault, faux):
    return TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                      base_url="http://127.0.0.1:8399")


def test_creer_tache_dans_un_nouveau_groupe(config, vault, faux, racine):
    with _client(config, vault, faux) as c:
        r = c.post("/api/taches", headers=H, json={"titre": "Plan du livre", "nouveau_groupe": {
            "nom": "Mon Livre", "dans": "Projets/C1-Alpha"}})
        assert r.status_code == 201 and r.json()["conteneur"] == "Projets/C1-Alpha/Mon-Livre"
        assert r.json()["fil_ariane"][-1] == "Mon Livre"
    ctx = fiches.lire(racine / "Projets/C1-Alpha/Mon-Livre/contexte.md")
    assert "type: contexte" in ctx and "nom: Mon Livre" in ctx and "projet: Mon-Livre" in ctx
    assert "casquette: C1\n" in ctx and "created: " in ctx and "updated: " in ctx
    assert vault.conteneur("Projets/C1-Alpha/Mon-Livre").casquette == "C1"


def test_nouveau_groupe_ignore_le_plafond_du_rangement(config, vault, faux, racine):
    for i in range(12):
        ecrire(racine, f"Projets/C1-Alpha/taches/t{i}.md", tache_md(titre=f"Affaire {i}"))
    with _client(config, vault, faux) as c:
        r = c.post("/api/taches", headers=H, json={"titre": "Quelque chose", "nouveau_groupe": {
            "nom": "Neuf", "dans": "Projets/C1-Alpha"}})
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("groupe, code", [({"nom": "  ", "dans": "Projets/C1-Alpha"}, 400),
                                          ({"nom": "G", "dans": "Projets/Inconnu"}, 404),
                                          ({"nom": "taches", "dans": "Projets/C1-Alpha"}, 409)])
def test_nouveau_groupe_refuse(config, vault, faux, racine, groupe, code):
    avant = sorted(p.as_posix() for p in racine.rglob("*"))
    with _client(config, vault, faux) as c:
        r = c.post("/api/taches", headers=H, json={"titre": "Plan", "nouveau_groupe": groupe})
        assert r.status_code == code and r.json()["detail"]
    assert sorted(p.as_posix() for p in racine.rglob("*")) == avant


def test_post_conteneurs_cree_le_groupe_seul(config, vault, faux, racine):
    with _client(config, vault, faux) as c:
        r = c.post("/api/conteneurs", headers=H, json={"nom": "Livres", "dans": "Projets/Vide"})
        assert r.status_code == 201 and r.json() == {"id": "Projets/Vide/Livres"}
        r = c.post("/api/conteneurs", headers=H, json={"nom": "Livres", "dans": "Projets/Vide"})
        assert r.status_code == 409
        assert any(x["id"] == "Projets/Vide/Livres" for x in c.get("/api/conteneurs").json())
    assert (racine / "Projets/Vide/Livres/taches").is_dir()
    assert "casquette: C3" in fiches.lire(racine / "Projets/Vide/Livres/contexte.md")


def test_post_conteneurs_cree_un_projet_sous_le_dossier_de_casquette(config, vault, faux, racine):
    config.vault.taches.append("Casquettes/*/*/taches/*.md")
    (racine / "Casquettes/C4-Ecrits").mkdir(parents=True)
    with _client(config, vault, faux) as c:
        r = c.post("/api/conteneurs", headers=H, json={"nom": "Roman", "dans": "Casquettes/C4-Ecrits"})
        assert r.status_code == 201 and r.json() == {"id": "Casquettes/C4-Ecrits/Roman"}
    assert vault.conteneur("Casquettes/C4-Ecrits/Roman").casquette == "C4"


@pytest.mark.parametrize("dans", ["Casquettes/Absente", "Casquettes/..", "Casquettes", "Autre/C4-Ecrits"])
def test_post_conteneurs_refuse_un_dossier_hors_casquette(config, vault, faux, racine, dans):
    config.vault.taches.append("Casquettes/*/*/taches/*.md")
    (racine / "Casquettes/C4-Ecrits").mkdir(parents=True)
    (racine / "Autre/C4-Ecrits").mkdir(parents=True)
    avant = sorted(p.as_posix() for p in racine.rglob("*"))
    with _client(config, vault, faux) as c:
        assert c.post("/api/conteneurs", headers=H, json={"nom": "Roman", "dans": dans}).status_code == 404
    assert sorted(p.as_posix() for p in racine.rglob("*")) == avant
