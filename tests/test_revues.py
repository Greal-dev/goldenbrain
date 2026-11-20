"""Lot 3 : statuts déclarés, revues de personas, validation (INV-EQUIPE-1, INV-VALID-1)."""

import asyncio
import json

import pytest

from orchestrateur import fiches
from orchestrateur.config import ConfigValidation
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.revues import analyser_avis
from conftest import ecrire, tache_md
from test_moteur import executer, moteur, vider

FICHE = "<fiche>\nstatut: {statut}\nfait: livré\nsituation: prête\nreste: rien\nprochain_pas: -\n</fiche>"
OK = "Rien à redire.\n<avis>\nverdict: ok\npoints:\n</avis>"
RESERVES = "Voir.\n<avis>\nverdict: reserves\npoints:\n- manque le test\n- nom flou\n</avis>"


def rendu(statut="terminee"):
    return "Fait.\n" + FICHE.format(statut=statut)


def evs(session, texte):
    return [Evenement("session", session=session), Evenement("fin", session=session, texte=texte)]


def multi(faux, scenarios: dict):
    """`scenarios[persona ou ""]` : liste d'événements, ou liste de listes consommées tour à tour."""
    restes = {k: list(v) if v and isinstance(v[0], list) else None for k, v in scenarios.items()}

    async def lancer(self, message, *, session, deriver, consigne, env, modele=""):
        cle = env.get("ORCH_PERSONA", "")
        type(self).lances.append({"message": message, "session": session, "consigne": consigne,
                                  "env": env, "persona": cle})
        if restes[cle] is not None:
            suite = restes[cle].pop(0) if len(restes[cle]) > 1 else restes[cle][0]
        else:
            suite = scenarios[cle]
        for ev in suite:
            if ev == "attendre":
                await self.stop.wait()
                return
            yield ev
            await asyncio.sleep(0)

    faux.lancer = lancer
    return faux


async def tout_finir(m: Moteur):
    for _ in range(200):
        en_cours = [b for b in m.boucles.values() if not b.done()] + list(m.revues._fond)
        if not en_cours:
            return
        await asyncio.gather(*en_cours, return_exceptions=True)


def persona(m, ident, nom, **extra):
    m.revues.equipe.ecrire(ident, {"nom": nom, "actif": True, "declenchement": "toujours",
                                   "mandat": f"Mandat {nom}", "focus": f"Focus {nom}", **extra})


def lancer_tache(config, vault, faux, prepa=None, ident="mere"):
    async def scenario():
        m = moteur(config, vault, faux)
        for p in m.revues.equipe.lister():  # exemples d'amorce : hors jeu
            m.revues.equipe.retirer(p["id"])
        if prepa:
            prepa(m)
        m.soumettre(ident, "travaille")
        await tout_finir(m)
        return m

    return executer(scenario())


def lances(faux, cle):
    return [x for x in faux.lances if x["persona"] == cle]


@pytest.mark.parametrize("declaree, statut", [
    ("en_cours", "en-cours"), ("en_attente", "retour-humain"), ("terminee", "fait"),
    ("terminée", "fait"), ("n'importe", "retour-humain"), (None, "retour-humain")])
def test_declaration_de_la_fiche_donne_le_statut(config, vault, faux, declaree, statut):
    texte = "Fait.\n<fiche>\nfait: x\n</fiche>" if declaree is None else rendu(declaree)
    multi(faux, {"": evs("s-1", texte)})
    lancer_tache(config, vault, faux)
    assert vault.tache("mere").statut == statut


def test_terminee_avec_session_reste_ouverte_et_a_valider(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu())})
    m = lancer_tache(config, vault, faux)
    t = vault.tache("mere")
    assert vault.a_valider(t) and vault.ouverte(t)
    pile = vault.arbre(False)
    while (noeud := pile.pop())["id"] != "mere":
        pile += noeud["enfants"]
    assert noeud["a_valider"] is True and noeud["situation"] == "prête"
    assert {"maj", "harnais", "modele"} <= set(noeud) and noeud["harnais"] == "faux"
    etat = m.etat_global()
    assert etat["a_valider"] == 1 and etat["compte"]["fait"] == 1
    assert not vault.a_valider(vault.tache("fermee"))  # `fait` sans session : fermée


