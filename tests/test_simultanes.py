"""Agents simultanés (INV-SIMULT-1) : nombre fixe, optimisation, plafond de RAM, pause et reprise,
repli par arrêt et remise en file. Le poste est simulé : aucune mesure ni suspension réelle."""

import asyncio
import itertools
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.api_simultanes import ecrire_cles
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Moteur
from orchestrateur.poste_ram import Mesure
from orchestrateur.vault import Conflit
from conftest import FauxHarnais

GO = 1024 ** 3
PIDS = itertools.count(1000, 10)


class FauxPoste:
    def __init__(self):
        self.total, self.libre, self.cpu = 16 * GO, 8 * GO, 0.0
        self.suspendus: list[int] = []
        self.echec = False
        self.disponible = True

    def occuper(self, pct):
        self.libre = int(self.total * (100 - pct) / 100)

    def mesurer(self):
        return Mesure(self.total, self.libre, self.cpu) if self.disponible else None

    def arbre(self, pid):
        return [pid, pid + 1]

    def memoire_travail(self, pids):
        return GO

    def suspendre(self, pids):
        if self.echec:
            return False
        self.suspendus += [p for p in pids if p not in self.suspendus]
        return True

    def reprendre(self, pids):
        self.suspendus = [p for p in self.suspendus if p not in pids]
        return True

    figer, degeler = suspendre, reprendre


@pytest.fixture
def lent():
    """Harnais factice qui tourne jusqu'à son arrêt, avec un processus (pid) à suspendre."""
    class Lent(FauxHarnais):
        scenario = [Evenement("session", session="s"), "attendre"]
        lances, arrets, liberer = [], [], None

        def __init__(self, conf):
            super().__init__(conf)
            self._proc = SimpleNamespace(pid=next(PIDS), returncode=None)
    return Lent


@pytest.fixture
def poste():
    return FauxPoste()


def moteur(config, vault, lent, poste, mode="plafond", **reglage):
    config.moteur.simultanes_max = 2
    config.simultanes.mode = mode
    config.simultanes.intervalle_s = 3600  # la veille est pilotée à la main par le test
    for k, v in reglage.items():
        setattr(config.simultanes, k, v)
    m = Moteur(config, vault, {"faux": lent})
    m._sem.poste = poste
    return m


async def laisser():
    for _ in range(20):
        await asyncio.sleep(0)


async def soumettre(m, *taches):
    for t in taches:
        m.soumettre(t, f"travaille {t}")
    await laisser()


def actifs(m):
    return sorted(m.tours)


