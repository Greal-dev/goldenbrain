"""Accueil d'un nouvel arrivant : aucune écriture avant validation, ajout sans écrasement, sources désactivables."""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from orchestrateur import accueil, accueil_ecriture
from orchestrateur.config import ConfigVault
from orchestrateur.vault import Invalide, Vault

MOTIFS = ["Casquettes/*/*/taches/*.md", "Casquettes/*/*/*/taches/*.md", "Projets/*/taches/*.md", "_meta/taches/*.md"]


def instantane(racine: Path) -> dict:
    return {p.relative_to(racine).as_posix(): p.read_bytes() for p in racine.rglob("*") if p.is_file()}


def vieillir(f: Path) -> None:
    vieux = time.time() - 3 * 86400
    os.utime(f, (vieux, vieux))


def claude(home: Path, dossier: Path, session: str, messages: list[str], fin_par="assistant") -> None:
    d = home / ".claude" / "projects" / "x"
    d.mkdir(parents=True, exist_ok=True)
    lignes = [{"type": "user", "cwd": str(dossier), "timestamp": "2026-11-02T10:00:00Z", "sessionId": session,
               "message": {"role": "user", "content": "<system-reminder>bruit</system-reminder>"}, "isMeta": True}]
    for m in messages:
        lignes.append({"type": "user", "cwd": str(dossier), "timestamp": "2026-11-03T10:00:00Z",
                       "message": {"role": "user", "content": m}})
        lignes.append({"type": "assistant", "timestamp": "2026-11-03T10:01:00Z", "message": {"role": "assistant"}})
    if fin_par == "user":
        lignes.pop()
    f = d / f"{session}.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    vieillir(f)


