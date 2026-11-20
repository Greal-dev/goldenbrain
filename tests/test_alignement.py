"""Lot 5 — alignement physique : dossiers attendus, écarts, plan, application tout ou rien."""

import asyncio
import posixpath
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrateur import alignement as A
from orchestrateur import api, arbre, fiches, geste
from orchestrateur.config import Config, ConfigAlignement, ConfigMoteur, ConfigVault
from orchestrateur.moteur import Moteur
from orchestrateur.references import nouveau_chemin
from orchestrateur.vault import Conflit, NonTrouve, Vault
from conftest import ecrire, tache_md

H = {"X-Orchestrateur": "1"}
MOTIFS = [f"{b}/{'*/' * n}taches/*.md" for b in ("Projets", "Casquettes") for n in range(1, 6)] \
    + ["_meta/taches/*.md"]
MARQUE = re.compile(r"\[\[(\.\.?/[^\]|#]+)[^\]]*\]\]|\]\((\.\.?/[^)#\s]+)")


def ctx(cas: str, parent: str | None = None) -> str:
    return f"---\ntype: contexte\ncasquette: {cas}\n" + (f"parent: {parent}\n" if parent else "") \
        + "---\n"


FICHIERS = {
    "Casquettes/C1-Pro/contexte.md": ctx("C1", "Pilotage"),  # conteneur de casquette
    "Casquettes/C1-Pro/taches/t0.md": tache_md(extra="casquette: C1\n"),
    "Casquettes/C2-Patri/Asso-H/contexte.md": ctx("C2", "Asso-H"),  # sous-aire, se cite
    "Casquettes/C2-Patri/Asso-H/taches/h.md": tache_md(),
    "Projets/C1-ORION/contexte.md": ctx("C1", "Atelier"),  # opération seule
    "Projets/C1-ORION/taches/t1.md": tache_md(extra="casquette: C1\n", titre="ORION un"),
    "Projets/C1-ORION/notes/n.md": "[[../../C1-ORION-V2/v]] [[../taches/t1]] "
                                   "[m](../../../memory.md) [[../../Vieux/C1-Loin/l]]\n",
    "Projets/C1-ORION-V2/contexte.md": ctx("C1"),  # sans rattachement, à sa place
    "Projets/C1-ORION-V2/v.md": "V6 : [[Projets/C1-ORION/notes/n]] et [[../C1-ORION/notes/n#x|al]]"
                                "\r\nProjets/C1-ORION-V2/v.md\r\n",
    "Projets/Op/C1-Sub/contexte.md": ctx("C1", "C1-ORION > Lot"),  # sous un conteneur
    "Projets/Vieux/C1-Loin/contexte.md": ctx("C1", "\"\""),  # `parent: ""`, mal placé
    "Projets/Vieux/C1-Loin/l.md": "\ufeff[[../../C1-ORION/notes/n]]\r\n",
    "Projets/C9-Meta/contexte.md": ctx("META", "Outils > Dev"),  # casquette sans dossier
    "_meta/taches/m.md": tache_md(),
    "_meta/annuaire.md": "- [[Projets/C1-ORION/contexte]]\n- [[Projets/Vieux/C1-Loin/l]]\n",
    "memory.md": "Projets\\C1-ORION\\notes et C:/AILLEURS/Projets/C1-ORION\n",
}


def faire(tmp_path: Path, fichiers=None, externes=()) -> A.Aligneur:
    r = tmp_path / "vault"
    for rel, texte in (fichiers or FICHIERS).items():
        ecrire(r, rel, texte)
    v = Vault(ConfigVault(racine=r, taches=MOTIFS, exclure=["_meta/templates/*"]))
    return A.Aligneur(v, list(externes))


def photo(racine: Path) -> dict:
    return {p.relative_to(racine).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(racine.rglob("*"))}


def ecarts(al) -> dict:
    return {e.conteneur: (e.vers, e.conflit) for e in al.ecarts()}


