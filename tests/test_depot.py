"""INV-DEPOT-1 : le dossier de travail d'une tâche est le dépôt déclaré par son projet."""

import asyncio

from orchestrateur import depot
from orchestrateur.moteur import Moteur
from conftest import ecrire, tache_md


def contexte(racine, rel, **cles):
    corps = "".join(f"{k}: {v}\n" for k, v in cles.items())
    ecrire(racine, f"{rel}/contexte.md", f"---\ntype: contexte\ncasquette: C1\n{corps}---\n")


def test_projet_avec_depot_declare(racine, vault, tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    contexte(racine, "Projets/C1-Alpha", nom="Alpha", parent='"[[Operation-X]]"', depot=f'"{d}"')
    assert depot.dossier_de_travail(vault, "mere") == (str(d), "depot: de Projets/C1-Alpha")


def test_projet_sans_depot_repli_harnais(racine, vault):
    assert depot.dossier_de_travail(vault, "mere") == (None, "")
    assert depot.conf_harnais(vault, {"dossier": "X"}, "mere") == {"dossier": "X"}


def test_depot_inexistant_ignore(racine, vault, tmp_path):
    contexte(racine, "Projets/C1-Alpha", nom="Alpha", depot=f'"{tmp_path / "absent"}"')
    assert depot.dossier_de_travail(vault, "mere") == (None, "")


def test_descendant_herite_du_depot_du_projet(racine, vault, tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    contexte(racine, "Projets/C1-Alpha", nom="Alpha", depot=f'"{d}"')
    contexte(racine, "Projets/C1-Alpha/Sous", nom="Sous", parent="C1 > C1-Alpha")
    vault.cfg.taches.append("Projets/*/*/taches/*.md")
    ecrire(racine, "Projets/C1-Alpha/Sous/taches/fille.md", tache_md(titre="Fille"))
    assert depot.dossier_de_travail(vault, "fille")[0] == str(d)


def test_table_projets_externes_en_repli(racine, vault, tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    ecrire(racine, "_meta/projets-externes.md",
           f"| chemin | casquette | projet_slug |\n|---|---|---|\n| {d} | C1 | C1-Alpha |\n")
    assert depot.dossier_de_travail(vault, "mere") == (str(d), "_meta/projets-externes.md (C1-Alpha)")


def test_tour_lance_dans_le_depot_tous_harnais(racine, config, vault, faux, tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    contexte(racine, "Projets/C1-Alpha", nom="Alpha", depot=f'"{d}"')
    confs = []
    config.harnais["faux"] = {"dossier": "ailleurs"}

    async def scenario():
        m = Moteur(config, vault, {"faux": lambda c: (confs.append(c), faux(c))[1]})
        m.soumettre("mere", "go")
        while any(not b.done() for b in m.boucles.values()):
            await asyncio.gather(*m.boucles.values(), return_exceptions=True)

    asyncio.run(scenario())
    assert confs[0]["dossier"] == str(d)
    assert config.harnais["faux"] == {"dossier": "ailleurs"}  # la config n'est pas mutée
