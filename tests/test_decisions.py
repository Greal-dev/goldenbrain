"""Page « Décisions » : agrégation des sources, extraction de la question, tri, gestes (INV-DECISIONS-1)."""

import pytest
from fastapi.testclient import TestClient

from conftest import ecrire, tache_md
from orchestrateur import api, decisions
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from test_api import BASE, H


@pytest.fixture
def monde(config, vault, faux, racine):
    t = "Projets/C1-Alpha/taches/"
    ecrire(racine, t + "q-comm.md", tache_md("retour-humain", 'commentaire: "Quelle option ?"\n', "Q comm"))
    ecrire(racine, t + "q-pas.md", tache_md("retour-humain", "priorite: haute\n", "Q pas"))
    ecrire(racine, t + "a-valider.md", tache_md("fait", "session: s-1\n", "À valider"))
    ecrire(racine, t + "a-valider2.md", tache_md("fait", "session: s-2\n", "À valider 2"))
    ecrire(racine, t + "en-retard.md", tache_md("a-faire", "echeance: 2020-01-01\n", "En retard"))
    ecrire(racine, t + "double.md", tache_md("retour-humain", "echeance: 2020-01-01\n", "Double"))
    vault.modifier("q-pas", {}, {**vault.tache("q-pas").fiche, "prochain_pas": "Choisir A ou B"})
    vault.modifier("a-valider", {}, {**vault.tache("a-valider").fiche, "resultat": "src/x.py", "essai": "lancer x", "fait": "fait"})
    return Moteur(config, vault, {"faux": faux})


def par_tache(res):
    return {d["tache"]: d for d in res["decisions"]}


def test_sources_reunies_une_ligne_par_decision(monde):
    res = decisions.rassembler(monde)
    genres = {d["tache"]: d["genre"] for d in res["decisions"]}
    assert genres["q-comm"] == genres["q-pas"] == genres["double"] == "reponse"
    assert genres["a-valider"] == genres["a-valider2"] == "validation"
    assert genres["en-retard"] == "echeance"
    assert len(res["decisions"]) == res["total"] == decisions.compter(monde) == 6  # « double » : une seule ligne
    assert par_tache(res)["double"]["retard"] is True


def test_question_commentaire_puis_prochain_pas_puis_vide(monde):
    d = par_tache(decisions.rassembler(monde))
    assert (d["q-comm"]["question"], d["q-comm"]["source"]) == ("Quelle option ?", "commentaire")
    assert (d["q-pas"]["question"], d["q-pas"]["source"]) == ("Choisir A ou B", "prochain_pas")
    assert d["double"]["question"] == "" and d["double"]["source"] == "agent"  # aucun journal : vide


def test_derniere_question_prend_le_dernier_paragraphe_interrogatif():
    assert decisions.derniere_question("Intro.\n\nA ou B ?\n\nMerci.") == "A ou B ?"
    assert decisions.derniere_question("Un.\n\nDeux.") == "Deux."
    assert decisions.derniere_question("") == ""


def test_validation_porte_resultat_et_essai_et_rapide_seulement_avec_resultat(monde):
    d = par_tache(decisions.rassembler(monde))
    assert (d["a-valider"]["resultat"], d["a-valider"]["essai"]) == ("src/x.py", "lancer x")
    assert d["a-valider"]["rapide"] is True and d["a-valider2"]["rapide"] is False


def test_proposition_en_attente_une_ligne_rapide_et_tranchee_disparait(monde):
    p = monde.proposer("echeance", "q-comm", "2030-01-01", de="agent", motif="m")
    d = par_tache(decisions.rassembler(monde))
    lg = next(x for x in decisions.rassembler(monde)["decisions"] if x["genre"] == "proposition")
    assert lg["proposition"]["n"] == p["n"] and lg["rapide"] is True and "q-comm" in d
    monde.trancher(p["n"], False)
    assert not [x for x in decisions.rassembler(monde)["decisions"] if x["genre"] == "proposition"]