# --- dossiers attendus ------------------------------------------------------------------
def test_dossier_attendu_pour_chaque_regle(tmp_path):
    al = faire(tmp_path)
    att = al.attendus()
    assert att["Projets/C1-ORION"] == "Casquettes/C1-Pro/Atelier/C1-ORION"
    assert att["Projets/C1-ORION-V2"] == "Projets/C1-ORION-V2"
    assert att["Projets/Op/C1-Sub"] == "Projets/C1-ORION/Lot/C1-Sub"  # dossier ACTUEL de ORION
    assert att["Projets/Vieux/C1-Loin"] == "Projets/C1-Loin"
    assert att["Projets/C9-Meta"] == "Projets/Outils/Dev/C9-Meta"  # casquette sans dossier
    assert att["Casquettes/C1-Pro"] == "Casquettes/C1-Pro"  # casquette : réputé aligné
    assert att["Casquettes/C2-Patri/Asso-H"] == "Casquettes/C2-Patri/Asso-H"  # ailleurs, sans place
    assert att["_meta"] == "_meta"


def test_ecarts_et_conflits(tmp_path):
    al = faire(tmp_path)
    (al.racine / "Projets/Outils/Dev/C9-Meta").mkdir(parents=True)
    e = ecarts(al)
    assert set(e) == {"Projets/C1-ORION", "Projets/Op/C1-Sub", "Projets/Vieux/C1-Loin",
                      "Projets/C9-Meta"}
    assert e["Projets/C1-ORION"][1] is None
    assert "autre dossier à déplacer" in e["Projets/Op/C1-Sub"][1]
    assert "existe déjà" in e["Projets/C9-Meta"][1]
    assert e["Projets/Vieux/C1-Loin"][1] is None


def test_conflits_nom_invalide_casquette_ambigue_et_parent_d_un_ecart(tmp_path):
    al = faire(tmp_path, {
        "Projets/C1-A/contexte.md": ctx("C1", "Mauvais: nom"),
        "Projets/C3-B/contexte.md": ctx("C3", "Op"),
        "Casquettes/C3-Un/x.md": "", "Casquettes/C3-Deux/x.md": "",
        "Projets/Op2/C4-P/contexte.md": ctx("C4", "\"\""),
        "Projets/Op2/C4-P/In/C4-Q/contexte.md": ctx("C4", "Op3"),  # explicite : pas implicite
    })
    e = ecarts(al)
    assert "inutilisable" in e["Projets/C1-A"][1]
    assert "plusieurs dossiers" in e["Projets/C3-B"][1]
    assert "parent d'un autre écart" in e["Projets/Op2/C4-P"][1]
    al.plan(["Projets/Op2/C4-P/In/C4-Q"])  # seul, il passe
    with pytest.raises(Conflit, match="parent d'un autre"):
        al.plan(["Projets/Op2/C4-P", "Projets/Op2/C4-P/In/C4-Q"])


def test_inv_align_3_depot_git_ou_claude_jamais_deplace(tmp_path):
    al = faire(tmp_path)
    ecrire(al.racine, "Projets/Vieux/C1-Loin/sous/.claude/x.json", "{}")
    assert "Projets/Vieux/C1-Loin" in ecarts(al)
    with pytest.raises(Conflit, match="dossier du code \\(git\\) ou un dossier .claude"):
        al.plan(["Projets/Vieux/C1-Loin"])
    ecrire(al.racine, "Projets/C1-ORION/.git/HEAD", "x")
    assert "dossier du code" in ecarts(al)["Projets/C1-ORION"][1]


def test_plan_refuse_inconnu_et_aligne(tmp_path):
    al = faire(tmp_path)
    with pytest.raises(NonTrouve):
        al.plan(["Projets/Rien"])
    with pytest.raises(Conflit, match="déjà aligné"):
        al.plan(["Projets/C1-ORION-V2"])


