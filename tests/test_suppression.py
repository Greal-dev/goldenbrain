"""Suppression d'une tâche ou d'un projet : tout ou rien, références nettoyées, archives (INV-SUPPR-1)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, fiches
from orchestrateur import suppression as S
from orchestrateur.alignement import Aligneur
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, aujourdhui
from conftest import ecrire, tache_md
from test_moteur import executer, finir, moteur

H = {"X-Orchestrateur": "1"}
ALPHA = "Projets/C1-Alpha"
SOUS = f"{ALPHA}/Sous"


@pytest.fixture(autouse=True)
def monde(config, racine):
    config.vault.taches += ["Projets/*/*/taches/*.md", "Casquettes/*/taches/*.md"]
    ecrire(racine, f"{SOUS}/contexte.md", "---\ntype: contexte\ncasquette: C1\n---\n\n# Sous\n")
    ecrire(racine, f"{SOUS}/taches/s1.md", tache_md(titre="S un"))
    ecrire(racine, f"{SOUS}/taches/s2.md", tache_md(extra="parent: s1\n", titre="S deux"))
    ecrire(racine, f"{SOUS}/pieces/contrat.pdf", "PDF")
    ecrire(racine, "Projets/C2-Beta/taches/lie.md", tache_md(
        extra="alimente: [mere, doublon]\nvoir_aussi: [\"[[enfant]]\"]\n", titre="Liée")
        + "\n<!-- orchestrateur:livrables -->\n- [x] Mère · 2026-11-01 · Moi · [[mere]]\n"
          "<!-- orchestrateur:livrables-fin -->\n")
    ecrire(racine, "Casquettes/C1-Pro/contexte.md", "---\ntype: contexte\ncasquette: C1\n---\n")


def photo(racine):
    return {p.relative_to(racine).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(racine.rglob("*"))}


def lancer(config, vault, faux, fn, avant=None):
    async def scenario():
        m = moteur(config, vault, faux)
        try:
            if avant:
                await avant(m)
            return m, await S.supprimer(m, Aligneur(vault, []), lambda: fn(m))
        finally:
            await finir(m)
    return executer(scenario())


def tache(config, vault, faux, ident, mode=None, vers=None):
    return lancer(config, vault, faux, lambda m: S.plan_tache(m, ident, mode, vers))


def projet(config, vault, faux, cid, mode=None, vers=None):
    return lancer(config, vault, faux, lambda m: S.plan_projet(m, Aligneur(vault, []), cid, mode, vers))


def test_suppression_simple(config, vault, faux, racine):
    _, r = tache(config, vault, faux, "x")
    assert r["supprimees"] == 1 and not (racine / "Projets/Sans/taches/x.md").exists()
    assert "x" not in vault.index()[0]
    journal = (config.donnees / "journal/suppressions.jsonl").read_text("utf-8")
    assert '"cible": "x"' in journal and '"qui": "moi"' in journal


def test_sous_taches_supprimees_avec(config, vault, faux, racine):
    _, r = tache(config, vault, faux, "mere", "supprimer")
    assert r["supprimees"] == 3
    assert not any(k in vault.index()[0] for k in ("mere", "enfant", "petit"))


def test_sous_taches_deplacees_parent_reecrit(config, vault, faux, racine):
    _, r = tache(config, vault, faux, "mere", "deplacer", "Projets/C2-Beta")
    taches = vault.index()[0]
    assert "mere" not in taches and r["deplacees"] == 1
    assert taches["enfant"].conteneur == "Projets/C2-Beta" and "parent" not in taches["enfant"].fm
    assert taches["petit"].conteneur == "Projets/C2-Beta" and taches["petit"].parent_brut == "enfant"


def test_sous_taches_deplacees_par_defaut_sous_le_parent(config, vault, faux):
    tache(config, vault, faux, "enfant", "deplacer")
    assert vault.index()[0]["petit"].parent_brut == "mere"


def test_references_nettoyees_chez_une_tache_liee(config, vault, faux, racine):
    tache(config, vault, faux, "mere", "supprimer")
    t = vault.tache("lie")
    assert t.fm["alimente"] == ["doublon"] and "voir_aussi" not in t.fm
    assert "[[mere]]" not in fiches.lire(t.chemin)


def test_refus_409_tour_en_cours(config, vault, faux, racine):
    faux.scenario = [Evenement("session", session="s"), "attendre"]
    avant = photo(racine)

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("petit", "travaille")
        while not faux.lances:
            await asyncio.sleep(0)
        try:
            with pytest.raises(Conflit, match="arrêtez"):
                await S.supprimer(m, Aligneur(vault, []), lambda: S.plan_tache(m, "mere", "supprimer", None))
        finally:
            await m.arreter("petit")
            await finir(m)

    executer(scenario())
    assert (racine / f"{ALPHA}/taches/mere.md").read_bytes() == avant[f"{ALPHA}/taches/mere.md"]


@pytest.mark.parametrize("cid", ["Casquettes/C1-Pro", "_meta"])
def test_refus_casquette_et_racine(config, vault, faux, racine, cid):
    avant = photo(racine)
    with pytest.raises(Conflit, match="ne peut pas être supprimé"):
        projet(config, vault, faux, cid, "supprimer")
    assert photo(racine) == avant


def test_projet_annexe_rangee_intacte_et_contexte_efface(config, vault, faux, racine):
    _, r = projet(config, vault, faux, SOUS, "supprimer")
    jour = aujourdhui().isoformat()
    assert (racine / f"Archives/supprimes/{jour}/{SOUS}/pieces/contrat.pdf").read_bytes() == b"PDF"
    assert not (racine / SOUS).exists() and r["supprimees"] == 2 and r["ranges"] == 1
    assert (racine / f"{ALPHA}/contexte.md").is_file()


def test_projet_contenu_deplace(config, vault, faux, racine):
    _, r = projet(config, vault, faux, ALPHA, "deplacer", "Projets/C2-Beta")
    taches = vault.index()[0]
    assert taches["mere"].conteneur == "Projets/C2-Beta" and taches["petit"].parent_brut == "enfant"
    assert taches["s1"].conteneur == "Projets/C2-Beta/Sous"  # le sous-projet garde son dossier entier
    assert (racine / "Projets/C2-Beta/Sous/pieces/contrat.pdf").is_file()
    assert not (racine / ALPHA).exists()


def test_tout_ou_rien_echec_au_milieu(config, vault, faux, racine, monkeypatch):
    avant = photo(racine)
    vrai, n = S._effacer, []

    def panne(p):
        n.append(p)
        if len(n) == 2:
            raise OSError("disque plein")
        vrai(p)

    monkeypatch.setattr(S, "_effacer", panne)
    with pytest.raises(Conflit, match="rien n'a changé"):
        projet(config, vault, faux, SOUS, "supprimer")
    assert photo(racine) == avant
    with pytest.raises(Conflit, match="rien n'a changé"):
        n.clear()
        tache(config, vault, faux, "mere", "supprimer")
    assert photo(racine) == avant


def test_routes_apercu_et_refus_agent(config, vault, faux, racine):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        a = c.get("/api/suppression", params={"tache": "mere"}, headers=H).json()
        assert a["sous_taches"] == 2 and a["defaut"] == ALPHA
        assert {"id": "Projets/C2-Beta", "type": "conteneur", "titre": "C2-Beta"} in a["emplacements"]
        assert all(e["id"] != "mere" for e in a["emplacements"])
        p = c.get("/api/suppression", params={"conteneur": SOUS}, headers=H).json()
        assert (p["taches"], p["sous_projets"], p["autres"]) == (2, 0, 1)
        r = c.post("/api/taches/doublon/supprimer", json={}, headers={**H, "X-Orch-Tache": "mere"})
        assert r.status_code == 403 and (racine / "Projets/C2-Beta/taches/doublon.md").exists()
        assert c.post("/api/conteneurs/supprimer", json={"conteneur": SOUS},
                      headers={**H, "X-Orch-Tache": "mere"}).status_code == 403
        assert c.post("/api/conteneurs/supprimer", json={"conteneur": "Casquettes/C1-Pro"},
                      headers=H).status_code == 409
        r = c.post("/api/taches/mere/supprimer", json={"sous_taches": "deplacer", "vers": "Projets/C2-Beta"},
                   headers=H)
        assert r.status_code == 200 and vault.tache("enfant").conteneur == "Projets/C2-Beta"