def test_fermetures_groupees_par_revue_et_statut_pose_seulement_sur_geste(monde, vault):
    a = monde.proposer("fermer", "q-comm", "cloture", de="revue", motif="obsolète")
    b = monde.proposer("fermer", "q-pas", "abandonne", de="revue")
    revue = [x for x in decisions.rassembler(monde)["decisions"] if x["genre"] == "revue"]
    assert len(revue) == 1 and [f["n"] for f in revue[0]["fermetures"]] == [a["n"], b["n"]]
    assert vault.tache("q-comm").statut == "retour-humain"  # proposé, pas posé
    res = decisions.fermer_lot(monde, [a["n"]])
    assert res["faits"] == [a["n"]] and res["echecs"] == []
    assert vault.tache("q-comm").statut == "cloture" and vault.tache("q-pas").statut == "retour-humain"
    assert monde.propositions.get(b["n"])["etat"] == "en_attente"


def test_fermer_refuse_un_statut_inconnu(monde):
    with pytest.raises(Invalide):
        monde.proposer("fermer", "q-comm", "fait")


def test_tri_par_le_classement_de_l_ordonnancement(monde):
    res = decisions.rassembler(monde)
    assert [d["rang"] for d in res["decisions"]] == list(range(1, 7))
    assert res["decisions"][0]["tache"] == "q-pas" and res["decisions"][0]["motif"] == "priorité haute"


def test_lot_de_validations_un_refus_n_arrete_pas_le_lot(monde, vault):
    res = decisions.valider_lot(monde, ["a-valider", "inconnue", "a-valider2"])
    assert res["faits"] == ["a-valider", "a-valider2"]
    assert [e["cible"] for e in res["echecs"]] == ["inconnue"]
    assert not any(vault.a_valider(t) for t in vault.index()[0].values())


def test_routes_liste_lot_et_compteur(monde, config, vault, faux):
    app = api.creer_app(config, monde)
    with TestClient(app, base_url=BASE) as c:
        assert c.get("/api/etat").json()["decisions"] == 6
        liste = c.get("/api/decisions").json()
        assert liste["total"] == 6 and "question" in liste["decisions"][0]
        r = c.post("/api/decisions/valider", json={"taches": ["a-valider"]}, headers=H)
        assert r.status_code == 200 and r.json()["faits"] == ["a-valider"]
        p = monde.proposer("fermer", "q-comm", "cloture", de="revue")
        r = c.post("/api/decisions/fermer", json={"numeros": [p["n"]]}, headers=H)
        assert r.json()["faits"] == [p["n"]]
        assert c.post("/api/decisions/fermer", json={"numeros": [p["n"]]}, headers=H).json()["echecs"]


def test_fiche_muette_sans_sujet_ou_sans_fait_et_documentee_sinon(monde, vault):
    d = par_tache(decisions.rassembler(monde))
    assert d["a-valider"]["sujet"] == "Corps." and d["a-valider"]["fait"] == "fait" and not d["a-valider"]["muette"]
    assert d["a-valider2"]["muette"] and d["a-valider2"]["fait"] == ""
    ecrire(vault.cfg.racine, "Projets/C1-Alpha/taches/sans-sujet.md",
           "---\ntype: tache\nstatut: retour-humain\ntags: []\n---\n\n# Sans sujet\n")
    assert par_tache(decisions.rassembler(monde))["sans-sujet"]["muette"]


def test_documenter_envoie_la_consigne_a_l_agent_de_la_tache(monde):
    envoyes = []
    monde.soumettre = lambda t, texte, *a, **k: envoyes.append((t, texte)) or "en_cours"
    assert decisions.documenter(monde, "a-valider2") == "en_cours"
    assert envoyes[0][0] == "a-valider2"
    assert all(mot in envoyes[0][1] for mot in ("situation", "fait", "essai", "mode de validation"))


