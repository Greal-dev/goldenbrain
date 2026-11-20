"""Modifier un message envoyé : retour arrière, repli par transcription, archive, points git (INV-RETOUR-*)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, points, retour
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import scenario_ok

BASE = "http://127.0.0.1:8399"
git_requis = pytest.mark.skipif(not shutil.which("git"), reason="git absent")


def _git(depot: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    d = tmp_path / "depot"
    d.mkdir()
    _git(d, "init", "-q")
    for n, v in (("a.txt", "v1"), ("c.txt", "c")):
        (d / n).write_text(v, "utf-8")
    _git(d, "add", "-A")
    _git(d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return d


def _sans_transcript(faux):
    """Harnais factice à la Codex : aucun transcript, la conversation se relit aux journaux."""
    def transcript(self, session, limite):
        raise NotImplementedError

    async def lancer(self, message, **kw):
        type(self).reprises.append(getattr(self, "reprendre_a", ""))
        async for ev in faux.lancer(self, message, **kw):
            yield ev
    return type("SansTranscript", (faux,), {"transcript": transcript, "lancer": lancer, "reprises": []})


async def _vider(m):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def _attendre(m):
    """Boucles lancées par une requête : elles tournent dans la boucle du client de test."""
    fin = time.monotonic() + 10
    while any(not b.done() for b in list(m.boucles.values())) and time.monotonic() < fin:
        time.sleep(0.02)


def _trois_tours(config, vault, classe) -> Moteur:
    m = Moteur(config, vault, {"faux": classe})

    async def jouer():
        for texte in ("premier message", "deuxième message", "troisième message"):
            m.soumettre("mere", texte)
            await _vider(m)
    asyncio.run(jouer())
    return m


def _utilisateur(conv):
    return [x for x in conv if x["role"] == "utilisateur"]


def test_repli_par_transcription_archive_la_fin_et_renvoie(config, vault, faux):
    classe = _sans_transcript(faux)
    m = _trois_tours(config, vault, classe)
    with TestClient(api.creer_app(config, m), base_url=BASE, headers={"X-Orchestrateur": "1"}) as c:
        conv = c.get("/api/taches/mere/conversation").json()
        tours = [x["tour"] for x in _utilisateur(conv)]
        assert len(tours) == 3 and len(set(tours)) == 3  # trois tours, même s'ils partagent un fichier
        p = c.get("/api/taches/mere/modifier", params={"tour": tours[1]}).json()
        assert p["retires"] == 2 and p["mecanisme"] == "transcription"
        assert p["vault"] == [str(vault.tache("mere").chemin)] and p["code"] is None
        r = c.post("/api/taches/mere/modifier", json={"tour": tours[1], "texte": "deuxième, corrigé"})
        assert r.status_code == 202 and r.json()["version"] == 1
        _attendre(m)
        envoye = classe.lances[-1]
        assert envoye["session"] is None  # conversation neuve, amorcée par la transcription
        assert "premier message" in envoye["message"] and "troisième message" not in envoye["message"]
        assert envoye["message"].rstrip().endswith("deuxième, corrigé")
        conv = c.get("/api/taches/mere/conversation").json()
        textes = [x["texte"] for x in _utilisateur(conv)]
        assert textes[0] == "premier message" and "transcription" in textes[1]
        assert "<<<" not in textes[1] and textes[1].endswith("deuxième, corrigé")
        assert not any("troisième" in t for t in textes)
        # INV-RETOUR-2 : la fin n'est pas détruite, elle se relit comme version précédente.
        assert [v["n"] for v in c.get("/api/taches/mere/versions").json()] == [1]
        v = c.get("/api/taches/mere/versions/1").json()
        assert [x["texte"] for x in _utilisateur(v["messages"])] == ["deuxième message", "troisième message"]


def test_modifier_le_premier_message_repart_d_une_conversation_neuve(config, vault, faux):
    classe = _sans_transcript(faux)
    m = _trois_tours(config, vault, classe)
    premier = retour.lister(config.donnees, "mere")[0]["id"]
    with TestClient(api.creer_app(config, m), base_url=BASE, headers={"X-Orchestrateur": "1"}) as c:
        r = c.post("/api/taches/mere/modifier", json={"tour": premier, "texte": "tout autre chose"})
        assert r.json()["mecanisme"] == "neuve"
        _attendre(m)
        assert classe.lances[-1]["session"] is None
        assert retour.MARQUE not in classe.lances[-1]["message"]
        assert len(retour.lister(config.donnees, "mere")) == 1


def test_retour_natif_reprend_la_session_au_point(config, vault, faux):
    classe = _sans_transcript(faux)
    classe.point_de_reprise = lambda self, session, texte, date: f"uuid-avant-{texte[:8]}"
    m = _trois_tours(config, vault, classe)
    tour = retour.lister(config.donnees, "mere")[2]["id"]
    with TestClient(api.creer_app(config, m), base_url=BASE, headers={"X-Orchestrateur": "1"}) as c:
        r = c.post("/api/taches/mere/modifier", json={"tour": tour, "texte": "troisième bis"})
        assert r.json()["mecanisme"] == "natif"
        _attendre(m)
    assert classe.lances[-1]["session"] == "s-1" and classe.lances[-1]["message"] == "troisième bis"
    assert classe.reprises[-1] == "uuid-avant-troisièm"  # l'adaptateur reçoit le point de reprise
    assert not m.rembobinages  # consommé par ce seul tour


def test_refus_pendant_un_tour(config, vault, faux):
    classe = _sans_transcript(faux)
    m = _trois_tours(config, vault, classe)
    tour = retour.lister(config.donnees, "mere")[1]["id"]
    classe.scenario = [Evenement("session", session="s-1"), "attendre"]

    async def scenario():
        m.soumettre("mere", "long tour")
        await asyncio.sleep(0.05)
        with pytest.raises(retour.Conflit):
            await retour.modifier(m, "mere", tour, "x", False, [], classe({}))
        await m.arreter("mere")
        await _vider(m)
    asyncio.run(scenario())
    assert len(retour.lister(config.donnees, "mere")) == 4  # rien n'a été retiré


def test_claude_option_de_reprise_au_point():
    from orchestrateur.harnais.claude import HarnaisClaude
    h = HarnaisClaude({"commande": sys.executable})
    h.reprendre_a = "abc"
    argv = h._argv("s-1", False, "", "")
    assert argv[argv.index("--resume-session-at") + 1] == "abc" and "--fork-session" in argv


def test_claude_point_de_reprise_lit_le_parent_du_message(tmp_path):
    from orchestrateur.harnais.claude import HarnaisClaude
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "s-1.jsonl").write_text(
        '{"type":"user","uuid":"u1","parentUuid":null,"message":{"content":"bonjour"}}\n'
        '{"type":"assistant","uuid":"a1","parentUuid":"u1","message":{"content":[{"type":"text","text":"ok"}]}}\n'
        '{"type":"user","uuid":"u2","parentUuid":"a1","message":{"content":"et ensuite"}}\n', "utf-8")
    h = HarnaisClaude({"transcripts": str(tmp_path)})
    assert h.point_de_reprise("s-1", "et ensuite", "") == "a1"
    assert h.point_de_reprise("s-1", "bonjour", "") == ""  # premier message : rien à garder


# --- points de restauration du code (INV-RETOUR-3) ---------------------------------------------

@git_requis
def test_point_plan_et_restauration_tout_ou_rien(depot):
    tete = _git(depot, "rev-parse", "HEAD")
    p = points.creer(depot, "mere")
    assert _git(depot, "rev-parse", p["ref"]).strip() == p["commit"]
    assert _git(depot, "status", "--porcelain") == ""  # rien de touché : ni index, ni arbre
    (depot / "a.txt").write_text("v2", "utf-8")
    (depot / "b.txt").write_text("nouveau", "utf-8")
    (depot / "c.txt").unlink()
    plan = {f["chemin"]: f["etat"] for f in points.plan(depot, p["commit"])}
    assert plan == {"a.txt": "modifie", "b.txt": "supprime", "c.txt": "recree"}
    avant = points.restaurer(depot, "mere", p["commit"])
    assert (depot / "a.txt").read_text("utf-8") == "v1" and (depot / "c.txt").exists()
    assert not (depot / "b.txt").exists()
    assert _git(depot, "show", f"{avant['commit']}:b.txt") == "nouveau"  # réversible
    assert _git(depot, "rev-parse", "HEAD") == tete


@git_requis
def test_restauration_en_echec_laisse_l_etat_d_avant(depot, monkeypatch):
    p = points.creer(depot, "mere")
    (depot / "a.txt").write_text("v2", "utf-8")
    (depot / "b.txt").write_text("nouveau", "utf-8")
    vrai = points._git

    def panne(d, *args, **kw):
        if args[0] == "checkout-index" and not panne.fait:
            panne.fait = True
            (depot / "a.txt").write_text("à moitié", "utf-8")
            raise points.ErreurPoint("panne simulée")
        return vrai(d, *args, **kw)
    panne.fait = False
    monkeypatch.setattr(points, "_git", panne)
    with pytest.raises(points.ErreurPoint, match="restauration annulée"):
        points.restaurer(depot, "mere", p["commit"])
    assert (depot / "a.txt").read_text("utf-8") == "v2" and (depot / "b.txt").exists()


@git_requis
def test_tour_pose_un_point_et_modifier_restaure_le_code(config, vault, faux, depot):
    classe = _sans_transcript(faux)
    classe.dossier = str(depot)
    edition = Evenement("outil", texte="Write", brut={"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"file_path": str(depot / "a.txt")}},
        {"type": "tool_use", "name": "Write", "input": {"file_path": str(config.vault.racine / "x.md")}}]}})
    m = Moteur(config, vault, {"faux": classe})

    async def jouer():
        m.soumettre("mere", "premier message")
        await _vider(m)
        (depot / "a.txt").write_text("écrit par le tour", "utf-8")  # l'agent modifie le dépôt
        classe.scenario = [edition, *scenario_ok()]
        m.soumettre("mere", "deuxième message")
        await _vider(m)
    asyncio.run(jouer())
    tours = retour.lister(config.donnees, "mere")
    assert all(t["point"] and t["point"]["ref"].startswith("refs/goldenbrain/points/mere/") for t in tours)
    with TestClient(api.creer_app(config, m), base_url=BASE, headers={"X-Orchestrateur": "1"}) as c:
        p = c.get("/api/taches/mere/modifier", params={"tour": tours[0]["id"]}).json()
        assert p["code"]["fichiers"] == [{"etat": "modifie", "chemin": "a.txt"}]
        assert str(config.vault.racine / "x.md") in p["vault"]  # listé, jamais annulé
        r = c.post("/api/taches/mere/modifier",
                   json={"tour": tours[0]["id"], "texte": "premier bis", "code": True})
        assert r.status_code == 202 and r.json()["restauration"]["ref"]
        _attendre(m)
    assert (depot / "a.txt").read_text("utf-8") == "v1"


def test_tour_inconnu_refuse(config, vault, faux):
    m = _trois_tours(config, vault, _sans_transcript(faux))
    with TestClient(api.creer_app(config, m), base_url=BASE, headers={"X-Orchestrateur": "1"}) as c:
        assert c.get("/api/taches/mere/modifier", params={"tour": "../../x"}).status_code == 400


def test_annoter_relie_chaque_reponse_au_tour_qui_la_suit():
    tours = [{"id": "t1", "texte": "un"}, {"id": "t2", "texte": "deux"}]
    msgs = retour.annoter([{"role": "utilisateur", "texte": "un"}, {"role": "assistant", "texte": "r1"},
                           {"role": "utilisateur", "texte": "deux"}, {"role": "assistant", "texte": "r2"}], tours)
    assert msgs[1]["suite"] == "t2" and "dernier" not in msgs[1]
    assert msgs[3].get("dernier") and "suite" not in msgs[3]  # dernière réponse : le fil continue
    terminal = retour.annoter([{"role": "assistant", "texte": "r"}, {"role": "utilisateur", "texte": "au terminal"}], [])
    assert "suite" not in terminal[0] and "dernier" not in terminal[0]  # suivie d'un message sans tour


def test_repondre_a_partir_d_une_reponse_retire_la_suite(config, vault, faux):
    classe = _sans_transcript(faux)
    m = _trois_tours(config, vault, classe)
    with TestClient(api.creer_app(config, m), base_url=BASE, headers={"X-Orchestrateur": "1"}) as c:
        conv = c.get("/api/taches/mere/conversation").json()
        reponse = next(x for x in conv if x["role"] == "assistant")  # réponse au premier message
        p = c.get("/api/taches/mere/modifier", params={"tour": reponse["suite"]}).json()
        assert p["retires"] == 2 and p["mecanisme"] == "transcription"
        r = c.post("/api/taches/mere/modifier", json={"tour": reponse["suite"], "texte": "autre piste"})
        assert r.status_code == 202
        _attendre(m)
        textes = [x["texte"] for x in _utilisateur(c.get("/api/taches/mere/conversation").json())]
    assert textes[0] == "premier message" and textes[1].endswith("autre piste") and len(textes) == 2
