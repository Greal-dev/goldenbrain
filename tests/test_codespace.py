"""Codespace : déclaration, état, gestes, exécution distante d'un harnais (faux `gh` en Python,
jamais le vrai ; jamais de vrai harnais), INV-CODESPACE-1 et INV-CODESPACE-2."""

import asyncio
import json
import shlex
import sys
import time

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, codespace
from orchestrateur.harnais import distant
from orchestrateur.harnais.claude import HarnaisClaude
from orchestrateur.harnais.codex import HarnaisCodex
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from conftest import ecrire

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}

# Faux `gh` : liste lue dans liste.json, gestes et connexions consignés dans journal.jsonl ;
# `ssh` rejoue un flux claude ou codex d'après la commande distante (citée par shlex).
FAUX_GH = r'''
import json, os, re, shlex, sys
from pathlib import Path
d = Path(os.environ["FAUX_GH"])
argv = sys.argv[1:]
def noter(o):
    with open(d / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(o) + "\n")
def emettre(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
if (d / "panne").exists():
    sys.stderr.write("gh: not logged in"); sys.exit(1)
if argv[:2] == ["codespace", "list"]:
    sys.stdout.write((d / "liste.json").read_text(encoding="utf-8")); sys.exit(0)
if argv[:2] == ["codespace", "ssh"]:
    script = shlex.split(argv[-1])[2]
    entree = sys.stdin.buffer.read().decode("utf-8")
    if (d / "absent").exists():
        sys.stderr.write(shlex.split(re.search(r"echo (.*?) >&2", script).group(1))[0])
        sys.exit(127)
    distant = shlex.split(script.split("exec env ", 1)[1])
    env = [x for x in distant if re.fullmatch(r"[A-Z_]+=.*", x)]
    cmd = [x for x in distant if x not in env]
    noter({"geste": "ssh", "gh": argv[:5], "env": env, "cmd": cmd, "stdin": entree,
           "cd": script.split("cd ", 1)[1].split(" ", 1)[0]})
    if cmd[0] == "claude":
        emettre({"type": "system", "subtype": "init", "session_id": "sess-cs"})
        emettre({"type": "result", "subtype": "success", "is_error": False,
                 "session_id": "sess-cs", "result": "fait au codespace"})
    else:
        emettre({"type": "thread.started", "thread_id": "th-cs"})
        emettre({"type": "item.completed", "item": {"id": "1", "type": "agent_message",
                 "text": "fait au codespace"}})
        emettre({"type": "turn.completed", "usage": {}})
    sys.exit(0)
noter({"geste": argv[1], "argv": argv})
'''

LISTE = [{"name": "autre-cs", "state": "Shutdown", "repository": "proprio/autre", "displayName": "a"},
         {"name": "cs-depot-1", "state": "Available", "repository": "proprio/depot",
          "displayName": "b"},
         {"name": "cs-depot-2", "state": "Available", "repository": "proprio/depot",
          "displayName": "c"}]