def test_revue_ok_n_envoie_rien(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu()), "rssi": evs("p-1", OK)})
    m = lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    assert len(lances(faux, "")) == 1 and len(lances(faux, "rssi")) == 1
    assert vault.tache("mere").statut == "fait" and m.revues.nb_renvois("mere") == 0
    avis = m.revues.avis_de("mere")
    assert avis[0]["verdict"] == "ok" and avis[0]["origine"] == "revue"
    revue = [e for e in vider(m) if e["type"] == "revue"]  # SSE `revue`
    assert revue[-1] == {"type": "revue", "tache": "mere", "persona": "rssi", "verdict": "ok"}
    message = lances(faux, "rssi")[0]["message"]
    assert "Mandat RSSI" in message and "Focus RSSI" in message and "<avis>" in message
    assert str(vault.tache("mere").chemin) in message and "session s-1" in message
    assert lances(faux, "rssi")[0]["env"]["ORCH_TACHE"] == "mere"


def test_revue_avec_reserves_renvoie_puis_rend_la_main_a_boucles_max(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu()), "rssi": evs("p-1", RESERVES)})
    m = lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    taches = lances(faux, "")
    assert len(taches) == 3  # premier tour + boucles_max (2) renvois
    assert taches[1]["message"].startswith("[Revue de RSSI : réserves]")
    assert "- manque le test" in taches[1]["message"]
    assert m.revues.nb_renvois("mere") == 2
    assert vault.tache("mere").statut == "retour-humain"
    persiste = json.loads((config.donnees / "etat" / "revues.json").read_text("utf-8"))
    assert persiste["renvois"] == {"mere": 2}


def test_session_de_revue_reprise_a_la_revue_suivante(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu()), "rssi": evs("p-1", RESERVES)})
    lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    sessions = [x["session"] for x in lances(faux, "rssi")]
    assert sessions == [None, "p-1", "p-1"]


def test_avis_sans_bloc_vaut_reserves_avec_le_texte():
    assert analyser_avis("Je trouve cela fragile.") == ("reserves", ["Je trouve cela fragile."])
    assert analyser_avis(OK) == ("ok", [])


def test_une_revue_ne_declenche_pas_de_revue_ni_n_ecrit_la_tache(config, vault, faux):
    # Le persona rend lui-même un bloc `<fiche>` « terminee » : il ne doit compter pour rien.
    multi(faux, {"": evs("s-1", rendu()), "rssi": evs("p-1", OK + "\n" + rendu())})
    m = lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    assert len(lances(faux, "rssi")) == 1 and len(lances(faux, "")) == 1
    fiche = fiches.lire_fiche(fiches.lire(vault.tache("mere").chemin))
    assert fiche["fait"] == "livré" and vault.tache("mere").statut == "fait"
    assert m.revues.avis_de("mere")[0]["verdict"] == "ok"


def test_mode_persona_ok_cloture(config, vault, faux):
    config.validation = ConfigValidation(mode="persona", persona="relecteur")
    multi(faux, {"": evs("s-1", rendu()), "relecteur": evs("v-1", OK), "rssi": evs("p", OK)})

    def prepa(m):
        persona(m, "rssi", "RSSI")
        persona(m, "relecteur", "Relecteur", declenchement="a-la-demande")
    m = lancer_tache(config, vault, faux, prepa)
    assert vault.tache("mere").statut == "cloture"
    origines = [a["origine"] for a in m.revues.avis_de("mere")]
    assert origines == ["validation", "revue"]  # le validateur passe en dernier


def test_mode_persona_reserves_renvoie(config, vault, faux):
    config.validation = ConfigValidation(mode="persona", persona="relecteur", boucles_max=1)
    multi(faux, {"": [evs("s-1", rendu()), evs("s-1", rendu("en_attente"))],
                 "relecteur": evs("v-1", RESERVES)})
    m = lancer_tache(config, vault, faux, lambda m: persona(m, "relecteur", "Relecteur"))
    taches = lances(faux, "")
    assert taches[1]["message"].startswith("[Validation de Relecteur : réserves]")
    assert vault.tache("mere").statut == "retour-humain" and m.revues.nb_renvois("mere") == 1


