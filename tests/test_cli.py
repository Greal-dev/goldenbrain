"""Commande `orch` : requêtes émises, sauts incrémentés, rendu texte, code de retour."""

import pytest

from orchestrateur import cli


@pytest.fixture
def appels(monkeypatch):
    journal = []
    reponses = {
        ("GET", "/arbre"): {"noeuds": [{"id": "casquette:C1", "type": "casquette", "titre": "C1",
                                        "ouvertes": 1, "enfants": [
            {"id": "t1", "type": "tache", "titre": "Tâche", "statut": "en-cours",
             "etat_execution": "en_cours", "ouvertes": 1, "enfants": []}]}]},
        ("POST", "/taches/t%2F2/messages"): {"etat_execution": "en_file"},
        ("POST", "/taches"): {"id": "n1", "titre": "Neuve"},
        ("POST", "/propositions"): {"n": 3, "type": "ticket", "tache": "t1", "valeur": "Sous"},
    }

    def faux(methode, chemin, corps=None):
        journal.append((methode, chemin, corps))
        if (methode, chemin) not in reponses:
            raise cli.ErreurCli("erreur 404 : tâche inconnue")
        return reponses[(methode, chemin)]

    monkeypatch.setattr(cli, "appeler", faux)
    monkeypatch.setenv("ORCH_TACHE", "t1")
    monkeypatch.setenv("ORCH_SAUTS", "2")
    return journal


def test_arbre(appels, capsys):
    assert cli.main(["arbre"]) == 0
    sortie = capsys.readouterr().out
    assert "C1 (casquette, 1 ouvertes)" in sortie and "- t1 [en-cours] Tâche (en_cours)" in sortie


def test_dire_incremente_les_sauts(appels, capsys):
    assert cli.main(["dire", "t/2", "bonjour"]) == 0
    assert appels[-1] == ("POST", "/taches/t%2F2/messages",
                          {"texte": "bonjour", "de": "t1", "sauts": 3})
    assert "message transmis" in capsys.readouterr().out


def test_proposer(appels, capsys):
    assert cli.main(["proposer", "ticket", "t1", "Sous"]) == 0
    assert appels[-1][2] == {"type": "ticket", "tache": "t1", "valeur": "Sous", "de": "t1",
                             "motif": ""}
    assert "proposition n°3" in capsys.readouterr().out


def test_proposer_ignoree_en_mode_simple_ne_plante_pas(appels, monkeypatch, capsys):
    monkeypatch.setattr(cli, "appeler", lambda *a, **k: {"type": "echeance", "tache": "t1",
                                                         "valeur": "2026-12-01", "etat": "ignoree"})
    assert cli.main(["proposer", "echeance", "t1", "2026-12-01"]) == 0
    assert "proposition ignorée" in capsys.readouterr().out


def test_erreur_code_non_nul(appels, capsys):
    assert cli.main(["lire", "inconnue"]) == 1
    assert "404" in capsys.readouterr().err


def test_serveur_injoignable(monkeypatch, capsys):
    monkeypatch.setenv("ORCH_URL", "http://127.0.0.1:1")
    assert cli.main(["arbre"]) == 1
    assert "injoignable" in capsys.readouterr().err


def test_chercher(appels, monkeypatch, capsys):
    resultat = [{"id": "t1", "titre": "Tâche", "statut": "a-faire", "fil_ariane": ["C1", "Alpha"],
                 "extrait": "devis attendu"}]
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: appels.append((m, c)) or resultat)
    assert cli.main(["chercher", "devis élec"]) == 0
    assert appels[-1] == ("GET", "/recherche?q=devis+%C3%A9lec")
    sortie = capsys.readouterr().out
    assert "- t1 [a-faire] Tâche (C1 > Alpha)" in sortie and "devis attendu" in sortie


@pytest.mark.parametrize("args, type_, valeur", [
    (["lier", "t1", "alimente", "t2"], "lier", "alimente:t2"),
    (["lier", "t1", "voir_aussi", "t2"], "lier", "voir_aussi:t2"),
    (["operation", "t1", "Op Nouvelle"], "operation", "Op Nouvelle"),
    (["tache", "t1", "Idée"], "tache", "Idée"),
    (["perimetre", "t1", "Seulement le devis"], "perimetre", "Seulement le devis"),
    (["deplacer", "t1", "Projets/X"], "deplacer", "Projets/X"),
    (["ticket", "t1", "Sous"], "ticket", "Sous"),
    (["projet", "t1", "P"], "projet", "P"),
])
def test_proposer_avec_motif(appels, args, type_, valeur):
    assert cli.main(["proposer", *args, "--motif", "parce que"]) == 0
    assert appels[-1][2] == {"type": type_, "tache": "t1", "valeur": valeur, "de": "t1",
                             "motif": "parce que"}


def test_proposer_lier_exige_type_et_cible(appels):
    with pytest.raises(SystemExit):
        cli.main(["proposer", "lier", "t1", "t2"])
    with pytest.raises(SystemExit):
        cli.main(["proposer", "tache", "t1", "a", "b"])
    assert appels == []


def test_deleguer_cree_l_enfant_le_lie_puis_le_lance_avec_le_brief(appels, capsys, monkeypatch):
    rep = {("POST", "/taches"): {"id": "t9"}, ("POST", "/taches/t9/liens"): {"id": "t9"},
           ("POST", "/taches/t9/messages"): {"etat_execution": "en_file"}}
    journal = []
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: journal.append((m, c, corps)) or rep[(m, c)])
    assert cli.main(["deleguer", "Relever les quotas", "Objectif : lire X ; livrable : tableau"]) == 0
    assert journal[0] == ("POST", "/taches", {"titre": "Relever les quotas", "parent": "t1",
                                              "description": "Objectif : lire X ; livrable : tableau"})
    assert journal[1] == ("POST", "/taches/t9/liens", {"type": "alimente", "cible": "t1"})
    m, c, corps = journal[2]
    assert corps["de"] == "t1" and corps["sauts"] == 3 and corps["texte"].startswith("Objectif : lire X")
    assert "tâche t9 créée sous t1" in capsys.readouterr().out


def test_deleguer_sans_brief_ou_hors_tache_refuse(appels, capsys, monkeypatch):
    assert cli.main(["deleguer", "T", "  "]) == 1
    monkeypatch.delenv("ORCH_TACHE")
    assert cli.main(["deleguer", "T", "brief"]) == 1


def test_creer_marque_l_agent_et_transmet_la_description(appels, capsys):
    assert cli.main(["creer", "Neuve", "--description", "Écrire la page d'accueil du site."]) == 0
    assert appels[-1] == ("POST", "/taches", {"titre": "Neuve", "de": "t1",
                                              "description": "Écrire la page d'accueil du site."})
    assert "tâche créée : n1" in capsys.readouterr().out


def test_creer_sans_description_rend_le_refus_du_serveur(monkeypatch, capsys):
    def refus(methode, chemin, corps=None):
        raise cli.ErreurCli("erreur 400 : tâche sans description : écrivez au moins une phrase")
    monkeypatch.setattr(cli, "appeler", refus)
    assert cli.main(["creer", "Nue"]) == 1
    assert "au moins une phrase" in capsys.readouterr().err