# --- plan -------------------------------------------------------------------------------
def test_plan_n_ecrit_rien_et_liste_reecritures(tmp_path):
    ext = tmp_path / "ext"
    ecrire(ext, "skills/s/SKILL.md", "lire ~/Documents/x Projets/C1-ORION/contexte.md\n")
    al = faire(tmp_path, externes=[str(ext / "skills"), str(ext / "absent")])
    avant = photo(al.racine)
    p = al.plan(["Projets/C1-ORION", "Projets/Vieux/C1-Loin"])
    assert photo(al.racine) == avant
    assert p["deplacements"] == [
        {"de": "Projets/C1-ORION", "vers": "Casquettes/C1-Pro/Atelier/C1-ORION"},
        {"de": "Projets/Vieux/C1-Loin", "vers": "Projets/C1-Loin"}]
    fichiers = {r["fichier"]: r for r in p["reecritures"]}
    assert set(fichiers) == {"Projets/C1-ORION/notes/n.md", "Projets/C1-ORION-V2/v.md",
                             "Projets/Vieux/C1-Loin/l.md", "_meta/annuaire.md", "memory.md"}
    assert fichiers["_meta/annuaire.md"]["lignes"] == 2
    assert fichiers["_meta/annuaire.md"]["exemples"][0] == {
        "avant": "- [[Projets/C1-ORION/contexte]]",
        "apres": "- [[Casquettes/C1-Pro/Atelier/C1-ORION/contexte]]"}
    assert p["externes"] == [{"fichier": str(ext / "skills/s/SKILL.md"), "occurrences": 1}]
    assert re.fullmatch(r"[0-9a-f]{32}", p["jeton"])


# --- application ------------------------------------------------------------------------
def cibles(racine: Path) -> dict:
    """Pour chaque lien relatif : (nom du fichier, rang du lien) -> cible résolue existante."""
    vus = {}
    for f in racine.rglob("*.md"):
        texte = f.read_bytes().decode("utf-8")
        for k, m in enumerate(MARQUE.finditer(texte)):
            lien = m.group(1) or m.group(2)
            p = posixpath.normpath(posixpath.join(f.parent.as_posix(), lien))
            p = Path(p if Path(p).suffix else p + ".md")
            vus[(f.name, k)] = p.relative_to(racine).as_posix() if p.is_file() else None
    return vus


def test_application_complete_liens_resolvent_vers_les_memes_fichiers(tmp_path):
    al = faire(tmp_path)
    avant = cibles(al.racine)
    assert None not in avant.values()
    p = al.plan(["Projets/C1-ORION", "Projets/Vieux/C1-Loin"])
    r = al.appliquer(p["jeton"], point_git=False)
    assert r == {"deplacements": 2, "fichiers_reecrits": 5, "commit": None}
    rac = al.racine
    assert (rac / "Casquettes/C1-Pro/Atelier/C1-ORION/taches/t1.md").is_file()
    assert not (rac / "Projets/C1-ORION").exists()
    assert not (rac / "Projets/Vieux").exists()  # parent laissé vide : retiré
    assert (rac / "Projets").is_dir()
    deps = [(d["de"], d["vers"]) for d in p["deplacements"]]
    assert cibles(rac) == {k: nouveau_chemin(c, deps) for k, c in avant.items()}
    n = (rac / "Casquettes/C1-Pro/Atelier/C1-ORION/notes/n.md").read_text("utf-8")
    assert n == ("[[../../../../../Projets/C1-ORION-V2/v]] [[../taches/t1]] "
                 "[m](../../../../../memory.md) [[../../../../../Projets/C1-Loin/l]]\n")
    assert (rac / "Projets/C1-Loin/l.md").read_bytes() == \
        "\ufeff[[../../Casquettes/C1-Pro/Atelier/C1-ORION/notes/n]]\r\n".encode()
    assert (rac / "Projets/C1-ORION-V2/v.md").read_bytes() == (
        "V6 : [[Casquettes/C1-Pro/Atelier/C1-ORION/notes/n]] et "
        "[[../../Casquettes/C1-Pro/Atelier/C1-ORION/notes/n#x|al]]\r\n"
        "Projets/C1-ORION-V2/v.md\r\n").encode()
    assert (rac / "memory.md").read_text("utf-8") == \
        "Casquettes\\C1-Pro\\Atelier\\C1-ORION\\notes et C:/AILLEURS/Projets/C1-ORION\n"
    assert "Projets/C1-ORION" not in ecarts(al)
    assert "Casquettes/C1-Pro/Atelier/C1-ORION" in al.vault.index()[1]


