"""Audit L2 (23/11) : `orch`, propositions et gestes — erreurs, plafonds, codes de sortie.

Un test par symptôme de l'audit (B1-B15, C7, C8, C10) : rouge sur l'état d'avant, vert après.
"""

import os
import stat
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from conftest import ecrire, tache_md

from orchestrateur import api, cli, fiches, liens
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Invalide

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
HA = {**H, "X-Orch-Tache": "petit"}  # appel d'un agent (en-tête posé par `orch`)
RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(config, vault, faux):
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


@pytest.fixture
def appels(monkeypatch):
    """Faux `appeler` : journal des requêtes ; `reponses` se complète par test."""
    class Journal(list):
        pass

    journal, reponses = Journal(), {}

    def faux_appeler(methode, chemin, corps=None):
        journal.append((methode, chemin, corps))
        if (methode, chemin) not in reponses:
            raise cli.ErreurCli("erreur 404 : inconnu")
        return reponses[(methode, chemin)]

    monkeypatch.setattr(cli, "appeler", faux_appeler)
    journal.reponses = reponses
    return journal


def detail(statut="a-faire", lignes=()):
    return {"statut": statut, "conteneur": "Projets/C1-Alpha", "fiche": {"lignes": list(lignes)}}


# --- B1 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("args", [["executeur"], ["executeur", "--serveur", "http://100.64.0.1:8300", "--code", "ABCD-EFGH"]])
def test_orch_executeur_sans_action_demarre_ou_explique(monkeypatch, args):
    from orchestrateur import executeur
    recus = []
    monkeypatch.setattr(executeur, "main", lambda *a: recus.append(a) or 0)
    assert cli.main(args) == 0
    assert len(recus) == 1


# --- B2 ------------------------------------------------------------------------------------------
def test_creer_sans_conteneur_prend_le_projet_de_la_tache_courante(client):
    r = client.post("/api/taches", headers=HA, json={"titre": "Via tâche", "de": "petit",
                                                      "description": "Une description de quatre mots."})
    assert r.status_code == 201
    assert client.get(f"/api/taches/{r.json()['id']}").json()["conteneur"] == "Projets/C1-Alpha"


def test_creer_hors_tache_sans_conteneur_refuse_avec_un_message_clair(appels, capsys):
    assert cli.main(["creer", "Orpheline", "--description", "Une description de quatre mots."]) == 1
    assert "--conteneur" in capsys.readouterr().err
    assert appels == []


# --- B3 ------------------------------------------------------------------------------------------
def remplir(client, n):
    for i in range(n):
        r = client.post("/api/taches", headers=HA, json={
            "titre": f"Fils {'abcdefghijkl'[i] * 6}", "parent": "mere", "forcer": True,
            "description": "Une description de quatre mots.", "de": "petit"})
        assert r.status_code == 201, r.text


def test_nouvelle_ne_leve_pas_le_plafond_de_dix_par_parent_pour_un_agent(client):
    remplir(client, 9)  # mere a déjà « enfant » : 10 ouvertes
    r = client.post("/api/taches", headers=HA, json={"titre": "Fils zzzzzz", "parent": "mere", "forcer": True,
                                                      "description": "Une description de quatre mots.", "de": "petit"})
    assert r.status_code == 409 and r.json()["rangement"]["raison"] == "plafond"
    r = client.post("/api/taches", headers=HA, json={"titre": "Fils zzzzzz", "parent": "mere", "forcer": True,
                                                      "hors_rangement": True,
                                                      "description": "Une description de quatre mots.", "de": "petit"})
    assert r.status_code == 201


def test_l_interface_garde_son_forcer_complet(client):
    remplir(client, 9)
    assert client.post("/api/taches", headers=H, json={"titre": "Fils zzzzzz", "parent": "mere", "forcer": True}).status_code == 201


