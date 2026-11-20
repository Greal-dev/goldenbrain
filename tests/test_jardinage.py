"""Jardinage : échéances (INV-JARD-1), tâche permanente, état persistant, configuration."""

import asyncio
import datetime as dt
import json

import pytest

from conftest import ecrire, tache_md
from orchestrateur import config as cfg_mod
from orchestrateur.config import ConfigJardinage
from orchestrateur.jardinage import Jardinier
from test_moteur import executer, finir, moteur

D = dt.datetime


class Horloge:
    def __init__(self, t: D):
        self.t = t

    def __call__(self) -> D:
        return self.t


def jardiner(config, vault, faux, rythme, instants, etat=None, jour="lundi"):
    """Appelle `verifier` à chaque instant, tours finis entre deux ; renvoie (résultats, j)."""
    config.jardinage = ConfigJardinage(rythme=rythme, jour=jour, message="Fais la revue.")
    if etat is not None:
        (config.donnees / "etat").mkdir(parents=True, exist_ok=True)
        (config.donnees / "etat" / "jardinage.json").write_text(etat, encoding="utf-8")
    h = Horloge(instants[0])

    async def scenario():
        m = moteur(config, vault, faux)
        j = Jardinier(m, horloge=h)
        sortie = []
        for t in instants:
            h.t = t
            sortie.append(j.verifier())
            await finir(m)
        return sortie, j

    return executer(scenario())


def test_a_la_demande_aucune_revue_automatique(config, vault, faux):
    sortie, j = jardiner(config, vault, faux, "a-la-demande", [D(2026, 11, 13, 9)])
    assert sortie == [None] and faux.lances == []
    assert j.public() == {"rythme": "a-la-demande", "prochaine": None, "derniere": None,
                          "tache": None}
    executer(asyncio.wait_for(j.boucle(), 1))  # rend la main aussitôt : rien au démarrage


def test_quotidien_une_revue_par_jour_et_tache_reutilisee(config, vault, faux):
    instants = [D(2026, 11, 13, 7, 0), D(2026, 11, 13, 7, 30), D(2026, 11, 13, 12),
                D(2026, 11, 14, 7, 29), D(2026, 11, 14, 7, 31)]
    sortie, j = jardiner(config, vault, faux, "quotidien", instants, etat="{}")
    # 07:00 le 13 : l'échéance du 12 n'a jamais eu de revue ; 07:30 : celle du 13.
    ident = sortie[0]
    assert sortie == [ident, ident, None, None, ident]  # une seule tâche permanente
    assert [x["message"] for x in faux.lances] == ["Fais la revue."] * 3
    t = vault.tache(ident)
    assert t.titre == "Revue de cohérence du second cerveau" and t.conteneur == "_meta"
    persiste = json.loads((config.donnees / "etat" / "jardinage.json").read_text("utf-8"))
    assert persiste == {"tache": ident, "derniere": "2026-11-14T07:31:00", "posees": 0}
    assert j.public()["prochaine"] == "2026-11-15T07:30:00"


def test_quotidien_echeance_du_jour(config, vault, faux):
    etat = json.dumps({"derniere": "2026-11-12T08:00:00"})
    sortie, _ = jardiner(config, vault, faux, "quotidien",
                         [D(2026, 11, 13, 7, 29), D(2026, 11, 13, 7, 30), D(2026, 11, 13, 8)],
                         etat=etat)
    assert sortie[0] is None and sortie[1] and sortie[2] is None


def test_hebdomadaire(config, vault, faux):
    # 13/11/2026 est un vendredi ; échéance : lundi 07:30.
    etat = json.dumps({"derniere": "2026-11-09T08:00:00"})
    sortie, j = jardiner(config, vault, faux, "hebdomadaire",
                         [D(2026, 11, 13, 10), D(2026, 11, 16, 7, 29), D(2026, 11, 16, 7, 30),
                          D(2026, 11, 20, 7, 30)], etat=etat)
    assert sortie[:2] == [None, None] and sortie[2] and sortie[3] is None
    assert j.public()["prochaine"] == "2026-11-23T07:30:00"


def test_echeances_manquees_une_seule_revue(config, vault, faux):
    etat = json.dumps({"derniere": "2026-10-01T07:30:00"})
    sortie, _ = jardiner(config, vault, faux, "quotidien",
                         [D(2026, 11, 13, 9), D(2026, 11, 13, 9, 1), D(2026, 11, 13, 9, 2)],
                         etat=etat)
    assert len([s for s in sortie if s]) == 1 and len(faux.lances) == 1


def test_pas_de_doublon_si_revue_en_file(config, vault, faux):
    config.jardinage = ConfigJardinage(rythme="quotidien")
    h = Horloge(D(2026, 11, 13, 9))

    async def scenario():
        m = moteur(config, vault, faux)
        j = Jardinier(m, horloge=h)
        ident = j.lancer()  # revue manuelle, encore en file
        j.etat["derniere"] = "2026-11-01T00:00:00"  # échéance due malgré tout
        refus = j.verifier()
        m.etats[ident] = "en_cours"
        refus2 = j.verifier()
        await finir(m)
        return refus, refus2

    assert executer(scenario()) == (None, None)
    assert len(faux.lances) == 1


