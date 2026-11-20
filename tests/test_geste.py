"""INV-ARBRE-2 — le dossier fait foi : lecture de l'arbre par les dossiers, geste = vrai déplacement."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrateur import alignement as A
from orchestrateur import api, arbre, geste
from orchestrateur.config import Config, ConfigAlignement, ConfigMoteur, ConfigVault
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Vault
from conftest import ecrire, tache_md

H = {"X-Orchestrateur": "1"}
MOTIFS = [f"{b}/{'*/' * n}taches/*.md" for b in ("Projets", "Casquettes") for n in range(1, 6)] \
    + ["_meta/taches/*.md"]


def ctx(cas: str, parent: str | None = None) -> str:
    return f"---\ntype: contexte\ncasquette: {cas}\n" + (f"parent: {parent}\n" if parent else "") \
        + "---\n"


VAULT = {
    "Casquettes/C1-Pro/x.md": "",
    "Casquettes/C1-Pro/Atelier/note-op.md": "Note de l'opération\n",
    "Casquettes/C1-Pro/Atelier/C1-ORION/contexte.md": ctx("C1"),
    "Casquettes/C1-Pro/Atelier/C1-ORION/taches/ti.md": tache_md(extra="casquette: C1\n",
                                                                        titre="Orion"),
    "Casquettes/C2-Patri/x.md": "",
    "Projets/C2-Autre/contexte.md": ctx("C2"),
    "Projets/C2-Autre/taches/au.md": tache_md(extra="casquette: C2\n"),
    "Projets/C1-Petit/contexte.md": ctx("C1"),
    "Projets/C1-Petit/taches/pe.md": tache_md(extra="casquette: C1\n", titre="Petit"),
    "Projets/C1-Petit/notes/n.md": "Voir [[../../C1-Grand/g]] et le mot pélican\n",
    "Projets/C1-Grand/contexte.md": ctx("C1"),
    "Projets/C1-Grand/taches/gr.md": tache_md(extra="casquette: C1\n", titre="Grand"),
    "Projets/C1-Grand/g.md": "Retour : [[Projets/C1-Petit/notes/n]]\n",
    "Projets/C1-Repli/contexte.md": ctx("C1", "Ailleurs"),  # parent: contredit par le dossier
    "Projets/C1-Repli/taches/re.md": tache_md(extra="casquette: C1\n", titre="Repli"),
    "_meta/annuaire.md": "- [[Projets/C1-Petit/notes/n]]\n",
}


def faire(tmp_path: Path, fichiers=None) -> A.Aligneur:
    r = tmp_path / "vault"
    for rel, texte in (fichiers or VAULT).items():
        ecrire(r, rel, texte)
    return A.Aligneur(Vault(ConfigVault(racine=r, taches=MOTIFS)), [])


def fil(al, tache: str) -> list[str]:
    return [x["id"] for x in al.vault.detail(tache)["fil"]]


def photo(racine: Path) -> dict:
    return {p.relative_to(racine).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(racine.rglob("*")) if ".git" not in p.parts}


# --- lecture ------------------------------------------------------------------------------
def test_operation_lue_dans_le_dossier_et_parent_en_repli_signale(tmp_path):
    al = faire(tmp_path)
    assert fil(al, "ti") == ["casquette:C1", "operation:C1/Atelier",
                             "Casquettes/C1-Pro/Atelier/C1-ORION"]
    assert fil(al, "re")[:2] == ["casquette:C1", "operation:C1/Ailleurs"]  # repli lu
    s = arbre.structure(al.vault)
    assert s.logiques == {"Projets/C1-Repli"}
    assert set(al.attendus().items()) - {(k, k) for k in al.attendus()} == {
        ("Projets/C1-Repli", "Casquettes/C1-Pro/Ailleurs/C1-Repli")}
    noeuds = {n["id"]: n for n in arbre.rendre(al.vault, True, lambda k: None)[0]["enfants"]}
    assert noeuds["Projets/C1-Petit"]["logique"] is False


# --- gestes -------------------------------------------------------------------------------
def test_projet_sous_projet_deplace_le_dossier_et_les_references(tmp_path):
    al = faire(tmp_path)
    p = geste.planifier(al, "Projets/C1-Petit", "Projets/C1-Grand")
    assert p["deplacements"] == [{"de": "Projets/C1-Petit", "vers": "Projets/C1-Grand/C1-Petit"}]
    assert (al.racine / "Projets/C1-Petit").is_dir()  # plan à blanc : rien n'a bougé
    r = al.appliquer(p["jeton"], point_git=False)
    assert r["deplacements"] == 1 and not (al.racine / "Projets/C1-Petit").exists()
    assert fil(al, "pe") == ["casquette:C1", "Projets/C1-Grand", "Projets/C1-Grand/C1-Petit"]
    assert (al.racine / "Projets/C1-Grand/g.md").read_text("utf-8") == \
        "Retour : [[Projets/C1-Grand/C1-Petit/notes/n]]\n"
    assert (al.racine / "Projets/C1-Grand/C1-Petit/notes/n.md").read_text("utf-8") == \
        "Voir [[../../g]] et le mot pélican\n"
    assert al.ecarts() == [e for e in al.ecarts() if e.conteneur == "Projets/C1-Repli"]


def test_operation_deplacee_avec_son_dossier_entier(tmp_path):
    al = faire(tmp_path)
    al.appliquer(geste.planifier(al, "operation:C1/Atelier", "Projets/C1-Grand")["jeton"],
                 point_git=False)
    assert (al.racine / "Projets/C1-Grand/Atelier/note-op.md").is_file()
    assert not (al.racine / "Casquettes/C1-Pro/Atelier").exists()
    assert fil(al, "ti") == ["casquette:C1", "Projets/C1-Grand",
                             "operation:C1/C1-Grand > Atelier",
                             "Projets/C1-Grand/Atelier/C1-ORION"]
    # Monter : l'opération redevient frère de C1-Grand, dans le dossier de la casquette.
    al.appliquer(geste.planifier(al, "operation:C1/C1-Grand > Atelier", None)["jeton"],
                 point_git=False)
    assert (al.racine / "Casquettes/C1-Pro/Atelier/note-op.md").is_file()
    assert fil(al, "ti")[1] == "operation:C1/Atelier"


def test_changement_de_casquette_retire_parent_et_suit_sur_les_taches(tmp_path):
    al = faire(tmp_path)
    p = geste.planifier(al, "Projets/C1-Repli", "casquette:C2")
    assert p["deplacements"] == []  # déjà sous `Projets` : seul le repli tombe
    assert {f["fichier"]: f["cles"] for f in p["fiches"]} == {
        "Projets/C1-Repli/contexte.md": {"parent": None, "casquette": "C2"},
        "Projets/C1-Repli/taches/re.md": {"casquette": "C2"}}
    al.appliquer(p["jeton"], point_git=False)
    assert (al.racine / "Projets/C1-Repli/contexte.md").read_text("utf-8") == \
        "---\ntype: contexte\ncasquette: C2\n---\n"
    assert fil(al, "re") == ["casquette:C2", "Projets/C1-Repli"]
    assert al.ecarts() == []  # le seul écart a disparu : plus de pastille


def test_depot_git_rattachement_logique_signale(tmp_path):
    al = faire(tmp_path)
    (al.racine / "Projets/C1-Petit/.git").mkdir()
    p = geste.planifier(al, "Projets/C1-Petit", "Projets/C1-Grand")
    assert p["deplacements"] == [] and "dossier du code" in p["avertissements"][0]
    al.appliquer(p["jeton"], point_git=False)
    assert (al.racine / "Projets/C1-Petit/.git").is_dir()  # INV-ALIGN-3
    assert "parent: C1-Grand\n" in (al.racine / "Projets/C1-Petit/contexte.md").read_text("utf-8")
    assert fil(al, "pe") == ["casquette:C1", "Projets/C1-Grand", "Projets/C1-Petit"]
    assert "Projets/C1-Petit" in arbre.structure(al.vault).logiques


def test_refus_explicites(tmp_path):
    al = faire(tmp_path, {**VAULT, "Projets/C1-Grand/C1-Petit/x.md": "",
                          "Projets/C1-Petit/Sous/contexte.md": ctx("C1", "Loin")})
    with pytest.raises(Conflit, match="existe déjà"):
        geste.planifier(al, "Projets/C1-Petit", "Projets/C1-Grand")
    with pytest.raises(Conflit, match="pas encore rangé"):  # descendant non aligné
        geste.planifier(al, "operation:C1/Loin", "Projets/C1-Grand")
    with pytest.raises(Conflit, match="déjà sous"):
        geste.planifier(al, "Projets/C1-Grand", "casquette:C1")
    with pytest.raises(Conflit, match="sous lui-même"):
        geste.planifier(al, "Projets/C1-Grand", "Projets/C1-Grand")
    with pytest.raises(Conflit, match="tâche"):
        geste.planifier(al, "pe", "Projets/C1-Grand")
    with pytest.raises(Conflit, match="plan"):  # INV-ARBRE-2 : plus de geste logique par l'API
        arbre.deplacer(al.vault, "Projets/C1-Petit", "Projets/C1-Grand", taches_seules=True)


def test_echec_en_fin_de_geste_retour_a_l_etat_initial(tmp_path, monkeypatch):
    al = faire(tmp_path)
    avant = photo(al.racine)
    p = geste.planifier(al, "Projets/C1-Repli", "Projets/C1-Grand")

    def panne(*a, **k):
        raise OSError("panne simulée")
    monkeypatch.setattr(A.fiches, "ecrire_atomique", panne)
    with pytest.raises(Conflit, match="annulé, rien n'a changé"):
        al.appliquer(p["jeton"], point_git=False)
    assert photo(al.racine) == avant


@pytest.mark.skipif(not shutil.which("git"), reason="git absent")
def test_point_de_restauration_git_puis_retour_arriere(tmp_path):
    al = faire(tmp_path)

    def git(*args):
        return subprocess.run(["git", *args], cwd=al.racine, capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout.strip()
    git("init", "-q")
    git("config", "core.autocrlf", "false")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "0")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    avant = photo(al.racine)
    r = al.appliquer(geste.planifier(al, "Projets/C1-Petit", "Projets/C1-Grand")["jeton"],
                     point_git=True)
    assert "avant déplacement" in git("log", "-1", "--format=%s", r["commit"])
    git("reset", "-q", "--hard", r["commit"])
    git("clean", "-q", "-fd")
    assert photo(al.racine) == avant


# --- API : plan, application, arbre et recherche justes ------------------------------------
def test_routes_plan_puis_appliquer_et_recherche(tmp_path, faux):
    faire(tmp_path)
    cfg = Config(port=8399, vault=ConfigVault(racine=tmp_path / "vault", taches=MOTIFS),
                 moteur=ConfigMoteur(simultanes_max=2, harnais_defaut="faux"),
                 harnais={"faux": {}}, consigne="{titre}", donnees=tmp_path / "donnees",
                 alignement=ConfigAlignement(externes=[]))
    app = api.creer_app(cfg, Moteur(cfg, None, {"faux": faux}))
    with TestClient(app, base_url="http://127.0.0.1:8399") as c:
        assert c.get("/api/vault/recherche?q=pélican").json()[0]["chemin"] == \
            "Projets/C1-Petit/notes/n.md"
        p = c.post("/api/arbre/plan", headers=H,
                   json={"noeud": "Projets/C1-Petit", "sous": "Projets/C1-Grand"}).json()
        r = c.post("/api/alignement/appliquer", headers=H,
                   json={"jeton": p["jeton"], "point_git": False})
        assert r.status_code == 200
        assert c.get("/api/taches/pe").json()["fil"][-1]["id"] == "Projets/C1-Grand/C1-Petit"
        assert [x["chemin"] for x in c.get("/api/vault/recherche?q=pélican").json()] == \
            ["Projets/C1-Grand/C1-Petit/notes/n.md"]
        assert c.post("/api/arbre/plan", headers=H,
                      json={"noeud": "casquette:C1", "sous": "casquette:C2"}).status_code == 409
