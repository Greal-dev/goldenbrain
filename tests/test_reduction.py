"""Lot 7 : réduction d'un projet en tâche (archivage tout ou rien, mandat de contraction)."""

import asyncio
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, fiches
from orchestrateur import transformations as T
from orchestrateur.alignement import Aligneur
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, aujourdhui
from conftest import ecrire, tache_md
from test_moteur import executer, finir, moteur

H = {"X-Orchestrateur": "1"}
SOUS = "Projets/C1-Alpha/Sous"
ARCHIVE = f"Archives/Sous-ARCHIVE-{aujourdhui().isoformat()}"


def ctx(cas, parent=None, corps=""):
    return (f"---\ntype: contexte\ncasquette: {cas}\n" + (f"parent: {parent}\n" if parent else "")
            + f"---\n\n{corps}")


@pytest.fixture(autouse=True)
def monde(config, racine):
    config.vault.taches += [f"{b}/{'*/' * n}taches/*.md" for b in ("Projets", "Casquettes")
                            for n in range(2, 4)] + ["Casquettes/*/taches/*.md"]
    ecrire(racine, f"{SOUS}/contexte.md", ctx("C1", corps="# Sous\n\nObjectif : finir.\n"))
    ecrire(racine, f"{SOUS}/taches/s1.md",
           tache_md(extra="session: sess-1\nharnais: faux\n", titre="S un")
           + "\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : a\n- **Situation** : b\n"
             "- **Reste à faire** : c\n- **Prochain pas** : d\n<!-- orchestrateur:fin -->\n")
    ecrire(racine, f"{SOUS}/taches/s2.md", tache_md(statut="fait", titre="S deux"))
    ecrire(racine, f"{SOUS}/notes/n.md", "note\n")
    ecrire(racine, "Projets/C1-Ext/contexte.md", ctx("C1", "C1-Alpha"))
    ecrire(racine, "Projets/C1-Seul/contexte.md", ctx("C1"))
    ecrire(racine, "Casquettes/C1-Pro/contexte.md", ctx("C1"))
    ecrire(racine, "Projets/C3-Z/contexte.md", ctx("C3"))
    ecrire(racine, "Inbox/lien.md", f"Voir [[{SOUS}/taches/s1]] et [[{SOUS}/notes/n|la note]].\n")


def reduire(config, vault, faux, cid, point_git=False, avant=None):
    async def scenario():
        m = moteur(config, vault, faux)
        if avant:
            await avant(m)
        r = await T.reduire(m, Aligneur(vault, []), cid, point_git)
        await finir(m)
        return m, r
    return executer(scenario())


def photo(racine):
    return {p.relative_to(racine).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(racine.rglob("*"))}


@pytest.mark.parametrize("cid,parent", [
    (SOUS, "Projets/C1-Alpha"),                      # parent implicite (dossier)
    ("Projets/C1-Ext", "Projets/C1-Alpha"),          # parent explicite
    ("Projets/C1-Seul", "Casquettes/C1-Pro"),    # conteneur de sa casquette
    ("Projets/C3-Z", "_meta")])                       # arrivée
def test_tache_creee_au_bon_endroit(config, vault, faux, racine, cid, parent):
    m, r = reduire(config, vault, faux, cid)
    t = vault.tache(r["tache"])
    assert t.conteneur == parent and t.titre == cid.rsplit("/", 1)[-1]
    assert r["archive"].startswith("Archives/") and (racine / r["archive"]).is_dir()
    assert not (racine / cid).exists()


def test_archivage_references_et_mandat_de_contraction(config, vault, faux, racine):
    ecrire(racine, f"{ARCHIVE}/deja.md", "pris\n")  # collision : suffixe -2
    m, r = reduire(config, vault, faux, SOUS)
    assert r["archive"] == ARCHIVE + "-2"
    assert (racine / ARCHIVE / "deja.md").is_file()
    assert (racine / r["archive"] / "notes/n.md").read_text("utf-8") == "note\n"
    lien = (racine / "Inbox/lien.md").read_text("utf-8")
    assert f"[[{r['archive']}/taches/s1]]" in lien and f"[[{r['archive']}/notes/n|la note]]" in lien
    corps = fiches.lire(vault.tache(r["tache"]).chemin)
    assert "Objectif : finir." in corps and corps.count("\n# Sous\n") == 1
    assert "- S un (a-faire) — b ; session faux sess-1" in corps and "- S deux (fait)" in corps
    message = faux.lances[0]["message"]
    assert f"« Sous » vient d'être réduit" in message and r["archive"] in message
    assert "### S un (a-faire)" in message and "- Situation : b" in message
    assert "Harnais et session : faux sess-1" in message
    assert "Tâches fermées :\n- S deux (fait)" in message
    assert faux.lances[0]["env"]["ORCH_TACHE"] == r["tache"]
    assert m.mandats.attente == {}  # tour réussi : la contraction est close