def test_mode_fixe_borne_au_nombre_sans_mesure(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        await soumettre(m, "mere", "enfant", "petit")
        assert actifs(m) == ["enfant", "mere"] and m.etat_de("petit") == "en_file"
        assert m._sem._veille is None  # aucune veille en mode fixe
        await m.fermer()
    asyncio.run(scenario())


def test_plafond_demarre_un_tour_par_mesure_tant_que_la_ram_reste_sous_le_plafond(
        config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=80, unite="pct")
        poste.occuper(50)
        await soumettre(m, "mere", "enfant", "petit")
        assert actifs(m) == ["mere"]  # un seul démarrage avant la mesure suivante
        m._sem.veiller_une_fois()
        await laisser()
        assert actifs(m) == ["enfant", "mere"]
        poste.occuper(75)  # marge de 5 % : de quoi absorber un tour (COUT_TOUR)
        m._sem.veiller_une_fois()
        await laisser()
        assert len(m.tours) == 3  # garde (10) et non plus le nombre fixe (2)
        poste.occuper(81)
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("petit")
        await m.fermer()
    asyncio.run(scenario())


def test_ram_saturee_met_en_pause_du_plus_recent_et_reprend_en_ordre_inverse(
        config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO  # 6 Go occupés
        await soumettre(m, "mere")
        m._sem.veiller_une_fois()
        await soumettre(m, "enfant")
        pid_mere, pid_enfant = (m.tours[t].harnais._proc.pid for t in ("mere", "enfant"))
        poste.libre = 4 * GO  # 12 Go occupés : au-dessus du plafond (une autre application)
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("enfant") and not m._sem.en_pause("mere")
        assert poste.suspendus == [pid_enfant, pid_enfant + 1]
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("mere")
        m.soumettre("petit", "attends")
        await laisser()
        assert m.etat_de("petit") == "en_file"  # la file attend tant qu'une pause dure
        poste.libre = 7 * GO  # 9 Go occupés : 1 Go rendu par la reprise tient sous 10 Go
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("enfant") and not m._sem.en_pause("mere")  # ordre inverse
        assert poste.suspendus == [pid_enfant, pid_enfant + 1]
        assert m.vault.tache("mere").statut == "en-cours"  # aucun travail perdu
        await m.fermer()
    asyncio.run(scenario())


def test_reprise_attend_la_place_de_la_memoire_rendue(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO
        await soumettre(m, "mere")
        poste.libre = 5 * GO
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("mere")
        poste.libre = 6.5 * GO  # 9,5 Go occupés + 1 Go à rendre > 10 Go
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("mere")
        await m.fermer()
    asyncio.run(scenario())


def test_reprendre_maintenant_exempte_le_tour_de_toute_nouvelle_pause(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO
        await soumettre(m, "mere")
        poste.libre = 4 * GO
        m._sem.veiller_une_fois()
        assert m._sem.reprendre("mere", force=True)
        m._sem.veiller_une_fois()
        assert not m._sem.en_pause("mere") and poste.suspendus == []
        await m.fermer()
    asyncio.run(scenario())


def test_suspension_impossible_arrete_le_tour_et_le_remet_en_tete_de_file_meme_session(
        config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre, poste.echec = 10 * GO, True
        await soumettre(m, "mere")
        m.soumettre("mere", "message suivant")
        poste.libre = 4 * GO
        m._sem.veiller_une_fois()
        for _ in range(100):
            await asyncio.sleep(0.01)
            if "mere" not in m.tours and m.etat_de("mere") == "en_file":
                break
        await laisser()
        assert len({id(h) for h in lent.arrets}) == 1 and "mere" not in m.tours
        assert len(lent.lances) == 1  # la file attend que la RAM le permette
        poste.libre = 10 * GO
        m._sem.veiller_une_fois()
        await laisser()
        assert len(lent.lances) == 2 and "libérer la RAM" in lent.lances[-1]["message"]
        assert lent.lances[-1]["session"] == "s"  # même session du harnais, avant le message suivant
        assert [e.texte for e in m.files["mere"]] == ["message suivant"]
        await m.fermer()
    asyncio.run(scenario())


def test_optimiser_garde_la_marge_de_ram_et_le_processeur(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="optimiser", marge_pct=20, cpu_max_pct=90)
        poste.occuper(85)
        await soumettre(m, "mere")
        assert actifs(m) == []
        poste.occuper(50)
        poste.cpu = 95
        m._sem.veiller_une_fois()
        await laisser()
        assert actifs(m) == []
        poste.cpu = 10
        m._sem.veiller_une_fois()
        await laisser()
        assert actifs(m) == ["mere"]
        await m.fermer()
    asyncio.run(scenario())


def test_mesure_indisponible_retombe_sur_le_nombre_fixe(config, vault, lent, poste):
    async def scenario():
        poste.disponible = False
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        await soumettre(m, "mere", "enfant", "petit")
        assert actifs(m) == ["enfant", "mere"]
        assert m._sem.public()["mesure_disponible"] is False
        await m.fermer()
    asyncio.run(scenario())


def test_ecrire_cles_garde_le_reste_du_fichier(tmp_path):
    f = tmp_path / "config.toml"
    f.write_bytes(b"# tete\r\n[moteur]\r\nsimultanes_max = 6 # commentaire\r\nsauts_max = 8\r\n\r\n[x]\r\na = 1\r\n")
    ecrire_cles(f, "moteur", {"simultanes_max": 3})
    ecrire_cles(f, "simultanes", {"mode": "plafond", "plafond": 12.5})
    assert f.read_bytes() == (b"# tete\r\n[moteur]\r\nsimultanes_max = 3\r\nsauts_max = 8\r\n\r\n[x]\r\na = 1\r\n"
                              b"\r\n[simultanes]\r\nmode = \"plafond\"\r\nplafond = 12.5\r\n")


def test_api_regle_persiste_et_refuse_l_invalide(config, vault, lent, tmp_path):
    config.chemin = tmp_path / "config.toml"
    config.chemin.write_text("[moteur]\nsimultanes_max = 2\n", encoding="utf-8")
    m = Moteur(config, vault, {"faux": lent})
    m._sem.poste = FauxPoste()
    with TestClient(api.creer_app(config, m), base_url="http://127.0.0.1:8399") as c:
        h = {"X-Orchestrateur": "1"}
        r = c.put("/api/simultanes", json={"mode": "plafond", "plafond": 12, "unite": "go",
                                           "simultanes_max": 4}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "plafond" and r.json()["ram"]["seuil"] == 12 * GO
        assert config.moteur.simultanes_max == 4
        texte = config.chemin.read_text(encoding="utf-8")
        assert "simultanes_max = 4" in texte and 'mode = "plafond"' in texte
        assert c.put("/api/simultanes", json={"mode": "turbo"}, headers=h).status_code == 400
        assert c.put("/api/simultanes", json={"plafond": 120, "unite": "pct"}, headers=h).status_code == 400
        assert config.simultanes.mode == "plafond"  # un refus ne change rien
        assert c.post("/api/taches/mere/reprendre-ram", headers=h).status_code == 409
        assert c.get("/api/simultanes").json()["limite"] == 10


def test_en_tete_commente_n_est_pas_dedouble(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text("[moteur]  # réglages\nsimultanes_max = 6\n", encoding="utf-8")
    ecrire_cles(f, "moteur", {"simultanes_max": 2})
    assert f.read_text(encoding="utf-8") == "[moteur]  # réglages\nsimultanes_max = 2\n"


@pytest.mark.parametrize("reglage", [{"plafond": float("nan")}, {"plafond": float("inf"), "unite": "go"},
                                     {"garde_max": 0}, {"marge_pct": 100}])
def test_reglage_non_fini_ou_hors_bornes_refuse(reglage):
    from orchestrateur.config import ConfigSimultanes
    with pytest.raises(ValueError):
        ConfigSimultanes(**reglage)


def test_reprise_refusee_garde_la_pause_et_reessaie(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO
        await soumettre(m, "mere")
        poste.libre = 4 * GO
        m._sem.veiller_une_fois()
        poste.reprendre = lambda pids: False
        assert not m._sem.reprendre("mere", force=True)
        assert m._sem.en_pause("mere")  # aucun processus laissé figé hors de suivi
        await m.fermer()
    asyncio.run(scenario())


def test_tour_arrete_pendant_sa_pause_libere_la_file(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO
        await soumettre(m, "mere")
        poste.libre = 4 * GO
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("mere")
        await m.arreter("mere")
        await laisser()
        assert not m._sem.pauses and m._sem.pris == 0
    asyncio.run(scenario())


def test_pause_manuelle_echappe_a_la_regulation_et_reprend_a_la_main(config, vault, lent, poste):
    """INV-TRAVAUX-2 : la veille ne reprend jamais un tour mis en pause à la main."""
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=90, unite="pct")
        await soumettre(m, "mere")
        pid = m.tours["mere"].harnais._proc.pid
        m._sem.pauser_main("mere")
        assert poste.suspendus == [pid, pid + 1] and m._sem.en_pause_manuelle("mere")
        with pytest.raises(Conflit):
            m._sem.pauser_main("mere")
        m._sem.veiller_une_fois()
        assert m._sem.en_pause_manuelle("mere") and poste.suspendus
        m._sem.reprendre_main("mere")
        assert poste.suspendus == [] and not m._sem.en_pause("mere")
        with pytest.raises(Conflit):
            m._sem.reprendre_main("mere")
        await m.fermer()
    asyncio.run(scenario())