def test_tache_verrouillee_jamais_validee_ni_renvoyee(config, vault, faux, racine):
    ecrire(racine, "Projets/C1-Alpha/taches/mere.md",
           tache_md(statut="en-cours", extra="paperclip: run-1\n", titre="Mère"))
    config.validation = ConfigValidation(mode="persona", persona="relecteur")
    multi(faux, {"": evs("s-1", rendu()), "relecteur": evs("v-1", OK),
                 "rssi": evs("p-1", RESERVES)})

    def prepa(m):
        persona(m, "rssi", "RSSI")
        persona(m, "relecteur", "Relecteur")
    m = lancer_tache(config, vault, faux, prepa)
    assert vault.tache("mere").statut == "en-cours"  # INV-VAULT-4 / INV-VALID-1
    assert len(lances(faux, "")) == 1 and m.revues.nb_renvois("mere") == 0
    assert lances(faux, "relecteur") == []


def test_validation_humaine_remet_le_compteur_a_zero(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu()), "rssi": evs("p-1", RESERVES)})
    m = lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    assert m.revues.nb_renvois("mere") == 2
    m.revues.valider("mere")
    assert vault.tache("mere").statut == "cloture" and m.revues.nb_renvois("mere") == 0


def test_solliciter_renvoie_l_avis_a_la_tache(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu("en_attente")), "rssi": evs("p-1", RESERVES)})

    async def scenario():
        m = moteur(config, vault, faux)
        persona(m, "rssi", "RSSI", declenchement="a-la-demande")
        m.revues.solliciter("mere", "rssi", "Est-ce sûr ?")
        await tout_finir(m)
        return m

    m = executer(scenario())
    assert "Question : Est-ce sûr ?" in lances(faux, "rssi")[0]["message"]
    assert lances(faux, "")[0]["message"].startswith("[Avis de RSSI] verdict : reserves")
    assert m.revues.avis_de("mere")[0]["origine"] == "demande"
    assert m.revues.nb_renvois("mere") == 0


def test_tour_de_persona_compte_apparait_et_interrompu_donne_echec(config, vault, faux):
    multi(faux, {"": evs("s-1", rendu()), "rssi": [Evenement("session", session="p"),
                                                   "attendre"]})

    async def scenario():
        m = moteur(config, vault, faux)
        persona(m, "rssi", "RSSI", declenchement="a-la-demande")
        m.revues.solliciter("mere", "rssi", "?")
        for _ in range(100):
            await asyncio.sleep(0.01)
            if m.tours:
                break
        tours = m.etat_global()["tours"]
        await m.fermer()
        await tout_finir(m)
        return m, tours

    m, tours = executer(scenario())
    assert tours[0]["tache"] == "mere" and tours[0]["persona"] == "rssi"
    assert m.revues.avis_de("mere")[0]["verdict"] == "echec"
    assert lances(faux, "") == []  # rien n'est renvoyé à la tâche après l'arrêt
    assert list((config.donnees / "journal").rglob("mere@rssi-*.jsonl"))  # INV-EXEC-4


def test_avis_reste_en_cours_au_redemarrage_devient_echec(config, vault, faux):
    etat = config.donnees / "etat"
    etat.mkdir(parents=True)
    (etat / "revues.json").write_text(json.dumps({"avis": {"mere": [
        {"persona": "rssi", "nom": "RSSI", "verdict": "en_cours", "points": [], "date": "x",
         "origine": "revue"}]}}), encoding="utf-8")
    m = Moteur(config, vault, {"faux": faux})
    assert m.revues.avis_de("mere")[0]["verdict"] == "echec"
    assert m.etat_de("mere") == "inactif"  # jamais relancé


def test_equipe_dans_la_consigne(config, vault, faux):
    config.consigne = "Équipe : {equipe}"
    multi(faux, {"": evs("s-1", rendu("en_attente"))})
    lancer_tache(config, vault, faux, lambda m: persona(m, "rssi", "RSSI"))
    assert lances(faux, "")[0]["consigne"].split("\n")[0] == "Équipe : rssi — RSSI : Focus RSSI"  # puis la langue (INV-LANGUE-1)