@pytest.fixture
def gh(tmp_path, monkeypatch):
    d = tmp_path / "gh"
    d.mkdir()
    (d / "liste.json").write_text(json.dumps(LISTE), encoding="utf-8")
    script = tmp_path / "faux_gh.py"
    script.write_text(FAUX_GH, encoding="utf-8")
    monkeypatch.setenv("FAUX_GH", str(d))
    monkeypatch.setattr(distant, "commande_gh", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(distant, "_cache", None)
    return d


def journal(d, attendu=1):
    for _ in range(500):  # les gestes « ouvrir » sont détachés
        f = d / "journal.jsonl"
        if f.exists() and len(lignes := f.read_text(encoding="utf-8").splitlines()) >= attendu:
            return [json.loads(x) for x in lignes]
        time.sleep(0.01)
    raise AssertionError("faux gh jamais appelé")


@pytest.fixture
def rattache(racine):
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\ncodespace: proprio/depot\n---\n")
    return racine


# --- INV-CODESPACE-1 : validation et citation -----------------------------------------------
@pytest.mark.parametrize("decl", ["cs-depot-1", "proprio/depot", "proprio/orion-v2"])
def test_declaration_valide_nom_ou_depot(decl):
    assert distant.declaration_valide(decl) == decl


@pytest.mark.parametrize("decl", ["x; rm -rf ~", "-c evil", "a/b/c", "$(id)", ""])
def test_declaration_douteuse_refusee(decl):
    with pytest.raises(distant.ErreurCodespace):
        distant.declaration_valide(decl)


def test_commande_distante_citee_argument_par_argument():
    consigne = "Sois bref ; rm -rf ~ \"$HOME\" `id` 'quote' « été »\nligne 2"
    argv = ["claude", "-p", "--append-system-prompt", consigne, "--resume", "s-1"]
    cmd = distant.script_distant(argv, {"ORCH_TACHE": "t 1", "ORCH_URL": "http://x"},
                                 "/workspaces/depot", "claude", "cs")
    bash, lc, script = shlex.split(cmd)
    assert (bash, lc) == ("bash", "-lc")
    reste = shlex.split(script.split("exec env ", 1)[1])
    assert reste == ["ORCH_TACHE=t 1", *argv]  # ORCH_URL (le poste) n'est pas transmis


# --- rattachement et état ------------------------------------------------------------------
def test_etat_premier_codespace_du_depot_declare(gh, rattache, vault):
    vue = asyncio.run(codespace.etat(vault, vault.tache("mere")))
    assert (vue["declaration"], vue["nom"], vue["etat"], vue["ou"]) == (
        "proprio/depot", "cs-depot-1", "Available", "poste")


def test_etat_sans_declaration_n_appelle_pas_gh(gh, vault):
    assert asyncio.run(codespace.etat(vault, vault.tache("mere")))["declaration"] == ""
    assert not (gh / "journal.jsonl").exists()


def test_etat_gh_en_panne_rendu_sans_lever(gh, rattache, vault):
    (gh / "panne").touch()
    vue = asyncio.run(codespace.etat(vault, vault.tache("mere")))
    assert vue["nom"] == "" and "not logged in" in vue["erreur"]


# --- INV-CODESPACE-2 : lieu d'exécution ----------------------------------------------------
def test_conf_tour_poste_inchangee_codespace_distante(rattache, vault):
    assert codespace.conf_tour({"a": 1}, "claude", vault, vault.tache("mere")) == {"a": 1}
    vault.modifier("mere", {"ou": "codespace"})
    conf = codespace.conf_tour({"a": 1}, "claude", vault, vault.tache("mere"))
    assert conf == {"a": 1, "distant": {"codespace": "proprio/depot", "harnais": "claude"}}


def test_conf_tour_sans_declaration_refuse(racine, vault):
    vault.modifier("mere", {"ou": "codespace"})
    with pytest.raises(Invalide, match="aucun codespace"):
        codespace.conf_tour({}, "claude", vault, vault.tache("mere"))


def test_conf_tour_harnais_non_pris_en_charge_refuse(rattache, vault):
    vault.modifier("mere", {"ou": "codespace"})
    with pytest.raises(Invalide, match="opencode"):
        codespace.conf_tour({}, "opencode", vault, vault.tache("mere"))


# --- exécution distante ------------------------------------------------------------------
async def collecter(h, **kw):
    return [ev async for ev in h.lancer("bonjour « été »", env={"ORCH_TACHE": "t",
                                        "ORCH_URL": "http://127.0.0.1:1"}, **kw)]


def test_claude_au_codespace_prompt_par_stdin_et_reprise(gh, tmp_path):
    h = HarnaisClaude({"dossier": str(tmp_path), "distant": {"codespace": "proprio/depot",
                                                            "harnais": "claude"}})
    evs = asyncio.run(collecter(h, session="sess-0", deriver=False, consigne="sois bref"))
    assert [e.type for e in evs] == ["session", "fin"] and evs[1].texte == "fait au codespace"
    ssh = journal(gh)[0]
    assert ssh["gh"] == ["codespace", "ssh", "-c", "cs-depot-1", "--"]
    assert ssh["stdin"] == "bonjour « été »" and ssh["env"] == ["ORCH_TACHE=t"]
    assert ssh["cmd"][0] == "claude" and ssh["cmd"][ssh["cmd"].index("--resume") + 1] == "sess-0"
    assert ssh["cd"] == "/workspaces/depot"
    with pytest.raises(NotImplementedError):  # transcript resté au codespace : journaux du poste
        h.transcript("sess-0", 10)
    assert h.commande_terminal("sess-0") == "gh codespace ssh -R proprio/depot -- -t 'claude --resume sess-0'"


def test_codex_au_codespace(gh, tmp_path):
    h = HarnaisCodex({"dossier": str(tmp_path), "distant": {"codespace": "cs-depot-2",
                                                           "harnais": "codex"}})
    evs = asyncio.run(collecter(h, session=None, deriver=False, consigne=""))
    assert [e.type for e in evs] == ["session", "texte", "fin"]
    ssh = journal(gh)[0]
    assert ssh["gh"][3] == "cs-depot-2" and ssh["cmd"][:2] == ["codex", "exec"]
    assert ssh["cmd"][-1] == "-"


def test_harnais_absent_du_codespace_erreur_avec_commande_d_installation(gh, tmp_path):
    (gh / "absent").touch()
    h = HarnaisClaude({"dossier": str(tmp_path), "distant": {"codespace": "proprio/depot",
                                                            "harnais": "claude"}})
    evs = asyncio.run(collecter(h, session=None, deriver=False, consigne=""))
    assert [e.type for e in evs] == ["erreur"]
    assert "npm install -g @anthropic-ai/claude-code" in evs[0].texte
    assert "cs-depot-1" in evs[0].texte


def test_codespace_introuvable_echoue_sans_rien_lancer(gh, tmp_path):
    h = HarnaisClaude({"dossier": str(tmp_path), "distant": {"codespace": "proprio/inconnu",
                                                            "harnais": "claude"}})
    with pytest.raises(distant.ErreurCodespace, match="aucun codespace"):
        asyncio.run(collecter(h, session=None, deriver=False, consigne=""))


def test_moteur_lance_la_tache_au_codespace_et_ecrit_la_session(gh, rattache, config, vault):
    config.harnais["claude"] = {"dossier": str(config.donnees)}
    vault.modifier("mere", {"ou": "codespace", "harnais": "claude"})
    m = Moteur(config, vault, {"claude": HarnaisClaude})

    async def scenario():
        m.soumettre("mere", "go")
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)
    asyncio.run(scenario())
    assert vault.tache("mere").fm["session"] == "sess-cs"
    assert journal(gh)[0]["gh"][3] == "cs-depot-1"