def test_aller_retour_contenu_d_origine(tmp_path):
    al = faire(tmp_path, {
        "Projets/C3-X/contexte.md": ctx("C3"),
        "Projets/C3-X/taches/x.md": tache_md(extra="casquette: C3\n"),
        "Projets/C3-X/n.md": "[[../../memory]] [[Projets/C3-X/n]] Projets\\C3-X\n",
        "Projets/C3-Y/y.md": "[[../C3-X/n#a|b]] [l](../C3-X/n.md)\n",
        "memory.md": "[[Projets/C3-X/n]]\n",
    })
    origine = photo(al.racine)
    ctx_x = al.racine / "Projets/C3-X/contexte.md"
    fiches.ecrire_atomique(ctx_x, fiches.modifier_cles(fiches.lire(ctx_x), {"parent": "Op"}))
    al.appliquer(al.plan(["Projets/C3-X"])["jeton"], point_git=False)
    assert (al.racine / "Projets/Op/C3-X/n.md").is_file()
    p = geste.planifier(al, "Projets/Op/C3-X", None)  # geste inverse : sous la casquette
    assert p["deplacements"] == [{"de": "Projets/Op/C3-X", "vers": "Projets/C3-X"}]
    al.appliquer(p["jeton"], point_git=False)
    fin = photo(al.racine)
    assert not (al.racine / "Projets/Op").exists()  # dossier d'opération vide retiré
    assert fin == origine  # octet pour octet, contexte compris (parent posé puis retiré)


def test_casquette_videe_gardee(tmp_path):
    al = faire(tmp_path, {"Casquettes/C3-Aut/Op/C3-Z/contexte.md": ctx("C5", "Op"),
                          "Projets/garde.md": ""})
    al.appliquer(al.plan(["Casquettes/C3-Aut/Op/C3-Z"])["jeton"], point_git=False)
    assert (al.racine / "Projets/Op/C3-Z/contexte.md").is_file()  # C5 : pas de dossier
    assert not (al.racine / "Casquettes/C3-Aut/Op").exists()
    assert (al.racine / "Casquettes/C3-Aut").is_dir()  # jamais un dossier de casquette


def test_jeton_perime_inconnu_ou_vault_change(tmp_path):
    al = faire(tmp_path)
    p = al.plan(["Projets/Vieux/C1-Loin"])
    with pytest.raises(Conflit, match="inconnu ou expiré"):
        al.appliquer("0" * 32, point_git=False)
    ecrire(al.racine, "_meta/annuaire.md", "- [[Projets/Vieux/C1-Loin/l]] modifié\n")
    avant = photo(al.racine)
    with pytest.raises(Conflit, match="le vault a changé"):
        al.appliquer(p["jeton"], point_git=False)
    assert photo(al.racine) == avant
    al.plans[p["jeton"]] = (al.plans[p["jeton"]][0] - A.DUREE_PLAN_S, al.plans[p["jeton"]][1])
    with pytest.raises(Conflit, match="expiré"):
        al.appliquer(p["jeton"], point_git=False)


def test_nouveau_fichier_citant_le_dossier_perime_le_plan(tmp_path):
    al = faire(tmp_path)
    p = al.plan(["Projets/Vieux/C1-Loin"])
    ecrire(al.racine, "Inbox/neuf.md", "Projets/Vieux/C1-Loin\n")
    with pytest.raises(Conflit, match="le vault a changé"):
        al.appliquer(p["jeton"], point_git=False)


# --- point git ---------------------------------------------------------------------------
def git(racine, *args):
    return subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


@pytest.mark.skipif(not shutil.which("git"), reason="git absent")
def test_point_git_commit_cree_puis_alignement(tmp_path):
    al = faire(tmp_path)
    git(al.racine, "init", "-q")
    git(al.racine, "config", "user.name", "Test")
    git(al.racine, "config", "user.email", "t@example.org")
    ecrire(al.racine, "brouillon.md", "non commité\n")
    r = al.appliquer(al.plan(["Projets/Vieux/C1-Loin"])["jeton"], point_git=True)
    assert r["commit"] == git(al.racine, "rev-parse", "HEAD")
    assert git(al.racine, "log", "-1", "--format=%s").startswith(
        "GoldenBrain : avant alignement ")
    assert "brouillon.md" in git(al.racine, "show", "--name-only", "--format=", "HEAD")
    assert "Projets/C1-Loin/l.md" in git(al.racine, "status", "--porcelain", "-uall")