def codex(home: Path, dossier: Path, session: str, messages: list[str]) -> None:
    d = home / ".codex" / "sessions" / "2026" / "11" / "03"
    d.mkdir(parents=True, exist_ok=True)
    lignes = [{"type": "session_meta", "timestamp": "2026-11-03T09:00:00Z",
               "payload": {"id": session, "cwd": str(dossier), "timestamp": "2026-11-03T09:00:00Z"}}]
    for m in messages:
        lignes.append({"type": "event_msg", "timestamp": "2026-11-03T09:05:00Z",
                       "payload": {"type": "user_message", "message": m}})
        lignes.append({"type": "response_item", "payload": {"type": "message", "role": "user",
                                                            "content": [{"type": "input_text", "text": m}]}})
        lignes.append({"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}})
    f = d / f"rollout-{session}.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    vieillir(f)


@pytest.fixture
def monde(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ORCH_ACCUEIL_HOME", str(home))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "temporaire"))
    travaux = tmp_path / "travaux"
    for nom in ("alpha", "beta"):
        (travaux / nom / ".git").mkdir(parents=True)
    (travaux / "alpha" / "README.md").write_text("# Alpha\n\nLe projet alpha, un site.\n", encoding="utf-8")
    claude(home, travaux / "alpha", "sess-alpha-1", ["Refaire la page d'accueil", "Ajoute un pied de page"])
    claude(home, travaux / "alpha" / "src", "sess-alpha-2", ["Refaire la page d'accueil", "Encore"])  # doublon
    claude(home, travaux / "alpha", "sess-alpha-3", ["Une seule question"], fin_par="user")  # sans suite
    codex(home, travaux / "beta", "sess-beta-1", ["Écrire le script d'import", "Ajoute des tests"])
    claude(home, home, "sess-passage", ["Bonjour", "Merci"])
    racine = tmp_path / "vault"
    racine.mkdir()
    vault = Vault(ConfigVault(racine=racine, taches=MOTIFS))
    return vault, home, travaux


TOUT = {"questions": {"actif": True, "metier": "Consultant", "roles": ["Pro", "Famille"]},
        "conversations": {"actif": True}, "dossier": {"actif": False}, "vault": {"actif": False}}


def test_proposition_n_ecrit_rien_et_nomme_sa_source(monde):
    vault, home, travaux = monde
    avant = instantane(vault.racine)
    plan = accueil.proposer(vault, TOUT)
    assert instantane(vault.racine) == avant
    assert {p["nom"] for p in plan["projets"]} == {"alpha", "beta"}
    assert {c["nom"] for c in plan["casquettes"]} == {"Pro", "Famille"}
    assert all(x["source"] for k in ("casquettes", "projets", "taches", "notes") for x in plan[k])
    assert plan["confidentialite"]["modele"] is False


def test_regroupement_et_laisses_de_cote_expliques(monde):
    vault, _, _ = monde
    plan = accueil.proposer(vault, TOUT)
    sessions = sorted(t["session"] for t in plan["taches"])
    assert sessions[-1] == "sess-beta-1" and sessions[0] in ("sess-alpha-1", "sess-alpha-2") and len(sessions) == 2
    pourquoi = {x["session"]: x["pourquoi"] for x in plan["laisses"]}
    assert "doublon" in pourquoi.get("sess-alpha-2", pourquoi.get("sess-alpha-1")) and "sans suite" in pourquoi["sess-alpha-3"]
    assert "passage" in pourquoi["sess-passage"]
    codex_t = next(t for t in plan["taches"] if t["harnais"] == "codex")
    assert "2 message(s)" in codex_t["detail"]  # les deux formes du message codex ne sont pas comptées deux fois


def test_chaque_source_se_desactive(monde):
    vault, _, _ = monde
    seul = accueil.proposer(vault, {**TOUT, "conversations": {"actif": False}})
    assert seul["taches"] == [] and seul["projets"] == [] and seul["lu"] == [accueil.RAISON["questions"]]
    cx = accueil.proposer(vault, {"conversations": {"actif": True, "harnais": ["codex"]}})
    assert [t["harnais"] for t in cx["taches"]] == ["codex"]
    with pytest.raises(Invalide):
        accueil.proposer(vault, {})


def test_validation_cree_la_structure_reprenable_et_les_liens(monde):
    vault, _, travaux = monde
    bilan = accueil_ecriture.appliquer(vault, accueil.proposer(vault, TOUT))
    assert bilan["crees"] == {"casquettes": 2, "projets": 2, "taches": 2, "notes": 5, "dossiers": 5}  # + vault de départ
    t = next(x for x in vault.index()[0].values() if x.fm.get("session") in ("sess-alpha-1", "sess-alpha-2"))
    assert t.fm["harnais"] == "claude" and t.fm["source"] == "accueil" and t.fm["casquette"].startswith("C")
    ctx = (vault.racine / t.conteneur / "contexte.md").read_text(encoding="utf-8")
    assert "depot:" in ctx and str(travaux / "alpha") in ctx
    profil = next(vault.racine.rglob("profil-c*-pro.md")).read_text(encoding="utf-8")
    assert "/notes/alpha|alpha]]" in profil and "/notes/beta|beta]]" in profil  # liens par chemin depuis la racine
    note = next(vault.racine.rglob("notes/alpha.md")).read_text(encoding="utf-8")
    assert "[[Casquettes/" in note and "/notes/profil-c" in note
    assert "Consultant" in profil


def test_relance_ajoute_sans_ecraser(monde):
    vault, home, travaux = monde
    accueil_ecriture.appliquer(vault, accueil.proposer(vault, TOUT))
    ctx = next(vault.racine.rglob("alpha/contexte.md"))
    ctx.write_text(ctx.read_text(encoding="utf-8") + "\nMa note à moi.\n", encoding="utf-8")
    claude(home, travaux / "alpha", "sess-alpha-9", ["Nouveau chantier", "Suite"])
    avant = instantane(vault.racine)
    plan = accueil.proposer(vault, TOUT)  # ce qui existe est reconnu : seule la conversation neuve est proposée
    assert [t["session"] for t in plan["taches"]] == ["sess-alpha-9"]
    assert all(p["existe"] for p in plan["projets"])
    bilan = accueil_ecriture.appliquer(vault, plan)
    assert bilan["crees"]["taches"] == 1 and bilan["crees"]["projets"] == 0
    apres = instantane(vault.racine)
    assert all(apres[k] == v for k, v in avant.items())  # aucun fichier existant n'a changé
    assert "Ma note à moi." in ctx.read_text(encoding="utf-8")
    assert accueil_ecriture.appliquer(vault, plan)["crees"]["taches"] == 0  # rejouer le même plan : rien de plus


def test_plan_corrige_par_le_client_est_revalide(monde):
    vault, _, _ = monde
    plan = accueil.proposer(vault, TOUT)
    plan["taches"][0]["session"] = "x;commande"
    with pytest.raises(Invalide):
        accueil_ecriture.appliquer(vault, plan)
    plan["taches"][0]["session"] = "sess-alpha-1"
    plan["projets"][0]["casquette"] = "inconnue"
    with pytest.raises(Invalide):
        accueil_ecriture.appliquer(vault, plan)
    assert not any(vault.racine.rglob("*.md"))  # un plan refusé n'a rien écrit
    plan["projets"][0]["casquette"] = plan["casquettes"][0]["id"]
    plan["projets"][0]["nom"] = "../../evasion"
    accueil_ecriture.appliquer(vault, plan)
    assert not (vault.racine.parent / "evasion").exists()
    assert all(vault.racine in p.parents for p in vault.racine.rglob("contexte.md"))


def test_dossier_designe_et_vault_en_place(monde):
    vault, _, travaux = monde
    plan = accueil.proposer(vault, {"dossier": {"actif": True, "chemin": str(travaux)}})
    assert {p["nom"] for p in plan["projets"]} == {"alpha", "beta"}
    assert next(p for p in plan["projets"] if p["nom"] == "alpha")["resume"] == "Le projet alpha, un site."
    assert len(plan["operations"]) == 1 and plan["operations"][0]["nom"] == "travaux"
    notes = vault.racine / "Maison" / "idees.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("- [ ] Appeler le plombier\n- [x] fait\n", encoding="utf-8")
    plan = accueil.proposer(vault, {"vault": {"actif": True}})
    assert [t["titre"] for t in plan["taches"]] == ["Appeler le plombier"]
    with pytest.raises(Invalide):
        accueil.proposer(vault, {"vault": {"actif": True, "chemin": str(travaux)}})
    accueil_ecriture.appliquer(vault, plan)
    assert notes.read_text(encoding="utf-8") == "- [ ] Appeler le plombier\n- [x] fait\n"  # en place, sans copie
    ctxs = [c.read_text(encoding="utf-8") for c in vault.racine.rglob("contexte.md")]
    assert any("nom: Maison" in c and "déjà là" in c for c in ctxs)  # le dossier d'origine n'est pas touché


def test_vault_sans_motif_pour_les_casquettes_refuse_avant_d_ecrire(monde):
    vault, _, _ = monde
    vault.cfg.taches = ["Projets/*/taches/*.md"]  # ne couvre pas Casquettes/… : les projets créés n'auraient pas de conteneur
    avant = instantane(vault.racine)
    with pytest.raises(Invalide, match="motif"):
        accueil_ecriture.appliquer(vault, accueil.proposer(vault, TOUT))
    assert instantane(vault.racine) == avant


def test_vault_vide_recoit_un_second_cerveau_de_depart_apres_validation(monde):
    vault, _, _ = monde
    q = {"questions": {"actif": True, "roles": ["Travail", "Famille"], "projets": ["Rénover la cuisine", "  "]}}
    plan = accueil.proposer(vault, q)
    assert plan["squelette"] == {"dossiers": ["Casquettes", "Projets", "Inbox", "Ressources", "Archives"],
                                 "notes": ["Lisez-moi.md"]}
    assert [p["nom"] for p in plan["projets"]] == ["Rénover la cuisine"]
    assert not any(vault.racine.iterdir())  # INV-ACCUEIL-2 : rien avant la validation
    bilan = accueil_ecriture.appliquer(vault, plan)
    assert bilan["crees"]["dossiers"] == 5 and bilan["crees"]["projets"] == 1
    assert all((vault.racine / d).is_dir() for d in plan["squelette"]["dossiers"])
    assert "Rôles → projets → tâches" in (vault.racine / "Lisez-moi.md").read_text(encoding="utf-8")
    ctx = next(vault.racine.rglob("contexte.md")).read_text(encoding="utf-8")
    assert "## Objectif" in ctx and "## Consignes pour l'IA" in ctx
    assert accueil.proposer(vault, q)["squelette"] is None  # rejoué : plus rien à proposer (INV-ACCUEIL-4)


def test_vault_de_depart_decoche_n_ecrit_aucun_dossier(monde):
    vault, _, _ = monde
    plan = accueil.proposer(vault, {"questions": {"actif": True, "roles": ["Travail"]}})
    plan["squelette"] = None
    accueil_ecriture.appliquer(vault, plan)
    assert not (vault.racine / "Inbox").exists() and not (vault.racine / "Lisez-moi.md").exists()


def test_vault_obsidian_existant_repris_tel_quel_sans_vault_de_depart(monde):
    vault, _, _ = monde
    (vault.racine / ".obsidian").mkdir()
    (vault.racine / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    (vault.racine / "Lisez-moi.md").write_text("Mon propre lisez-moi.\n", encoding="utf-8")
    jardin = vault.racine / "Jardin" / "semis.md"
    jardin.parent.mkdir()
    jardin.write_text("Semis de [[tomates]]\n- [ ] Commander les graines\n", encoding="utf-8")
    avant = instantane(vault.racine)
    plan = accueil.proposer(vault, {"vault": {"actif": True}})
    assert plan["squelette"] is None
    plan["squelette"] = {"dossiers": ["Inbox"], "notes": ["Lisez-moi.md"]}  # un client qui insiste n'y change rien
    bilan = accueil_ecriture.appliquer(vault, plan)
    assert bilan["crees"]["dossiers"] == 0 and not (vault.racine / "Inbox").exists()
    apres = instantane(vault.racine)
    assert all(apres[k] == v for k, v in avant.items())  # .obsidian, notes et lisez-moi intacts
    assert [t.titre for t in vault.index()[0].values()] == ["Commander les graines"]