def test_creation_par_un_agent_sans_description_refusee_motif_lisible(monde, config):
    app = api.creer_app(config, monde)
    with TestClient(app, base_url=BASE) as c:
        r = c.post("/api/taches", json={"titre": "Nue", "de": "mere"}, headers=H)
        assert r.status_code == 400 and "au moins une phrase" in r.json()["detail"]
        assert c.post("/api/taches", json={"titre": "Nue"}, headers={**H, "X-Orch-Tache": "mere"}).status_code == 400
        assert c.post("/api/taches", json={"titre": "Nue", "de": "mere", "description": "Trop court"}, headers=H).status_code == 400
        assert c.post("/api/taches", json={"titre": "Humain"}, headers=H).status_code == 201  # l'humain reste libre
        ok = c.post("/api/taches", json={"titre": "Dite", "de": "mere",
                                          "description": "Mettre à jour la page d'accueil du site."}, headers=H)
        assert ok.status_code == 201


def test_proposition_tache_ou_ticket_sans_motif_refusee_et_motif_devient_description(monde, vault):
    for type_ in ("tache", "ticket"):
        with pytest.raises(Invalide, match="au moins une phrase"):
            monde.proposer(type_, "q-comm", "Titre seul")
    p = monde.proposer("tache", "q-comm", "Nouvelle", motif="Documenter le flux de reprise après échec")
    monde.trancher(p["n"], True)
    neuve = next(t for t in vault.index()[0].values() if t.titre == "Nouvelle")
    assert "Documenter le flux de reprise" in neuve.chemin.read_text("utf-8")


def test_decision_repondue_reste_affichee_tant_que_le_tour_n_a_pas_demarre(monde):
    """Symptôme (22/11) : la réponse est envoyée, le tour attend (verrou, poste, file) ; la tâche reste au statut
    de retour et la décision continue de s'afficher. Elle doit quitter la liste dès la réponse."""
    import asyncio

    async def scenario():
        bloc = asyncio.Event()

        async def attente(_ident):  # le tour ne démarre pas : verrou tenu par un autre
            await bloc.wait()
        monde._attendre_verrou = attente
        assert "q-comm" in par_tache(decisions.rassembler(monde))
        monde.soumettre("q-comm", "Option A", humain=True)
        await asyncio.sleep(0.05)
        assert monde.vault.tache("q-comm").statut == "retour-humain"  # le tour n'a rien levé
        res = decisions.rassembler(monde)
        assert "q-comm" not in par_tache(res) and decisions.compter(monde) == res["total"] == 5
        assert [r["tache"] for r in res["reprises"]] == ["q-comm"]  # mention discrète : « l'agent reprend »
        assert "q-pas" in par_tache(res)  # les autres décisions restent
        bloc.set()
        await monde.arreter("q-comm")

    asyncio.run(scenario())


def test_decision_reportee_masquee_jusqu_a_sa_date_par_toutes_les_voies(monde):
    """Symptôme (23/11) : un report ne retirait pas la décision. Voies : POST /temps et geste Telegram ; retour à la date."""
    from orchestrateur import telegram_assistant, temps
    assert {"q-comm", "q-pas", "a-valider", "en-retard"} <= set(par_tache(decisions.rassembler(monde)))
    avant = monde.etat_global()["a_moi"]
    temps.poser(monde.vault, "q-comm", "2099-01-01", None)  # voie de l'interface (POST /taches/{id}/temps)
    telegram_assistant.appliquer(monde, "oui", {"tache": "a-valider", "cle": "echeance", "valeur": "2099-01-01"})
    telegram_assistant.appliquer(monde, "oui", {"tache": "en-retard", "cle": "echeance", "valeur": "2099-01-01"})
    res = decisions.rassembler(monde)
    assert not {"q-comm", "a-valider", "en-retard"} & set(par_tache(res))
    assert "q-pas" in par_tache(res) and decisions.compter(monde) == res["total"] == 3
    assert monde.etat_global()["a_moi"] == avant - 1  # la pastille « À moi » suit
    monde.vault.modifier("q-comm", {"echeance": "2020-01-01", "reporte_jusqu_au": "2020-01-01"})  # date atteinte
    assert "q-comm" in par_tache(decisions.rassembler(monde))
    temps.poser(monde.vault, "q-pas", "2099-01-01", None)
    temps.poser(monde.vault, "q-pas", "2020-01-01", None)  # nouvelle date déjà passée : plus un report
    assert "q-pas" in par_tache(decisions.rassembler(monde))