@pytest.mark.skipif(not shutil.which("git"), reason="git absent")
def test_restauration_identique_octet_pour_octet_sous_autocrlf_true(tmp_path):
    # Recette du 15/11, A1 : avec core.autocrlf=true, 373 fichiers rendus différents (fins de ligne).
    al = faire(tmp_path)
    git(al.racine, "init", "-q")
    for cle, val in (("user.name", "Test"), ("user.email", "t@example.org"),
                     ("core.autocrlf", "true"), ("core.safecrlf", "true")):
        git(al.racine, "config", cle, val)  # config d'utilisateur hostile, laissée en place
    for nom, octets in (("lf.md", b"a\nb\n"), ("crlf.md", b"a\r\nb\r\n"),
                        ("mixte.md", b"a\r\nb\nc\r\n"), ("cr_seul.md", b"a\rb\r\n")):
        (al.racine / "Projets/Vieux/C1-Loin" / nom).write_bytes(octets)
    def vault():
        return {k: v for k, v in photo(al.racine).items() if not k.startswith(".git")}
    avant = vault()
    r = al.appliquer(al.plan(["Projets/Vieux/C1-Loin"])["jeton"], point_git=True)
    assert vault() != avant
    git(al.racine, *A.GIT_NEUTRE, "reset", "-q", "--hard", r["commit"])
    git(al.racine, "clean", "-q", "-fd")
    assert vault() == avant
    assert git(al.racine, "config", "core.autocrlf") == "true"


def test_point_git_sans_depot_409_rien_touche(tmp_path, monkeypatch):
    al = faire(tmp_path)
    p = al.plan(["Projets/Vieux/C1-Loin"])
    avant = photo(al.racine)
    monkeypatch.setattr(A, "_git", lambda racine, *a: subprocess.CompletedProcess(a, 128, "",
                                                                                   "pas un dépôt"))
    with pytest.raises(Conflit, match="pas géré par git"):
        al.appliquer(p["jeton"], point_git=True)
    monkeypatch.setattr(A.shutil, "which", lambda nom: None)
    with pytest.raises(Conflit, match="git introuvable"):
        al.appliquer(p["jeton"], point_git=True)
    assert photo(al.racine) == avant


# --- tout ou rien ------------------------------------------------------------------------
def echouer_au(n: int, vraie, exc=OSError("panne simulée")):
    compte = {"n": 0}

    def f(*a, **k):
        compte["n"] += 1
        if compte["n"] == n:
            raise exc
        return vraie(*a, **k)
    return f


def test_echec_au_deuxieme_deplacement_etat_initial(tmp_path, monkeypatch):
    al = faire(tmp_path)
    p = al.plan(["Projets/C1-ORION", "Projets/Vieux/C1-Loin"])
    avant = photo(al.racine)
    monkeypatch.setattr(A.os, "rename", echouer_au(2, A.os.rename))
    with pytest.raises(Conflit, match="rien n'a changé"):
        al.appliquer(p["jeton"], point_git=False)
    assert photo(al.racine) == avant


def test_echec_a_la_deuxieme_reecriture_etat_initial(tmp_path, monkeypatch):
    al = faire(tmp_path)
    p = al.plan(["Projets/C1-ORION", "Projets/Vieux/C1-Loin"])
    avant = photo(al.racine)
    monkeypatch.setattr(A, "ecrire", echouer_au(2, A.ecrire))
    with pytest.raises(Conflit, match="rien n'a changé"):
        al.appliquer(p["jeton"], point_git=False)
    assert photo(al.racine) == avant


def test_fichier_ouvert_dans_obsidian_409_lisible(tmp_path, monkeypatch):
    al = faire(tmp_path)
    p = al.plan(["Projets/Vieux/C1-Loin"])
    avant = photo(al.racine)
    monkeypatch.setattr(A.os, "rename", echouer_au(1, A.os.rename, PermissionError(13, "refus")))
    with pytest.raises(Conflit, match="Obsidian"):
        al.appliquer(p["jeton"], point_git=False)
    assert photo(al.racine) == avant


# --- INV-ALIGN-2 et routes ---------------------------------------------------------------
@pytest.fixture
def cfg(tmp_path):
    faire(tmp_path)
    return Config(port=8399, vault=ConfigVault(racine=tmp_path / "vault", taches=MOTIFS),
                  moteur=ConfigMoteur(simultanes_max=2, harnais_defaut="faux"),
                  harnais={"faux": {}}, consigne="{titre}", donnees=tmp_path / "donnees",
                  alignement=ConfigAlignement(externes=[]))