def test_moteur_sans_declaration_echoue_sans_repli_sur_le_poste(gh, config, vault, faux):
    vault.modifier("mere", {"ou": "codespace"})
    m = Moteur(config, vault, {"faux": faux})

    async def scenario():
        m.soumettre("mere", "go")
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)
    asyncio.run(scenario())
    assert faux.lances == [] and "aucun codespace" in vault.tache("mere").fm["echec_tour"]


# --- routes ---------------------------------------------------------------------------------
def test_routes_etat_lieu_et_gestes(gh, rattache, config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})),
                    base_url=BASE) as c:
        assert c.get("/api/taches/mere/codespace").json()["nom"] == "cs-depot-1"
        assert c.post("/api/taches/mere/ou", headers=H, json={"ou": "codespace"}
                      ).json()["frontmatter"]["ou"] == "codespace"
        assert c.post("/api/taches/mere/ou", headers=H, json={"ou": "lune"}).status_code == 400
        assert "ou" not in c.post("/api/taches/mere/ou", headers=H, json={"ou": "poste"}
                                  ).json()["frontmatter"]
        assert c.post("/api/taches/mere/codespace/arreter", headers=H).status_code == 200
        assert c.post("/api/taches/mere/codespace/web", headers=H).status_code == 200
        assert c.post("/api/taches/mere/codespace/supprimer", headers=H).status_code == 400
        assert c.post("/api/taches/doublon/codespace/code", headers=H).status_code == 400
    gestes = journal(gh, 2)
    assert {"geste": "stop", "argv": ["codespace", "stop", "-c", "cs-depot-1"]} in gestes
    assert {"geste": "code", "argv": ["codespace", "code", "-c", "cs-depot-1", "--web"]} in gestes


def test_harnais_non_connecte_dit_comment_le_connecter():
    d = {"codespace": "proprio/depot"}
    assert "gh codespace ssh -R proprio/depot" in distant.indice("Not logged in · Please run /login", d)
    assert distant.indice("Not logged in", None) == "Not logged in"  # au poste : inchangé
    assert distant.indice("quota", d) == "quota"


def test_depot_puis_codespace_le_codespace_l_emporte(gh, rattache, config, vault, tmp_path):
    from orchestrateur import depot
    ecrire(rattache, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\ncodespace: proprio/depot\n"
           f"depot: {tmp_path}\n---\n")
    vault.modifier("mere", {"ou": "codespace"})
    conf = codespace.conf_tour(depot.conf_harnais(vault, {"dossier": "x"}, "mere"), "claude",
                               vault, vault.tache("mere"))
    assert conf["dossier"] == str(tmp_path)  # dossier de lancement de gh, sur le poste
    assert conf["distant"]["codespace"] == "proprio/depot"  # le tour, lui, s'exécute au codespace


def test_interface_native_refusee_pour_une_tache_au_codespace(rattache, config, vault, faux):
    from orchestrateur.vault import Conflit
    vault.modifier("mere", {"ou": "codespace"})
    m = Moteur(config, vault, {"faux": faux})
    with pytest.raises(Conflit, match="codespace"):
        m.natif.ouvrir("mere")