def test_orch_creer_hors_rangement_transmet_son_drapeau(monkeypatch):
    envoyes = []
    monkeypatch.setattr(cli, "appeler", lambda m, c, corps=None: envoyes.append(corps) or {"id": "n", "titre": "T"})
    assert cli.main(["creer", "T", "--conteneur", "Projets/C1-Alpha", "--description", "Une phrase de description ici.",
                     "--nouvelle"]) == 0
    assert envoyes[0]["forcer"] is True and "hors_rangement" not in envoyes[0]
    assert cli.main(["creer", "T", "--conteneur", "Projets/C1-Alpha", "--description", "Une phrase de description ici.",
                     "--hors-rangement"]) == 0
    assert envoyes[1]["hors_rangement"] is True


# --- B5 ------------------------------------------------------------------------------------------
def test_dire_sur_tache_close_le_dit_au_lieu_de_la_rouvrir_en_silence(appels, capsys):
    appels.reponses[("GET", "/taches/mere")] = detail("cloture")
    appels.reponses[("POST", "/taches/mere/messages")] = {"etat_execution": "en_file"}
    assert cli.main(["dire", "mere", "bonjour"]) == 1
    assert "--rouvrir" in capsys.readouterr().err
    assert not [a for a in appels if a[0] == "POST"]
    assert cli.main(["dire", "mere", "bonjour", "--rouvrir"]) == 0
    sortie = capsys.readouterr().out
    assert "rouverte" in sortie and appels[-1][1] == "/taches/mere/messages"


# --- B6 ------------------------------------------------------------------------------------------
def test_valider_une_tache_non_terminee_est_refuse(client):
    r = client.post("/api/taches/mere/valider", headers=H)
    assert r.status_code == 409 and client.get("/api/taches/mere").json()["statut"] == "a-faire"


def test_valider_une_tache_faite_reste_admis(client):
    client.post("/api/taches/mere/statut", headers=H, json={"statut": "fait"})
    assert client.post("/api/taches/mere/valider", headers=H).json()["statut"] == "cloture"


def test_renvoyer_une_tache_close_est_refuse(client):
    client.post("/api/taches/mere/statut", headers=H, json={"statut": "cloture"})
    assert client.post("/api/taches/mere/renvoyer", headers=H, json={"texte": "reprends"}).status_code == 409


# --- B7 ------------------------------------------------------------------------------------------
def test_proposer_lier_vers_une_cible_inconnue_est_refuse_a_la_creation(client):
    r = client.post("/api/propositions", headers=H, json={"type": "lier", "tache": "mere", "valeur": "alimente:inconnue"})
    assert r.status_code == 404
    assert client.get("/api/propositions").json() == []


def test_proposer_un_auto_lien_est_refuse_a_la_creation(client):
    r = client.post("/api/propositions", headers=H, json={"type": "lier", "tache": "mere", "valeur": "alimente:mere"})
    assert r.status_code == 409 and client.get("/api/propositions").json() == []


def test_proposer_deux_fois_la_meme_chose_ne_depose_qu_une_proposition(config, vault, faux):
    config.interface.office = []  # INV-PROP-1 : ce test éprouve le geste à trancher
    m = Moteur(config, vault, {"faux": faux})
    a = m.proposer("deplacer", "mere", "Projets/C2-Beta")
    b = m.proposer("deplacer", "mere", "Projets/C2-Beta")
    assert b["etat"] == "deja_proposee" and b["n"] == a["n"] and len(m.propositions.liste) == 1


# --- B8 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("type_", ["ticket", "tache"])
def test_proposer_ticket_ou_tache_sans_motif_nomme_le_motif(appels, capsys, type_):
    assert cli.main(["proposer", type_, "mere", "Titre du ticket"]) == 1
    assert "--motif" in capsys.readouterr().err and appels == []


