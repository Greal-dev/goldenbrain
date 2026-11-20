"""INV-CONTROLE-1 : « terminée » n'est retenue que si le contrôle requis par le projet passe ;
verdict, référence de l'état vérifié et journal conservés ; verdict périmé si l'état change."""

import asyncio
import subprocess

import pytest

from conftest import ecrire, scenario_ok
from orchestrateur import controle
from orchestrateur.moteur import Moteur

VERIF = "import pathlib, sys\nsys.exit(0 if pathlib.Path('ok.txt').read_text().strip() == 'ok' else 3)\n"


def rendu(statut="terminee", extra=""):
    return f"Fini.\n<fiche>\nstatut: {statut}\nfait: livré\n{extra}situation: prête\n</fiche>"


def git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


@pytest.fixture
def depot_git(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, "init", "-q")
    (d / "verif.py").write_text(VERIF, encoding="utf-8")
    (d / "ok.txt").write_text("faux", encoding="utf-8")
    git(d, "add", ".")
    git(d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return d


def declarer(racine, depot, commande='"{python} verif.py"'):
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           f"---\ntype: contexte\ncasquette: C1-Pro\nnom: Alpha\ndepot: \"{depot}\"\n"
           f"controle: {commande}\n---\n")


def tour(config, vault, faux, texte=None, ident="mere"):
    faux.scenario = scenario_ok(rendu=texte or rendu())

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre(ident, "go")
        while any(not b.done() for b in m.boucles.values()):
            await asyncio.gather(*m.boucles.values(), return_exceptions=True)
        return m

    return asyncio.run(scenario())


def test_echec_puis_correction_puis_modification_rend_le_verdict_perime(
        racine, config, vault, faux, depot_git):
    declarer(racine, depot_git)
    m = tour(config, vault, faux)
    t = vault.tache("mere")
    assert t.statut == "retour-humain"  # l'échec garde la tâche ouverte, rendue à l'utilisateur
    v = m.controle_vue("mere")["verdict"]
    assert v["verdict"] == "echoue" and "code 3" in v["cause"] and v["journal"]
    assert str(t.fm["controle"]).startswith("échoué le ")

    (depot_git / "ok.txt").write_text("ok", encoding="utf-8")
    git(depot_git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "corrige")
    vault.poser_statut("mere", "en-cours")
    m = tour(config, vault, faux)
    assert vault.tache("mere").statut == "fait"  # « terminée », jamais « clôturée » d'office
    v = m.controle_vue("mere")["verdict"]
    assert v["verdict"] == "reussi" and v["perime"] is False and "@" in v["reference"]

    (depot_git / "ok.txt").write_text("ok modifié", encoding="utf-8")
    assert m.controle_vue("mere")["verdict"]["perime"] is True


def test_sans_controle_declare_aucune_preuve_et_fin_retenue(config, vault, faux):
    m = tour(config, vault, faux)
    assert vault.tache("mere").statut == "fait"
    assert m.controle_vue("mere") is None and "controle" not in vault.tache("mere").fm


def test_pas_de_controle_si_l_agent_ne_declare_pas_terminee(racine, config, vault, faux, depot_git):
    declarer(racine, depot_git)
    m = tour(config, vault, faux, rendu("en_cours"))
    assert vault.tache("mere").statut == "en-cours"
    assert m.controle_vue("mere")["verdict"] is None  # requis, jamais lancé


def test_controle_dossier_hors_du_depot_refuse(racine, config, vault, faux, depot_git, tmp_path):
    declarer(racine, depot_git)
    m = tour(config, vault, faux, rendu(extra=f"controle_dossier: {tmp_path}\n"))
    assert vault.tache("mere").statut == "retour-humain"
    assert "hors du dossier du code" in m.controle_vue("mere")["verdict"]["cause"]


def test_controle_dossier_dans_le_depot_est_celui_verifie(racine, config, vault, faux, depot_git):
    arbre = depot_git / "arbres" / "gb-x"
    arbre.mkdir(parents=True)
    (arbre / "verif.py").write_text(VERIF, encoding="utf-8")
    (arbre / "ok.txt").write_text("ok", encoding="utf-8")
    declarer(racine, depot_git)
    m = tour(config, vault, faux, rendu(extra="controle_dossier: arbres/gb-x\n"))
    assert vault.tache("mere").statut == "fait"
    assert m.controle_vue("mere")["verdict"]["dossier"] == str(arbre.resolve())


def test_commande_introuvable_est_un_echec_lisible(racine, config, vault, faux, depot_git):
    declarer(racine, depot_git, "commande-qui-n-existe-pas")
    m = tour(config, vault, faux)
    assert vault.tache("mere").statut == "retour-humain"
    assert "non lancée" in m.controle_vue("mere")["verdict"]["cause"]


def test_delai_depasse_tue_le_controle(racine, config, vault, faux, depot_git):
    (depot_git / "lent.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    declarer(racine, depot_git, '"{python} lent.py"')
    config.moteur.controle_duree_s = 1
    m = tour(config, vault, faux)
    assert "durée maximale" in m.controle_vue("mere")["verdict"]["cause"]
    assert m.poste.actuelle() is None  # le poste tenu pendant le contrôle est rendu


def test_tache_permanente_jamais_controlee(racine, config, vault, faux, depot_git):
    declarer(racine, depot_git)
    ecrire(racine, "Projets/C1-Alpha/taches/perm.md",
           "---\ntype: tache\nstatut: a-faire\nnature: permanente\n---\n\n# Perm\n")
    m = tour(config, vault, faux, ident="perm")
    assert vault.tache("perm").statut == "en-cours"
    assert m.controle_vue("perm")["verdict"] is None


def test_verdict_persiste_au_redemarrage(racine, config, vault, faux, depot_git):
    declarer(racine, depot_git)
    tour(config, vault, faux)
    relu = controle.Controles(config.donnees / "etat" / "controles.json")
    assert relu.dernier("mere")["verdict"] == "echoue"


def test_argv_sans_shell_et_interprete_du_serveur():
    import sys
    a = controle.argv('{python} "scripts/check.py" --vite')
    assert a[0] == sys.executable and a[1:] == ["scripts/check.py", "--vite"]