def test_tache_disparue_recreee_et_etat_corrompu_tolere(config, vault, faux):
    sortie, _ = jardiner(config, vault, faux, "quotidien", [D(2026, 11, 13, 9)],
                         etat='{"tache": "disparue", "derniere": "pas une date"')
    assert sortie[0] and sortie[0] != "disparue"


def test_config_sections_absentes_et_lues(tmp_path):
    base = '[vault]\nracine = "."\ntaches = ["*.md"]\n'
    (tmp_path / "a.toml").write_text(base, encoding="utf-8")
    c = cfg_mod.charger(tmp_path / "a.toml")
    assert c.liens.propagation is True and c.jardinage.rythme == "a-la-demande"
    assert c.jardinage.heure == "07:30" and "Revue de cohérence" in c.jardinage.message
    (tmp_path / "b.toml").write_text(base + '[liens]\npropagation = false\n[jardinage]\n'
                                     'rythme = "hebdomadaire"\njour = "jeudi"\n', encoding="utf-8")
    c = cfg_mod.charger(tmp_path / "b.toml")
    assert c.liens.propagation is False and c.jardinage.jour == "jeudi"
    (tmp_path / "c.toml").write_text(base + '[jardinage]\nrythme = "mensuel"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        cfg_mod.charger(tmp_path / "c.toml")


def test_echec_de_soumission_ne_cree_pas_une_tache_par_minute(config, vault, faux):
    # Épreuve du réel 2026-11-14 : la tâche permanente n'était mémorisée qu'après la soumission ;
    # une soumission en échec recréait une tâche de revue à chaque vérification (une par minute).
    config.jardinage = ConfigJardinage(rythme="quotidien")
    h = Horloge(D(2026, 11, 13, 9))

    async def scenario():
        m = moteur(config, vault, faux)
        j = Jardinier(m, horloge=h)
        reel = m.soumettre
        m.soumettre = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("soumission en échec"))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                j.verifier()
        m.soumettre = reel
        ident = j.verifier()  # la panne cesse : la même tâche est réutilisée
        await finir(m)
        return ident

    ident = executer(scenario())
    assert len([t for t in vault.index()[0].values() if t.titre == config.jardinage.titre]) == 1
    assert json.loads((config.donnees / "etat" / "jardinage.json").read_text("utf-8"))["tache"] == ident


# --- INV-JARD-2 : le jardinier propose, n'applique jamais, et plafonne ----------------------
def _jardin(config, vault, faux, racine, **reglages):
    ecrire(racine, "Projets/C1-Alpha/taches/recente.md", tache_md(extra="updated: 2026-11-18\n", titre="Récente"))
    ecrire(racine, "Projets/C1-Alpha/taches/ancienne.md", tache_md(extra="updated: 2026-01-05\n", titre="Ancienne"))
    ecrire(racine, "Projets/C1-Alpha/taches/cible.md", tache_md(titre="Cible"))
    config.jardinage = ConfigJardinage(message="Revue, au plus {plafond}.", **reglages)
    async def passage():
        m = moteur(config, vault, faux)
        j = Jardinier(m, horloge=Horloge(D(2026, 11, 19, 9)))
        return m, j, j.lancer()
    return executer(passage())


async def _relancer(j):
    j.lancer()


def test_proposition_du_jardinier_appliquee_d_office_en_politique_accepter(config, vault, faux, racine):
    m, j, ident = _jardin(config, vault, faux, racine, plafond=3)
    config.interface.propositions = "accepter"
    p = m.proposer("lier", "recente", "voir_aussi:cible", ident, "mentionnée")
    assert p["etat"] == "en_attente"  # jamais d'écriture d'office
    assert "voir_aussi" not in vault.tache("recente").fm


def test_jardinier_depose_plus_que_son_plafond_par_passage(config, vault, faux, racine):
    m, j, ident = _jardin(config, vault, faux, racine, plafond=2)
    for _ in range(2):
        m.proposer("lier", "recente", "voir_aussi:cible", ident, "mentionnée")
    with pytest.raises(Exception, match="plafond du jardinier"):
        m.proposer("lier", "ancienne", "voir_aussi:cible", ident, "mentionnée")
    m.proposer("lier", "ancienne", "voir_aussi:cible", "autre-agent", "hors jardinier")  # non concerné
    executer(_relancer(j))  # un nouveau passage remet le compte à zéro
    m.proposer("lier", "ancienne", "voir_aussi:cible", ident, "mentionnée")


def test_message_du_passage_porte_le_plafond_et_les_taches_recentes(config, vault, faux, racine):
    m, j, ident = _jardin(config, vault, faux, racine, plafond=5, recentes_jours=14)
    message = j._message()
    assert "au plus 5" in message and "recente — Récente" in message
    assert "ancienne" not in message


def test_plafond_et_fraicheur_hors_bornes_refuses():
    with pytest.raises(ValueError, match="plafond"):
        ConfigJardinage(plafond=0)
    with pytest.raises(ValueError, match="recentes_jours"):
        ConfigJardinage(recentes_jours=400)
