"""Audit L1 (poste) : régulation RAM sans boucle (hystérésis, garde de reprise, titulaire de la
réservation épargné, plafond sous earlyoom, démarrages espacés) et instance unique par vault."""

import asyncio
import os
from types import SimpleNamespace

import pytest

from conftest import FauxHarnais
from orchestrateur import __main__ as principal
from orchestrateur.harnais import Evenement
from test_simultanes import (GO, FauxPoste, actifs, laisser, lent, moteur, poste,  # noqa: F401
                             soumettre)


async def attendre_repli(m, tache):
    for _ in range(200):
        await asyncio.sleep(0.01)
        if tache not in m.tours and m.etat_de(tache) == "en_file":
            break
    await laisser()


def test_repli_ram_ne_relance_pas_tant_que_la_ram_n_est_pas_sous_le_seuil_de_relance(
        config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre, poste.echec = 10 * GO, True  # Linux : suspension impossible, repli par arrêt
        await soumettre(m, "mere")
        poste.libre = 5 * GO  # 11 Go occupés : coupure
        m._sem.veiller_une_fois()
        await attendre_repli(m, "mere")
        assert len(lent.lances) == 1
        poste.libre = 6.5 * GO  # 9,5 Go : sous le seuil de coupure, au-dessus du seuil de relance
        for _ in range(3):
            m._sem.veiller_une_fois()
            await laisser()
        assert len(lent.lances) == 1, "relancé aussitôt : oscillation coupe/relance"
        poste.libre = 8 * GO  # 8 Go : nettement sous le seuil
        m._sem.veiller_une_fois()
        await laisser()
        assert len(lent.lances) == 2
        await m.fermer()
    asyncio.run(scenario())


def test_repli_ram_repete_sans_progres_ne_relance_pas_deux_fois_en_automatique(
        config, vault, poste):
    class Muet(FauxHarnais):
        scenario, lances, arrets, liberer = ["attendre"], [], [], None

        def __init__(self, conf):
            super().__init__(conf)
            self._proc = SimpleNamespace(pid=4242, returncode=None)

    async def scenario():
        m = moteur(config, vault, Muet, poste, plafond=10, unite="go")
        poste.libre, poste.echec = 10 * GO, True
        await soumettre(m, "mere")
        for tour in range(2):
            poste.libre = 5 * GO
            m._sem.veiller_une_fois()
            await attendre_repli(m, "mere")
            poste.libre = 12 * GO
            m._sem.veiller_une_fois()
            await laisser()
        assert len(Muet.lances) == 2, "un 2e repli sans progrès a relancé le tour"
        assert m.etat_de("mere") == "interrompu"
        await m.fermer()
    asyncio.run(scenario())


def test_titulaire_de_la_reservation_du_poste_n_est_pas_coupe_par_la_regulation(
        config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO
        await soumettre(m, "mere")
        m.poste.reserver("mere", "porte complète")
        poste.libre = 4 * GO
        m._sem.veiller_une_fois()
        await laisser()
        assert actifs(m) == ["mere"] and not m._sem.en_pause("mere") and not lent.arrets
        await m.fermer()
    asyncio.run(scenario())


def test_plafond_regle_au_dessus_de_earlyoom_est_ramene_sous_son_seuil(config, vault, lent, poste):
    m = moteur(config, vault, lent, poste, plafond=95, unite="pct")
    mesure = poste.mesurer()
    assert m._sem.seuil(mesure) <= int(mesure.total * 0.85)


def test_demarrage_refuse_quand_la_marge_de_ram_ne_couvre_pas_un_nouveau_tour(
        config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=80, unite="pct")
        poste.occuper(79)  # 160 Mo de marge : un tour Claude en demande 450 à 600
        await soumettre(m, "mere")
        m._sem.veiller_une_fois()
        await laisser()
        assert m.etat_de("mere") == "en_file"
        await m.fermer()
    asyncio.run(scenario())


def test_reprise_au_demarrage_attend_que_le_poste_soit_sous_le_seuil(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 4 * GO  # poste chargé au redémarrage
        m.interrompus["mere"] = {"tache": "mere", "texte": "travaille mere", "sauts": 0}
        from orchestrateur import reprise
        reprise.reprendre_au_demarrage(m)
        await laisser()
        assert m.etat_de("mere") == "en_file" and not lent.lances
        poste.libre = 10 * GO
        m._sem.veiller_une_fois()
        await laisser()
        assert len(lent.lances) == 1
        await m.fermer()
    asyncio.run(scenario())


# --- C1 : instance unique par vault ----------------------------------------------------------

def test_deuxieme_demarrage_sur_le_meme_vault_est_refuse_avec_un_message_clair(tmp_path):
    verrou = tmp_path / "v.lock"
    premier = principal.prendre_verrou(verrou, tmp_path / "vault", 8300)
    with pytest.raises(SystemExit) as e:
        principal.prendre_verrou(verrou, tmp_path / "vault", 8301)
    msg = str(e.value)
    assert str(os.getpid()) in msg and "8300" in msg and "vault" in msg.lower()
    premier.close()


def test_demarrage_permis_apres_la_mort_du_premier(tmp_path):
    verrou = tmp_path / "v.lock"
    premier = principal.prendre_verrou(verrou, tmp_path / "vault", 8300)
    premier.close()  # le système rend le verrou à la mort du processus
    principal.prendre_verrou(verrou, tmp_path / "vault", 8301).close()


def test_deux_vaults_differents_ne_se_genent_pas(tmp_path):
    a = principal.prendre_verrou(principal.fichier_verrou(tmp_path / "a"), tmp_path / "a", 8300)
    b = principal.prendre_verrou(principal.fichier_verrou(tmp_path / "b"), tmp_path / "b", 8301)
    a.close(); b.close()


def test_main_refuse_de_demarrer_si_le_vault_est_deja_tenu(tmp_path, monkeypatch):
    conf = SimpleNamespace(vault=SimpleNamespace(racine=tmp_path / "vault"), port=8399)
    monkeypatch.setattr(principal, "charger", lambda: conf)
    monkeypatch.setattr(principal, "fichier_verrou", lambda racine: tmp_path / "v.lock")
    monkeypatch.setattr(principal, "creer_app", lambda c: pytest.fail("l'application ne doit pas démarrer"))
    tenu = principal.prendre_verrou(tmp_path / "v.lock", tmp_path / "vault", 8300)
    with pytest.raises(SystemExit):
        principal.main()
    tenu.close()


# --- C4 : l'arrêt d'un tour atteint les processus détachés -----------------------------------

@pytest.mark.skipif(os.name == "nt", reason="groupes de processus POSIX")
def test_arret_du_tour_tue_aussi_le_navigateur_detache_dans_son_propre_groupe(tmp_path):
    import subprocess
    import sys
    import time

    from orchestrateur.harnais.processus import SESSION_PROPRE, arreter_arbre

    pidfichier = tmp_path / "petit-fils.pid"
    petit_fils = ("import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
                  "start_new_session=True); open(sys.argv[1],'w',encoding='utf-8').write(str(p.pid)); import time; time.sleep(60)")

    def vivant(pid):
        try:
            return open(f"/proc/{pid}/stat", encoding="utf-8").read().rpartition(")")[2].split()[0] != "Z"
        except OSError:
            return False

    async def scenario():
        proc = await asyncio.create_subprocess_exec(sys.executable, "-c", petit_fils, str(pidfichier),
                                                    **SESSION_PROPRE)
        for _ in range(100):
            if pidfichier.exists() and pidfichier.read_text(encoding="utf-8"):
                break
            await asyncio.sleep(0.05)
        detache = int(pidfichier.read_text(encoding="utf-8"))
        assert vivant(detache)
        await arreter_arbre(proc)
        await proc.wait()
        for _ in range(100):
            if not vivant(detache):
                break
            await asyncio.sleep(0.05)
        try:
            assert not vivant(detache), "le processus détaché a survécu à l'arrêt du tour"
        finally:
            if vivant(detache):
                os.kill(detache, 9)
    asyncio.run(scenario())
