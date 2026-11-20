"""Coupures réseau (INV-RESEAU-1, 2, 3) : classement des erreurs, gel des départs, reprise au retour
avec sonde factice, cadence 2 puis 5 minutes, une seule reprise, fournisseur seul en panne."""

import asyncio

from orchestrateur import echecs, reseau
from orchestrateur.config import ConfigReseau
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from conftest import scenario_ok

COUPE = "API Error: Can't reach the API server — check your internet or DNS (ENOTFOUND)"
QUOTA = "You’ve hit your usage limit. Try again at 3:14 PM."


class Sonde:
    """Sonde factice : {hôte: joignable} ; aucun accès réseau."""

    def __init__(self, **etat):
        self.etat, self.appels = {"a": True, "b": True, **etat}, 0

    async def __call__(self, hote, delai):
        self.appels += 1
        return self.etat[hote]


def moteur(config, vault, faux, sonde, hotes=None, **kw):
    dormir = kw.pop("dormir", asyncio.sleep)
    config.reseau = ConfigReseau(hotes=hotes or {"faux": ["a"], "autre": ["b"]}, **kw)
    m = Moteur(config, vault, {"faux": faux})
    m.reseau = reseau.Reseau(m, sonde=sonde, dormir=dormir)
    return m


async def finir(m):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)
    await asyncio.sleep(0)


def test_erreur_reseau_reconnue_et_distincte_du_quota():
    assert reseau.est_reseau(COUPE) and reseau.est_reseau("getaddrinfo ENOTFOUND api.anthropic.com")
    assert reseau.est_reseau("Error: connect ECONNREFUSED 1.2.3.4:443") and reseau.est_reseau("fetch failed")
    assert not reseau.est_reseau(QUOTA) and not reseau.est_reseau("rate limit: connection reset by quota")
    assert not reseau.est_reseau("boum") and not reseau.est_reseau("")
    assert echecs.est_quota(QUOTA)


def test_cadence_deux_minutes_puis_cinq():
    c = ConfigReseau()
    assert [reseau.intervalle(c, t) for t in (0, 119, 599)] == [120] * 3
    assert [reseau.intervalle(c, t) for t in (600, 601, 3600)] == [300] * 3


def test_tour_en_erreur_reseau_gele_puis_reprend_au_retour_une_seule_fois(config, vault, faux):
    sonde = Sonde(a=False, b=False)
    m = moteur(config, vault, faux, sonde)
    faux.scenario = [Evenement("session", session="s-1"), Evenement("erreur", texte=COUPE)]

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        assert m.etat_de("mere") == "attente_reseau" and list(m.reseau.gele) == ["mere"]
        assert m.reseau.public()["perdu_depuis"] and m.reseau.public()["en_attente"] == 1
        assert vault.tache("mere").statut == "en-cours" and not vault.tache("mere").fm.get("echec_tour")
        # le réseau revient : une reprise, signée GoldenBrain, dans la même conversation
        faux.scenario = scenario_ok()
        m.reseau._appliquer({"faux": True, "autre": True})
        assert m.reseau.reprendre() == ["mere"]
        await finir(m)
        assert m.reseau.reprendre() == [] and not m.reseau.gele
        assert m.etat_de("mere") == "inactif"

    asyncio.run(essai())
    assert len(faux.lances) == 2
    assert "reprise après interruption" in faux.lances[1]["message"] and "coupure du réseau" in faux.lances[1]["message"]
    assert faux.lances[1]["session"] == "s-1"
    assert "mere" not in m.actifs


def test_aucun_depart_tant_que_le_reseau_est_perdu_puis_depart_au_retour(config, vault, faux, monkeypatch):
    m = moteur(config, vault, faux, Sonde())
    m.reseau._appliquer({"faux": False, "autre": False})
    monkeypatch.setattr(reseau, "INTERVALLE_DEPART_S", 0.01)

    async def essai():
        m.soumettre("mere", "go")
        await asyncio.sleep(0.1)
        assert not faux.lances and m.reseau.public()["en_attente"] == 1 and m.etat_de("mere") == "en_file"
        m.reseau._appliquer({"faux": True, "autre": True})
        await finir(m)

    asyncio.run(essai())
    assert len(faux.lances) == 1


def test_un_seul_fournisseur_injoignable_les_autres_continuent(config, vault, faux):
    sonde = Sonde(a=False, b=True)
    m = moteur(config, vault, faux, sonde)
    faux.scenario = [Evenement("erreur", texte=COUPE)]

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        assert m.etat_de("mere") == "attente_reseau"
        p = m.reseau.public()
        assert p["perdu_depuis"] is None and list(p["hors"]) == ["faux"]  # panne d'un fournisseur, pas du réseau
        assert m.reseau.bloque("faux") and not m.reseau.bloque("autre")

    asyncio.run(essai())