# --- B9 / B10 ------------------------------------------------------------------------------------
def lancer_dans(tmp_path, python_local):
    for nom in ("lancer.sh", "config.depart.toml"):
        (tmp_path / nom).write_bytes((RACINE / nom).read_bytes())
    (tmp_path / "python.local").write_bytes(python_local)
    return subprocess.run(["bash", "lancer.sh"], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_lancer_python_local_inexistant_donne_une_piste_en_francais(tmp_path):
    r = lancer_dans(tmp_path, b"/inexistant/python\n")
    assert r.returncode != 0 and "python.local" in r.stderr and "GUIDE" in r.stderr


def test_lancer_python_local_en_crlf_et_entre_guillemets_est_lu(tmp_path):
    faux_py = tmp_path / "py.sh"
    faux_py.write_text("#!/bin/sh\necho OK-$#\nexit 0\n", encoding="utf-8")
    faux_py.chmod(0o755)
    r = lancer_dans(tmp_path, f'"{faux_py}"\r\n'.encode())
    assert "OK-" in r.stdout


def test_lancer_sans_dependances_dit_quoi_installer(tmp_path):
    faux_py = tmp_path / "py.sh"
    faux_py.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    faux_py.chmod(0o755)
    r = lancer_dans(tmp_path, str(faux_py).encode())
    assert r.returncode != 0 and "Traceback" not in r.stderr and "GUIDE" in r.stderr


def test_serveur_injoignable_donne_la_piste(monkeypatch, capsys):
    monkeypatch.setenv("ORCH_URL", "http://127.0.0.1:1")
    assert cli.main(["arbre"]) == 1
    erreur = capsys.readouterr().err
    assert "lancer.sh" in erreur and "ORCH_URL" in erreur


def test_orch_url_sans_schema_n_est_pas_un_traceback(monkeypatch, capsys):
    monkeypatch.setenv("ORCH_URL", "127.0.0.1:1")
    assert cli.main(["arbre"]) == 1
    assert "Traceback" not in capsys.readouterr().err
    monkeypatch.setenv("ORCH_URL", "http://")
    assert cli.main(["arbre"]) == 1


# --- B11 / B12 -----------------------------------------------------------------------------------
def test_ligne_sans_texte_sort_en_code_non_nul(appels, capsys):
    assert cli.main(["ligne", "mere", ""]) == 1
    assert "texte attendu" in capsys.readouterr().err


def test_chaine_sans_tache_sort_en_code_non_nul(appels, capsys):
    assert cli.main(["chaine", "plan"]) == 1
    assert "ORCH_TACHE" in capsys.readouterr().err


def test_reflexes_apercu_sans_harnais_sort_en_code_non_nul(capsys):
    assert cli.main(["reflexes", "apercu"]) == 1
    assert "--harnais" in capsys.readouterr().err


def test_ligne_texte_et_cocher_ensemble_sont_refuses(appels, capsys):
    assert cli.main(["ligne", "mere", "x", "--cocher", "1"]) == 1
    assert "texte" in capsys.readouterr().err and appels == []


def test_ligne_cocher_est_idempotent(appels, capsys):
    appels.reponses[("GET", "/taches/mere")] = detail(lignes=[{"fait": True, "texte": "a"}, {"fait": False, "texte": "b"}])
    appels.reponses[("POST", "/taches/mere/lignes/basculer")] = {"lignes": [{"fait": True}, {"fait": True}]}
    assert cli.main(["ligne", "mere", "--cocher", "1"]) == 0  # déjà faite : rien n'est basculé
    assert not [a for a in appels if a[1].endswith("/basculer")]
    assert cli.main(["ligne", "mere", "--cocher", "2"]) == 0  # pas faite : cochée
    assert [a for a in appels if a[1].endswith("/basculer")][0][2] == {"index": 1}
    appels.reponses[("GET", "/taches/mere")] = detail(lignes=[{"fait": True, "texte": "a"}])
    assert cli.main(["ligne", "mere", "--decocher", "1"]) == 0
    assert appels[-1][1].endswith("/basculer")


def test_ligne_cocher_hors_liste_est_une_erreur(appels, capsys):
    appels.reponses[("GET", "/taches/mere")] = detail(lignes=[{"fait": True, "texte": "a"}])
    assert cli.main(["ligne", "mere", "--cocher", "5"]) == 1


# --- B16 / B17 / B18 / B24 (P3) ---------------------------------------------------------------
def test_erreur_argparse_est_en_francais(capsys):
    with pytest.raises(SystemExit):
        cli.main(["lire"])
    erreur = capsys.readouterr().err
    assert "arguments obligatoires manquants" in erreur and "required" not in erreur


def test_texte_non_guillemete_donne_le_conseil_des_guillemets(capsys):
    with pytest.raises(SystemExit):
        cli.main(["dire", "mere", "bonjour", "tout", "le", "monde"])
    assert "guillemets" in capsys.readouterr().err


def test_creer_titre_vide_nomme_le_titre_pas_la_description(appels, capsys):
    assert cli.main(["creer", "", "--conteneur", "Projets/C1-Alpha", "--description", "Une phrase de description ici."]) == 1
    assert "titre attendu" in capsys.readouterr().err and appels == []


def test_reflexes_langue_inconnue_est_refusee():
    with pytest.raises(SystemExit):
        cli.main(["reflexes", "etat", "--langue", "xx"])


# --- C7 ------------------------------------------------------------------------------------------
def test_proposition_tache_acceptee_refuse_un_doublon(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    p = m.proposer("tache", "mere", "Enfant", motif="Une description de quatre mots.")
    with pytest.raises(Conflit):
        m.trancher(p["n"], True)  # « Enfant » existe déjà et est ouverte
    assert m.propositions.get(p["n"])["etat"] == "en_attente"


def test_proposition_ticket_accepte_respecte_le_plafond_et_lie_l_integration(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    for i in range(9):
        vault.creer(f"Fils {'abcdefghi'[i] * 6}", None, "mere", "Une description de quatre mots.")
    p = m.proposer("ticket", "mere", "Sujet unique zzzzzz", motif="Une description de quatre mots.")
    with pytest.raises(Conflit):
        m.trancher(p["n"], True)  # 10 ouvertes sous « mere »


def test_proposition_tache_acceptee_est_liee_a_l_integration(config, vault, faux, racine):
    config.interface.office = []  # INV-PROP-1 : ce test éprouve le geste à trancher
    ecrire(racine, "Projets/C1-Alpha/contexte.md",
           "---\ntype: contexte\ncasquette: C1-Pro\nparent: \"[[Operation-X]]\"\nnom: Alpha\nintegration: integ\n---\n")
    ecrire(racine, "Projets/C1-Alpha/taches/integ.md", tache_md(titre="Intégrer les branches"))
    m = Moteur(config, vault, {"faux": faux})
    for type_, titre in (("tache", "Sujet unique zzzzzz"), ("ticket", "Autre sujet yyyyyy")):
        m.trancher(m.proposer(type_, "mere", titre, motif="Une description de quatre mots.")["n"], True)
        nouvelle = next(t for t in vault.index()[0].values() if t.titre == titre)
        assert "integ" in [r["id"] for r in liens.refs(vault.index()[0], nouvelle.id)["alimente"]], type_


# --- C8 ------------------------------------------------------------------------------------------
def test_deux_acceptations_simultanees_d_une_operation_sont_refusees(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.propositions.reserver(7)
    with pytest.raises(Conflit):
        m.propositions.reserver(7)
    m.propositions.liberer(7)
    m.propositions.reserver(7)


def test_api_accepter_une_operation_deja_en_cours_repond_409(client):
    p = client.post("/api/propositions", headers=H, json={"type": "operation", "tache": "mere", "valeur": "Nouvelle-Op"}).json()
    client.app.state.moteur.propositions.reserver(p["n"])
    assert client.post(f"/api/propositions/{p['n']}/accepter", headers=H).status_code == 409


# --- C10 -----------------------------------------------------------------------------------------
def test_fiche_reecrite_conserve_ses_droits_d_origine(tmp_path):
    f = tmp_path / "t.md"
    f.write_text("a", encoding="utf-8")
    f.chmod(0o755)
    fiches.ecrire_atomique(f, "b")
    assert stat.S_IMODE(f.stat().st_mode) == 0o755 and f.read_text("utf-8") == "b"


def test_fiche_neuve_prend_les_droits_du_umask_pas_0600(tmp_path):
    f = tmp_path / "neuve.md"
    fiches.ecrire_atomique(f, "b")
    masque = os.umask(0)
    os.umask(masque)
    assert stat.S_IMODE(f.stat().st_mode) == 0o666 & ~masque
