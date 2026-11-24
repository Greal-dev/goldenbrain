"""Tours (INV-EXEC-1..5), messages entre tâches (INV-MSG-1), propositions."""

import asyncio
import json

import pytest

from orchestrateur import fiches
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Conflit, Invalide, NonTrouve
from conftest import RENDU, scenario_ok


def executer(coro):
    return asyncio.run(coro)


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def moteur(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m._q = m.abonner()
    return m


def vider(m):
    out = []
    while not m._q.empty():
        out.append(m._q.get_nowait())
    return out


def test_tour_complet(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        assert m.soumettre("mere", "travaille") == "en_file"
        await finir(m)
        return m

    m = executer(scenario())
    t = vault.tache("mere")
    assert t.fm["statut"] == "retour-humain" and t.fm["session"] == "s-1"
    assert t.fm["harnais"] == "faux"
    fiche = fiches.lire_fiche(fiches.lire(t.chemin))
    assert fiche["fait"] == "lu le dossier" and fiche["sous_taches"][1] == {"fait": False,
                                                                             "texte": "écrire"}
    assert m.etat_de("mere") == "inactif"
    types = [e["type"] for e in vider(m)]
    # INV-VERROU-1 : la mise en file se publie (« arbre »), avant le début du tour.
    assert types[:3] == ["arbre", "tour_debut", "arbre"] and "tour_texte" in types and "tour_outil" in types
    lance = faux.lances[0]
    assert lance["session"] is None and lance["deriver"] is False
    assert lance["env"] == {"ORCH_TACHE": "mere", "ORCH_SAUTS": "0",
                            "ORCH_URL": "http://127.0.0.1:8399"}
    assert "Tâche Mère" in lance["consigne"] and "C1 > Operation-X > Alpha" in lance["consigne"]
    assert "{autre}" in lance["consigne"] and "orch.py" in lance["consigne"]
    journaux = list((config.donnees / "journal").rglob("mere-*.jsonl"))
    assert len(journaux) == 1  # INV-EXEC-4
    lignes = journaux[0].read_text("utf-8").splitlines()
    assert len(lignes) == 5  # orch_message + 4 événements
    assert json.loads(lignes[0])["type"] == "orch_message"


def test_evenement_tour_fin_et_fiche_absente(config, vault, faux):
    faux.scenario = scenario_ok(rendu="Réponse sans bloc. " * 50)

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return vider(m)

    evts = executer(scenario())
    fin = next(e for e in evts if e["type"] == "tour_fin")
    assert fin == {"type": "tour_fin", "tache": "mere", "statut": "en-cours",
                   "fiche_absente": True}  # INV-EXEC-12 : relance, pas de retour à l'utilisateur
    fiche = fiches.lire_fiche(fiches.lire(vault.tache("mere").chemin))
    assert len(fiche["situation"]) <= 500 and fiche["situation"].startswith("Réponse sans bloc.")


def test_fiche_absente_relancee_une_fois_puis_bloque_sans_retour_utilisateur(config, vault, faux):
    faux.scenario = scenario_ok(rendu="Texte libre sans bloc fiche.")

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return m

    m = executer(scenario())
    assert [x["message"][:30] for x in faux.lances][1:] == ["[GoldenBrain — fiche manquante"]
    t = vault.tache("mere")
    assert t.fm["statut"] == "bloque" and "fiche absente après relance" in t.fm["echec_tour"]
    assert m.relance_fiche.public() == {"absentes": 2, "relancees": 1, "bloquees": 1}


def test_fiche_absente_puis_fiche_rendue_a_la_relance_ne_bloque_pas(config, vault, faux, monkeypatch):
    faux.scenario = scenario_ok(rendu="Texte libre sans bloc fiche.")
    from orchestrateur import moteur as mod, relance_fiche
    vraie = relance_fiche.redemander

    def redemander(m, ident):
        faux.scenario = scenario_ok()  # la relance reçoit un vrai bloc fiche
        vraie(m, ident)
    monkeypatch.setattr(mod, "redemander", redemander)

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return m

    m = executer(scenario())
    assert vault.tache("mere").fm["statut"] != "bloque" and len(faux.lances) == 2
    assert m.relance_fiche.relancees == set()


def test_session_ecrite_des_le_premier_evenement(config, vault, faux):
    faux.scenario = [Evenement("session", session="tot"), "attendre",
                     Evenement("fin", session="tot", texte="ok")]
    faux.liberer = None

    async def scenario():
        faux.liberer = asyncio.Event()
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        for _ in range(50):
            await asyncio.sleep(0.01)
            if vault.tache("mere").fm.get("session"):
                break
        pendant = (vault.tache("mere").fm.get("session"), vault.tache("mere").fm["statut"],
                   m.etat_de("mere"))
        faux.liberer.set()
        await finir(m)
        return pendant

    assert executer(scenario()) == ("tot", "en-cours", "en_cours")


def test_echec_du_harnais_bloque(config, vault, faux):
    faux.scenario = [Evenement("session", session="s"), Evenement("erreur", texte="boum")]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return vider(m)

    fin = next(e for e in executer(scenario()) if e["type"] == "tour_fin")
    assert fin["statut"] == "bloque" and fin["erreur"] == "boum"
    assert vault.tache("mere").fm["statut"] == "bloque"


def test_exception_du_harnais_bloque_sans_tuer_le_moteur(config, vault, faux):
    faux.scenario = [RuntimeError("plantage")]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return m.etat_de("mere")

    assert executer(scenario()) == "inactif"
    assert vault.tache("mere").fm["statut"] == "bloque"


def test_file_attente_un_tour_a_la_fois_dans_l_ordre(config, vault, faux):
    faux.scenario = ["attendre", Evenement("fin", session="s", texte=RENDU)]

    async def scenario():
        faux.liberer = asyncio.Event()
        m = moteur(config, vault, faux)
        m.soumettre("mere", "premier")
        await asyncio.sleep(0.02)
        etat2 = m.soumettre("mere", "second")
        en_file = m.etat_global()["en_file"]
        nb_lances = len(faux.lances)
        faux.liberer.set()
        await finir(m)
        return etat2, en_file, nb_lances

    etat2, en_file, nb_lances = executer(scenario())
    assert etat2 == "en_cours" and en_file == 1 and nb_lances == 1  # INV-EXEC-2
    assert [x["message"] for x in faux.lances] == ["premier", "second"]
    assert faux.lances[1]["session"] == "s"  # le second tour reprend la conversation


def test_arret_marque_interrompu_sans_relance(config, vault, faux):
    faux.scenario = [Evenement("session", session="s"), "attendre"]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "premier")
        m.soumettre("mere", "second")
        await asyncio.sleep(0.02)
        etat = await m.arreter("mere")
        await finir(m)
        return etat, m.etat_de("mere"), vider(m)

    etat, final, evts = executer(scenario())
    assert etat == final == "interrompu"
    assert len(faux.lances) == 1  # INV-EXEC-1 : la file est vidée, rien n'est relancé
    fin = next(e for e in evts if e["type"] == "tour_fin")
    assert fin["erreur"] == "tour interrompu"
    assert vault.tache("mere").fm["statut"] == "retour-humain"


def test_message_entre_taches_et_plafond_de_sauts(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("enfant", "coucou", de="mere", sauts=3)
        await finir(m)
        with pytest.raises(Conflit):
            m.soumettre("enfant", "boucle", de="mere", sauts=4)  # INV-MSG-1
        with pytest.raises(NonTrouve):
            m.soumettre("inconnue", "x")
        with pytest.raises(Invalide):
            m.soumettre("enfant", "  ")

    executer(scenario())
    assert faux.lances[0]["message"] == "[Message de la tâche mere]\ncoucou"
    assert faux.lances[0]["env"]["ORCH_SAUTS"] == "3"


def test_derivation_avec_fil_et_sans(config, vault, faux):
    vault.modifier("mere", {"session": "orig"})

    async def scenario():
        m = moteur(config, vault, faux)
        fille = m.deriver("mere", "Fille", "enfant", avec_fil=True, message="suite")
        await finir(m)
        soeur = m.deriver("enfant", "Soeur", "soeur", avec_fil=False)
        with pytest.raises(Conflit):
            m.deriver("enfant", "x", "enfant", avec_fil=True)
        with pytest.raises(Invalide):
            m.deriver("mere", "x", "cousine", avec_fil=False)
        return fille, soeur

    fille, soeur = executer(scenario())
    assert faux.lances[0]["session"] == "orig" and faux.lances[0]["deriver"] is True
    tf = vault.tache(fille)
    assert tf.parent_brut == "mere" and tf.fm["session"] == "s-1"  # nouvelle session écrite
    assert vault.tache(soeur).parent_brut == "mere"
    assert vault.tache(soeur).conteneur == "Projets/C1-Alpha"


def test_propositions_creer_accepter_refuser_persistance(config, vault, faux):
    config.interface.office = []  # INV-PROP-1 : ce test éprouve le geste à trancher
    async def scenario():
        m = moteur(config, vault, faux)
        p1 = m.proposer("deplacer", "enfant", "Projets/C2-Beta", de="mere")
        p2 = m.proposer("projet", "x", "Projet X")
        p3 = m.proposer("ticket", "mere", "Sous-ticket", motif="Traite la part restante du sujet")
        assert m.etat_global()["propositions"] == 3
        m.trancher(p1["n"], True)
        m.trancher(p2["n"], False)
        m.trancher(p3["n"], True)
        with pytest.raises(Conflit):
            m.trancher(p1["n"], False)
        with pytest.raises(Invalide):
            m.proposer("supprimer", "x", "y")
        with pytest.raises(NonTrouve):
            m.trancher(99, True)
        return m

    executer(scenario())
    assert vault.tache("enfant").conteneur == "Projets/C2-Beta"
    assert vault.tache("x").conteneur == "Projets/Sans"
    assert any(t.parent_brut == "mere" and t.titre == "Sous-ticket"
               for t in vault.index()[0].values())
    persiste = json.loads((config.donnees / "etat" / "propositions.json").read_text("utf-8"))
    assert [p["etat"] for p in persiste] == ["acceptee", "refusee", "acceptee"]
    m2 = Moteur(config, vault, {"faux": faux})  # relu au redémarrage
    assert len(m2.propositions.liste) == 3 and m2.etat_de("mere") == "inactif"


def test_paperclip_le_tour_ne_touche_pas_au_statut(config, vault, faux, racine):
    p = racine / "_meta/taches/pc.md"
    p.write_text("---\nstatut: a-faire\npaperclip: X\n---\n# P\n", encoding="utf-8")

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("pc", "go")
        await finir(m)

    executer(scenario())
    fm = vault.tache("pc").fm
    assert fm["statut"] == "a-faire" and fm["session"] == "s-1"


# --- durcissement (revue adversariale) ---------------------------------------------------

def test_exception_apres_session_tue_le_processus_et_libere_la_file(config, vault, faux):
    config.moteur.simultanes_max = 1
    faux.scenario = [Evenement("session", session="s"), RuntimeError("plantage")]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "premier")
        m.soumettre("mere", "second")
        await finir(m)
        m.soumettre("enfant", "autre")  # le sémaphore a bien été rendu
        await finir(m)
        return m, vider(m)

    m, evts = executer(scenario())
    assert len(faux.arrets) == 2  # chaque tour en échec tue son arbre de processus
    # INV-EXEC-11 : « mere » bloquée retient sa file (échoué en tête) ; l'autre tâche part.
    assert [x["message"] for x in faux.lances] == ["premier", "autre"]
    assert [e.texte for e in m.files["mere"]] == ["premier", "second"] and "mere" in m.retenus
    assert m._sem.pris == 0 and m.etat_de("mere") == "inactif"
    fins = [e for e in evts if e["type"] == "tour_fin"]
    assert len(fins) == 2 and all("plantage" in e["erreur"] for e in fins)


def test_journal_impossible_tour_en_echec_sans_boucle_morte(config, vault, faux):
    async def scenario():
        m = moteur(config, vault, faux)
        ouvrir = m._journal
        appels = []

        def journal(ident):
            appels.append(ident)
            if len(appels) == 1:
                raise PermissionError("disque verrouillé")
            return ouvrir(ident)

        m._journal = journal
        m.soumettre("mere", "premier")
        m.soumettre("mere", "second")
        await finir(m)
        m.liberer("mere")  # INV-EXEC-11 : geste humain, la file retenue repart dans l'ordre
        await finir(m)
        return vider(m)

    fins = [e for e in executer(scenario()) if e["type"] == "tour_fin"]
    assert "disque verrouillé" in fins[0]["erreur"] and "erreur" not in fins[1]
    assert [x["message"] for x in faux.lances] == ["premier", "second"]


def test_redemarrage_apres_plantage_marque_interrompu_sans_relance(config, vault, faux):
    faux.scenario = [Evenement("session", session="s"), "attendre"]
    fichier = config.donnees / "etat" / "tours.json"

    async def scenario():
        m1 = moteur(config, vault, faux)
        m1.soumettre("mere", "go")
        await asyncio.sleep(0.02)
        pendant = json.loads(fichier.read_text("utf-8"))
        m2 = Moteur(config, vault, {"faux": faux})  # redémarrage sur les mêmes données
        apres = json.loads(fichier.read_text("utf-8"))
        etat, boucles = m2.etat_de("mere"), dict(m2.boucles)
        await m1.arreter("mere")
        await finir(m1)
        return pendant, apres, etat, boucles

    pendant, apres, etat, boucles = executer(scenario())
    assert [x["tache"] for x in pendant] == ["mere"] and apres == [] and etat == "interrompu"  # INV-EXEC-1
    assert boucles == {} and len(faux.lances) == 1


def test_fichiers_d_etat_corrompus_n_empechent_pas_le_demarrage(config, vault, faux):
    etat = config.donnees / "etat"
    etat.mkdir(parents=True)
    (etat / "tours.json").write_text("{pas du json", encoding="utf-8")
    (etat / "propositions.json").write_text("[{", encoding="utf-8")
    m = Moteur(config, vault, {"faux": faux})
    assert m.propositions.liste == [] and m.etats == {}


def test_statut_change_par_humain_pendant_le_tour_respecte(config, vault, faux):
    faux.scenario = ["attendre", Evenement("fin", session="s", texte=RENDU)]

    async def scenario():
        faux.liberer = asyncio.Event()
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await asyncio.sleep(0.02)
        vault.poser_statut("mere", "abandonne", humain=True)
        faux.liberer.set()
        await finir(m)

    executer(scenario())
    t = vault.tache("mere")
    assert t.statut == "abandonne"
    assert fiches.lire_fiche(fiches.lire(t.chemin))["fait"] == "lu le dossier"


def test_message_final_vide_n_ecrase_pas_la_situation(config, vault, faux):
    vault.modifier("mere", {}, fiches.fiche_vide() | {"situation": "ancienne"})
    faux.scenario = [Evenement("fin", session="s", texte="")]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)

    executer(scenario())
    assert fiches.lire_fiche(fiches.lire(vault.tache("mere").chemin))["situation"] == "ancienne"


def test_session_invalide_dans_le_fichier_rien_n_est_lance(config, vault, faux):
    vault.modifier("mere", {"session": "--dangerous; x"})

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return vider(m)

    fin = next(e for e in executer(scenario()) if e["type"] == "tour_fin")
    assert faux.lances == [] and "conversation" in fin["erreur"]
    assert vault.tache("mere").statut == "bloque"


def test_session_invalide_recue_du_harnais_n_est_pas_ecrite(config, vault, faux):
    faux.scenario = [Evenement("session", session="../../x"), Evenement("fin", texte=RENDU)]

    async def scenario():
        m = moteur(config, vault, faux)
        m.soumettre("mere", "go")
        await finir(m)
        return vider(m)

    fin = next(e for e in executer(scenario()) if e["type"] == "tour_fin")
    assert "conversation" in fin["erreur"] and "session" not in vault.tache("mere").fm
    assert faux.arrets