def test_routes_alignement(cfg, faux):
    app = api.creer_app(cfg, Moteur(cfg, None, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        e = c.get("/api/alignement").json()
        assert {x["conteneur"] for x in e} >= {"Projets/C1-ORION", "Projets/Vieux/C1-Loin"}
        assert set(e[0]) == {"conteneur", "titre", "de", "vers", "conflit"}
        assert c.post("/api/alignement/plan", json={"conteneurs": []}).status_code == 403
        p = c.post("/api/alignement/plan", headers=H, json={"conteneurs": ["Projets/C1-ORION"]})
        assert p.status_code == 200 and set(p.json()) == {
            "deplacements", "reecritures", "fiches", "externes", "avertissements", "jeton"}
        assert c.post("/api/alignement/plan", headers=H,
                      json={"conteneurs": ["Projets/C1-ORION-V2"]}).status_code == 409
        r = c.post("/api/alignement/appliquer", headers=H,
                   json={"jeton": p.json()["jeton"], "point_git": False})
        assert r.status_code == 200
        assert r.json()["deplacements"] == 1 and "noeuds" in r.json()["arbre"]
        assert c.post("/api/alignement/appliquer", headers=H,
                      json={"jeton": p.json()["jeton"], "point_git": False}).status_code == 409


def test_inv_align_2_refus_si_un_tour_touche_le_dossier(cfg, faux):
    faux.scenario = ["attendre"]
    m = Moteur(cfg, None, {"faux": faux})
    app = api.creer_app(cfg, m)
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        jeton = c.post("/api/alignement/plan", headers=H,
                       json={"conteneurs": ["Projets/C1-ORION"]}).json()["jeton"]
        assert c.post("/api/taches/t1/messages", headers=H, json={"texte": "go"}).status_code == 202
        r = c.post("/api/alignement/appliquer", headers=H, json={"jeton": jeton,
                                                                 "point_git": False})
        assert r.status_code == 409 and "séance de travail" in r.json()["detail"]
        assert (cfg.vault.racine / "Projets/C1-ORION").is_dir()
        c.post("/api/taches/t1/arret", headers=H)


def test_inv_align_2_aucun_tour_ne_demarre_pendant_l_application(cfg, faux):
    asyncio.run(_aucun_tour_pendant_l_application(cfg, faux))


async def _aucun_tour_pendant_l_application(cfg, faux):
    m = Moteur(cfg, None, {"faux": faux})
    async with m.exclusif():
        assert m.exclusif_actif
        m.soumettre("t1", "go")
        await asyncio.sleep(0.05)
        assert faux.lances == []
        with pytest.raises(Conflit):
            async with m.exclusif():
                pass
    for _ in range(50):
        await asyncio.sleep(0.01)
        if faux.lances:
            break
    assert len(faux.lances) == 1
    while m.occupe():
        await asyncio.sleep(0.01)


# --- conteneur rangé dans le dossier d'un autre, sans `parent:` (correctif du 13/11) --------
IMBRIQUES = {
    "Projets/C2-H-A/contexte.md": ctx("C2"),
    "Projets/C2-H-A/taches/a.md": tache_md(),
    "Projets/C2-H-A/entree-des-lieux/contexte.md": ctx("C2"),
    "Projets/C2-H-A/entree-des-lieux/taches/ea.md": tache_md(titre="EA"),
    "Projets/C2-H-B/contexte.md": ctx("C2", "Immo"),
    "Projets/C2-H-B/entree-des-lieux/contexte.md": ctx("C2"),
    "Projets/C2-H-B/entree-des-lieux/taches/eb.md": tache_md(titre="EB"),
    "Projets/C2-H-B/Docs/sans-fiche/taches/s.md": tache_md(titre="S"),
    "Casquettes/C1-Pro/contexte.md": ctx("C1"),
    "Casquettes/C1-Pro/ORION/X/contexte.md": ctx("C1"),
    "Casquettes/C1-Pro/Y/contexte.md": ctx("C1"),
}


def test_sous_dossier_conteneur_sans_parent_aligne_sous_son_parent_sans_conflit(tmp_path):
    al = faire(tmp_path, IMBRIQUES)
    v, att = al.vault, al.attendus()
    for cid in ("Projets/C2-H-A/entree-des-lieux", "Projets/C2-H-B/entree-des-lieux",
                "Projets/C2-H-B/Docs/sans-fiche", "Casquettes/C1-Pro/Y"):
        assert att[cid] == cid  # aligné : dossier attendu = dossier actuel
    # INV-ARBRE-2 : sans `parent:`, le dossier d'opération ORION est sa place.
    assert att["Casquettes/C1-Pro/ORION/X"] == "Casquettes/C1-Pro/ORION/X"
    e = ecarts(al)
    assert set(e) == {"Projets/C2-H-B"}
    assert all(c is None for _, c in e.values())  # plus de « même destination »
    noeuds = v.arbre(False)
    assert chemin_de(noeuds, "eb") == ["casquette:C2", "operation:C2/Immo", "Projets/C2-H-B",
                                       "Projets/C2-H-B/entree-des-lieux", "eb"]
    assert chemin_de(noeuds, "s")[-2:] == ["Projets/C2-H-B/Docs/sans-fiche", "s"]
    assert [x["id"] for x in v.detail("ea")["fil"]] == [
        "casquette:C2", "Projets/C2-H-A", "Projets/C2-H-A/entree-des-lieux"]
    assert chemin_de(noeuds, "Projets/C2-H-A")[0] == "casquette:C2"


def test_sous_dossier_conteneur_suit_son_parent_deplace_ou_aligne(tmp_path):
    al = faire(tmp_path, IMBRIQUES)
    ctx_eb = al.racine / "Projets/C2-H-B/entree-des-lieux/contexte.md"
    avant = ctx_eb.read_bytes()
    p = geste.planifier(al, "Projets/C2-H-B", "Projets/C2-H-A")  # INV-ARBRE-2 : vrai déplacement
    assert p["deplacements"] == [{"de": "Projets/C2-H-B", "vers": "Projets/C2-H-A/C2-H-B"}]
    al.appliquer(p["jeton"], point_git=False)
    neuf = "Projets/C2-H-A/C2-H-B/entree-des-lieux"
    assert (al.racine / neuf / "taches/eb.md").is_file()
    assert (al.racine / neuf / "contexte.md").read_bytes() == avant  # il suit sans rien écrire
    assert "parent" not in (al.racine / "Projets/C2-H-A/C2-H-B/contexte.md").read_text("utf-8")
    assert ecarts(al) == {}
    assert [x["id"] for x in al.vault.detail("eb")["fil"]][-2:] == ["Projets/C2-H-A/C2-H-B", neuf]


def test_monter_un_sous_dossier_conteneur_ecrit_le_parent_explicite(tmp_path):
    al = faire(tmp_path, IMBRIQUES)
    v = al.vault
    arbre.monter(v, "Projets/C2-H-B/entree-des-lieux")
    assert "parent: Immo\n" in (v.racine / "Projets/C2-H-B/entree-des-lieux/contexte.md"
                                ).read_text("utf-8")
    assert ecarts(al)["Projets/C2-H-B/entree-des-lieux"] == (
        "Projets/Immo/entree-des-lieux", None)
    arbre.monter(v, "Projets/C2-H-A/entree-des-lieux")  # parent sous la casquette : `parent: ""`
    assert 'parent: ""\n' in (v.racine / "Projets/C2-H-A/entree-des-lieux/contexte.md"
                              ).read_text("utf-8")
    assert chemin_de(v.arbre(False), "ea")[:2] == ["casquette:C2",
                                                   "Projets/C2-H-A/entree-des-lieux"]
    assert ecarts(al)["Projets/C2-H-A/entree-des-lieux"] == ("Projets/entree-des-lieux", None)
    with pytest.raises(Conflit, match="fiche de contexte"):
        arbre.monter(v, "Projets/C2-H-B/Docs/sans-fiche")


def chemin_de(noeuds, ident, pile=()):
    for n in noeuds:
        if n["id"] == ident:
            return [*pile, ident]
        if x := chemin_de(n["enfants"], ident, (*pile, n["id"])):
            return x
    return None


# --- performances du plan et des écarts (correctif du 13/11) --------------------------------
def test_plan_lent_ne_decode_que_les_fichiers_citant_un_nom_deplace(tmp_path, monkeypatch):
    fichiers = dict(FICHIERS)
    fichiers.update({f"Ressources/r{i}.md": f"# R{i}\nrien à voir, Projets/Autre\n"
                     for i in range(50)})
    fichiers["Ressources/espace.md"] = "[x](Projets/Vieux/C1%20Loin%20Bis/l.md)\n"
    fichiers["Projets/Vieux/C1 Loin Bis/contexte.md"] = ctx("C1", "\"\"")
    fichiers["Ressources/maj.md"] = "PROJETS/VIEUX/C1-LOIN en capitales\n"
    al = faire(tmp_path, fichiers)
    analyses = []
    vrai = A.references.reecrire

    def espion(texte, rel, *a, **k):
        analyses.append(rel)
        return vrai(texte, rel, *a, **k)

    monkeypatch.setattr(A.references, "reecrire", espion)
    p = al.plan(["Projets/Vieux/C1-Loin", "Projets/Vieux/C1 Loin Bis"])
    assert not [r for r in analyses if r.startswith("Ressources/r")]  # ni décodés ni analysés
    assert "Ressources/maj.md" in analyses  # pré-filtre sans casse : l'avertissement demeure
    assert any("casse" in x for x in p["avertissements"])
    reecrits = {r["fichier"]: r for r in p["reecritures"]}
    assert reecrits["Ressources/espace.md"]["exemples"][0]["apres"] == \
        "[x](Projets/C1%20Loin%20Bis/l.md)"  # nom encodé `%20` : trouvé par le pré-filtre
    assert set(reecrits) >= {"Projets/Vieux/C1-Loin/l.md", "_meta/annuaire.md"}


def test_ecarts_lents_ne_cherchent_pas_git_a_chaque_appel(tmp_path, monkeypatch):
    al = faire(tmp_path)
    premiers = ecarts(al)
    vus = []
    vrai_exists, vrai_is_dir = Path.exists, Path.is_dir
    monkeypatch.setattr(Path, "exists", lambda p: vus.append(p.name) or vrai_exists(p))
    monkeypatch.setattr(Path, "is_dir", lambda p: vus.append(p.name) or vrai_is_dir(p))
    assert ecarts(al) == premiers
    assert ".git" not in vus and ".claude" not in vus  # mémorisé par (mtime, taille)
    ecrire(al.racine, "Projets/Vieux/C1-Loin/.git/HEAD", "x")
    assert "dossier du code" in ecarts(al)["Projets/Vieux/C1-Loin"][1]


def test_route_alignement_hors_de_la_boucle(cfg, faux, monkeypatch):
    app = api.creer_app(cfg, Moteur(cfg, None, {"faux": faux}))
    fils = []
    vrai = app.state.aligneur.ecarts
    monkeypatch.setattr(app.state.aligneur, "ecarts",
                        lambda: fils.append(threading.current_thread()) or vrai())
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        assert c.get("/api/alignement").status_code == 200
    assert fils and fils[0] is not threading.main_thread()


def test_commande_apres_lancee_dans_le_vault_une_fois_l_alignement_applique(cfg, faux):
    """Épreuve du réel 14/11 : `alignement.apres` n'avait aucun test ; elle doit tourner dans la
    racine du vault, après (et seulement après) une application réussie."""
    cfg.alignement.apres = f'"{sys.executable}" -c "open(\'marqueur.txt\', \'w\').write(\'ok\')"'
    app = api.creer_app(cfg, Moteur(cfg, None, {"faux": faux}))
    marqueur = cfg.vault.racine / "marqueur.txt"
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        p = c.post("/api/alignement/plan", json={"conteneurs": ["Projets/Vieux/C1-Loin"]},
                   headers=H).json()
        assert not marqueur.exists()  # un plan n'écrit rien et ne lance rien
        assert c.post("/api/alignement/appliquer", json={"jeton": "0" * 32, "point_git": False},
                      headers=H).status_code == 409
        assert not marqueur.exists()  # un refus ne lance rien
        assert c.post("/api/alignement/appliquer", json={"jeton": p["jeton"], "point_git": False},
                      headers=H).status_code == 200
    for _ in range(100):  # tâche de fond, sans attente côté serveur
        if marqueur.exists():
            break
        time.sleep(0.1)
    assert marqueur.read_text(encoding="utf-8") == "ok"