def test_mandat_de_contraction_en_attente_si_interrompu(config, vault, faux):
    faux.scenario = [Evenement("session", session="s"), "attendre"]

    async def scenario():
        m = moteur(config, vault, faux)
        r = await T.reduire(m, Aligneur(vault, []), SOUS, False)
        while not faux.lances:
            await asyncio.sleep(0)
        await m.arreter(r["tache"])
        await finir(m)
        return m, r

    m, r = executer(scenario())
    assert m.mandats.attente[r["tache"]]["type"] == "contraction"


def test_refus_409(config, vault, faux, racine):
    ecrire(racine, "Projets/C3-Z/.claude/x.json", "{}")
    ecrire(racine, f"{SOUS}/Plus/contexte.md", ctx("C1"))
    ecrire(racine, f"{SOUS}/Plus/taches/p.md", tache_md(titre="P"))
    avant = photo(racine)
    for cid, motif in [("Projets/Sans", "contexte"), ("Casquettes/C1-Pro", "casquette"),
                       ("_meta", "contexte"), ("Projets/C1-Alpha", "sous-projet"),
                       (SOUS, "sous-projet"), ("Projets/C3-Z", "dossier du code \\(git\\) ou un dossier .claude")]:
        with pytest.raises(Conflit, match=motif):
            reduire(config, vault, faux, cid)
    assert photo(racine) == avant and faux.lances == []


def test_refus_409_tour_en_cours(config, vault, faux, racine):
    faux.scenario = [Evenement("session", session="s"), "attendre"]

    async def lancer(m):
        m.soumettre("s1", "travaille")
        while not faux.lances:
            await asyncio.sleep(0)

    async def scenario():
        m = moteur(config, vault, faux)
        await lancer(m)
        try:
            with pytest.raises(Conflit, match="séance de travail"):
                await T.reduire(m, Aligneur(vault, []), SOUS, False)
        finally:
            await m.arreter("s1")
            await finir(m)

    executer(scenario())
    assert (racine / SOUS).is_dir()


def test_restauration_sur_echec(config, vault, faux, racine, monkeypatch):
    avant = photo(racine)

    def panne(*a, **k):
        raise OSError("disque plein")

    monkeypatch.setattr(vault, "creer", panne)
    with pytest.raises(Conflit, match="archivage annulé, rien n'a changé"):
        reduire(config, vault, faux, SOUS)
    assert photo(racine) == avant and faux.lances == []


def git(racine, *args):
    return subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


@pytest.mark.skipif(not shutil.which("git"), reason="git absent")
def test_point_git_avant_archivage(config, vault, faux, racine):
    git(racine, "init", "-q")
    git(racine, "config", "user.name", "Test")
    git(racine, "config", "user.email", "t@example.org")
    reduire(config, vault, faux, SOUS, point_git=True)
    assert git(racine, "log", "-1", "--format=%s").startswith("GoldenBrain : avant archivage ")
    assert f"{SOUS}/taches/s1.md" in git(racine, "show", "--name-only", "--format=", "HEAD")


def test_route_reduire(config, vault, faux, racine):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        r = c.post("/api/conteneurs/reduire", headers=H,
                   json={"conteneur": "Projets/C3-Z", "point_git": False})
        assert r.status_code == 200 and r.json()["tache"]["conteneur"] == "_meta"
        assert r.json()["archive"].startswith("Archives/C3-Z-ARCHIVE-")
        r = c.post("/api/conteneurs/reduire", headers=H, json={"conteneur": "_meta"})
        assert r.status_code == 409
        assert c.post("/api/conteneurs/reduire", headers=H,
                      json={"conteneur": "Inconnu"}).status_code == 404