def test_erreur_reseau_sans_coupure_confirmee_reste_un_echec_ordinaire(config, vault, faux):
    sonde = Sonde()  # tout répond : la sonde dément la coupure
    m = moteur(config, vault, faux, sonde)
    faux.scenario = [Evenement("erreur", texte=COUPE)]
    asyncio.run(_un_tour(m))
    assert not m.reseau.gele and m.etat_de("mere") == "inactif"
    assert "La séance de travail a échoué" in vault.tache("mere").fm["echec_tour"] and sonde.appels == 2


async def _un_tour(m):
    m.soumettre("mere", "go")
    await finir(m)


def test_quota_ne_declenche_ni_sonde_ni_gel(config, vault, faux):
    sonde = Sonde(a=False, b=False)
    m = moteur(config, vault, faux, sonde)
    faux.scenario = [Evenement("erreur", texte=QUOTA)]
    asyncio.run(_un_tour(m))
    assert sonde.appels == 0 and not m.reseau.gele
    assert "Quota épuisé" in vault.tache("mere").fm["echec_tour"]


def test_veille_sonde_toutes_les_2_min_puis_5_min_et_reprend_au_retour(config, vault, faux):
    horloge, pauses = [0.0], []

    async def dormir(d):
        pauses.append(d)
        horloge[0] += d
        await asyncio.sleep(0)

    sonde = Sonde(a=False, b=False)
    m = moteur(config, vault, faux, sonde, dormir=dormir)
    m.reseau.dormir, m.reseau.horloge = dormir, lambda: horloge[0]
    faux.scenario = [Evenement("erreur", texte=COUPE)]

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        faux.scenario = scenario_ok()
        while len(pauses) < 7:
            await asyncio.sleep(0)
        sonde.etat.update(a=True, b=True)  # le réseau revient à la 8ᵉ sonde
        await m.reseau._veille
        await finir(m)

    asyncio.run(essai())
    assert pauses[:7] == [120] * 5 + [300] * 2 and len(faux.lances) == 2
    assert m.etat_de("mere") == "inactif" and not m.reseau.gele


def test_gel_reseau_leve_des_le_reveil_de_veille(config, vault, faux):
    # 5 h de veille : l'horloge monotone n'avance pas, l'horloge murale saute ; la pause d'intervalle
    # (monotone) ne finirait jamais seule : seul le guet de veille déclenche la sonde.
    mono, mur, pauses = [0.0], [1000.0], []

    async def dormir(d):
        pauses.append(d)
        await asyncio.Event().wait()  # jamais fini : l'intervalle monotone ne compte pas la veille

    async def guetter(_):
        await asyncio.sleep(0)
        mur[0] += 5 * 3600 if sonde.appels >= 2 else 1

    sonde = Sonde(a=False, b=False)
    m = moteur(config, vault, faux, sonde, dormir=dormir)
    m.reseau.horloge, m.reseau.reel, m.reseau.guetter = lambda: mono[0], lambda: mur[0], guetter
    faux.scenario = [Evenement("erreur", texte=COUPE)]

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        faux.scenario = scenario_ok()
        sonde.etat.update(a=True, b=True)  # le réseau est revenu pendant la veille
        await asyncio.wait_for(m.reseau._veille, 5)
        await finir(m)

    asyncio.run(essai())
    assert pauses == [120] and len(faux.lances) == 2
    assert m.etat_de("mere") == "inactif" and not m.reseau.gele


def test_sans_veille_le_guet_ne_declenche_aucune_sonde_anticipee(config, vault, faux):
    mono, mur = [0.0], [1000.0]

    async def dormir(d):
        await asyncio.Event().wait()

    async def guetter(_):
        await asyncio.sleep(0)
        mono[0] += 5
        mur[0] += 5

    sonde = Sonde(a=False, b=False)
    m = moteur(config, vault, faux, sonde, dormir=dormir)
    m.reseau.horloge, m.reseau.reel, m.reseau.guetter = lambda: mono[0], lambda: mur[0], guetter
    faux.scenario = [Evenement("erreur", texte=COUPE)]

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        n = sonde.appels
        for _ in range(50):
            await asyncio.sleep(0)
        assert sonde.appels == n and m.reseau.gele
        m.ferme = True
        m.reseau._veille.cancel()

    asyncio.run(essai())


def test_arret_humain_d_une_tache_gelee_annule_sa_reprise(config, vault, faux):
    m = moteur(config, vault, faux, Sonde(a=False, b=False))
    faux.scenario = [Evenement("erreur", texte=COUPE)]

    async def essai():
        m.soumettre("mere", "go")
        await finir(m)
        await m.arreter("mere")
        assert not m.reseau.gele and m.etat_de("mere") == "inactif"
        m.reseau._appliquer({"faux": True, "autre": True})
        assert m.reseau.reprendre() == []

    asyncio.run(essai())
    assert len(faux.lances) == 1


def test_sonde_reelle_refus_de_connexion_donne_faux():
    assert asyncio.run(reseau.sonde_reelle("127.0.0.1:1", 1)) is False
